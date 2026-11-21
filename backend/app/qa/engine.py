"""Multiverse Console engine: question -> resolve names -> plan (LLM, else rules)
-> checked, read-only query -> answer built only from the returned rows, with
citations. Yields progress events for the streaming API."""

from __future__ import annotations

import json
import re
import time
from collections import OrderedDict
from typing import AsyncIterator

from anyio import to_thread

from app import settings
from app.qa import llm, resolve, router, sqlguard, tools
from app.store import Store

PLANNER_SYSTEM = """You plan database queries for "Ask the Multiverse", an index of the Marvel Database wiki.
Return ONLY a JSON object, one of:
  {"tool": "<name>", "args": {...}}                       -- preferred
  {"sql": "<one DuckDB SELECT>", "explain": "<what it returns>"}  -- only if no tool fits
  {"unsupported": "<why the data cannot answer this>"}
Tools (args ending in ? are optional; pass names as written by the user, ids are resolved for you):
%s

%s
Rules: never invent ids or facts; prefer a tool; SQL must be a single read-only SELECT over the tables above;
questions about real-world box office, actors' private lives, opinions or rankings the data has no column for are unsupported."""

ANSWER_SYSTEM = """You write the answer for "Ask the Multiverse" using ONLY the JSON rows given.
Rules: do not add any fact, name or number that is not in the rows; if the rows are empty say the data has no match;
be concise (under 120 words); use short bullet points for lists; mention row values exactly as written;
refer to sources with [n] markers matching the numbered citation list. Plain ASCII hyphens only."""

EDGE_KIND = {"fought_both": "enemy", "opponents": "enemy", "team_overlap": "team", "team_members": "team",
             "variants": "variant", "relatives": "family", "event_sides": "ally", "allies": "ally",
             "first_fight": "enemy", "deaths": "enemy", "relationship": "enemy"}
_cache: OrderedDict[str, tuple[float, list[dict]]] = OrderedDict()
CACHE_TTL = 3600


def _tool_doc() -> str:
    return "\n".join(f"- {n}({', '.join(p)}): {d}" for n, (_, p, d) in tools.TOOLS.items())


def _key(question: str, store: Store) -> str:
    return f"{store.snapshot.get('run_id')}|{' '.join(question.lower().split())}"


def _event(etype: str, **data) -> dict:
    return {"type": etype, **data}


def verify(answer: str, rows: list[dict], question: str) -> list[str]:
    """Numbers and capitalised names in the answer that appear neither in the rows nor the question."""
    haystack = (json.dumps(rows, default=str) + " " + question).lower()
    problems = []
    for num in re.findall(r"\b\d[\d,]*\b", answer):
        if num.replace(",", "") not in haystack.replace(",", "") and not re.fullmatch(r"\d", num):
            problems.append(num)
    for name in re.findall(r"\b[A-Z][a-zA-Z'-]+(?:\s+[A-Z][a-zA-Z'-]+)+\b", answer):
        if name.lower() not in haystack:
            problems.append(name)
    return problems


def _table_answer(rows: list[dict], explain: str | None) -> str:
    if not rows:
        return "The query returned no rows, so the data has no match for that."
    cols = list(rows[0])[:4]
    lines = [f"{explain or 'Query result'} ({len(rows)} row{'s' if len(rows) != 1 else ''}):"]
    for r in rows[:15]:
        lines.append("- " + "; ".join(f"{c}: {r[c]}" for c in cols if r[c] not in (None, "", [])))
    if len(rows) > 15:
        lines.append(f"...and {len(rows) - 15} more rows.")
    return "\n".join(lines)


async def ask(store: Store, question: str) -> AsyncIterator[dict]:
    question = question.strip()[:400]
    key = _key(question, store)
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_TTL:
        for ev in hit[1]:
            yield ev
        yield _event("cached")
        return
    events: list[dict] = []

    def emit(ev):
        events.append(ev)
        return ev

    yield emit(_event("step", id="resolve", label="Resolving names across realities", status="running"))
    hints = await to_thread.run_sync(resolve.spans, store, question)
    yield emit(_event("step", id="resolve", status="done",
                      detail=", ".join(f"{h['span']} -> {h['top_entity']}" for h in hints[:4]) or "no known names"))

    yield emit(_event("step", id="plan", label="Planning the query", status="running"))
    plan, planner, unsupported = None, "rules", None
    if llm.configured():
        prompt = PLANNER_SYSTEM % (_tool_doc(), sqlguard.SCHEMA_DOC)
        hint_txt = "\n".join(f"- '{h['span']}' matches {h['matches']} pages, most often {h['top_entity']} ({h['kind']})"
                             for h in hints) or "- none"
        text, provider = await llm.complete(prompt, f"Question: {question}\nKnown names in the question:\n{hint_txt}",
                                            as_json=True, max_tokens=500)
        obj = llm.parse_json(text)
        if obj and obj.get("tool") in tools.TOOLS and isinstance(obj.get("args"), dict):
            plan, planner = ("tool", obj["tool"], obj["args"]), provider
        elif obj and isinstance(obj.get("sql"), str):
            plan, planner = ("sql", obj["sql"], obj.get("explain")), provider
        elif obj and obj.get("unsupported"):
            unsupported, planner = str(obj["unsupported"])[:300], provider
    if plan is None and unsupported is None:
        ruled = router.plan(question)
        if ruled:
            plan, planner = ("tool", *ruled), "rules" if not llm.configured() else "rules (LLM plan unusable)"
    if plan is None:
        yield emit(_event("step", id="plan", status="done", detail=f"planner: {planner}"))
        msg = (f"The data can't answer that: {unsupported}" if unsupported else
               "I can't map that question onto the data I have. Try asking about a character's origin or powers, "
               "a reality, first appearances, variants, team members, who fought whom (and when first), allies, "
               "how two characters are connected, who killed whom, family, creators or reality counts.")
        yield emit(_event("answer", text=msg, grounded=False))
        yield emit(_event("done", ok=False))
        return
    yield emit(_event("step", id="plan", status="done", detail=f"planner: {planner}",
                      plan={"tool": plan[1], "args": plan[2]} if plan[0] == "tool" else {"sql": plan[1]}))

    yield emit(_event("step", id="query", label="Traversing the graph", status="running"))
    result: tools.Result | None = None
    sql_rows, sql_text = None, None
    try:
        if plan[0] == "tool":
            try:
                result = await to_thread.run_sync(tools.run, store, plan[1], plan[2])
            except (ValueError, TypeError) as exc:
                ruled = router.plan(question)
                if not ruled:
                    raise
                result = await to_thread.run_sync(tools.run, store, ruled[0], ruled[1])
        else:
            cur = store.cursor()
            try:
                sql_text = sqlguard.validate(cur, plan[1])
                sql_rows = await to_thread.run_sync(sqlguard.run, cur, plan[1])
            finally:
                cur.close()
    except sqlguard.UnsafeQuery as exc:
        yield emit(_event("step", id="query", status="error", detail=str(exc)))
        ruled = router.plan(question)
        if ruled:
            result = await to_thread.run_sync(tools.run, store, ruled[0], ruled[1])
        else:
            yield emit(_event("answer", text=f"The generated query was rejected ({exc}), so I won't guess.", grounded=False))
            yield emit(_event("done", ok=False))
            return
    except Exception as exc:
        yield emit(_event("step", id="query", status="error", detail=f"{type(exc).__name__}: {str(exc)[:200]}"))
        yield emit(_event("answer", text="The query failed, so I can't answer that reliably.", grounded=False))
        yield emit(_event("done", ok=False))
        return

    if result is not None:
        yield emit(_event("query", sql=result.sql, tool=result.tool, rows=len(result.rows)))
        yield emit(_event("step", id="query", status="done", detail=f"{len(result.rows)} rows"))
        yield emit(_event("graph", nodes=result.nodes, edges=result.edges, kind=EDGE_KIND.get(result.tool, "team")))
        yield emit(_event("step", id="ground", label="Grounding the answer in sources", status="running"))
        answer = result.answer + (f"\n\n{result.note}" if result.note else "")
        yield emit(_event("answer", text=answer, grounded=result.ok))
        yield emit(_event("citations", items=list({c["url"]: c for c in result.citations}.values())))
        yield emit(_event("step", id="ground", status="done", detail=f"{len(result.citations)} sources"))
        yield emit(_event("done", ok=result.ok))
    else:
        yield emit(_event("query", sql=sql_text, tool="sql", rows=len(sql_rows)))
        yield emit(_event("step", id="query", status="done", detail=f"{len(sql_rows)} rows"))
        ids = [str(v) for r in sql_rows[:30] for v in r.values() if isinstance(v, str)]
        known = await to_thread.run_sync(
            lambda: store.rows("SELECT id, url FROM entities WHERE id IN (SELECT unnest($i)) UNION ALL "
                               "SELECT id, sources[1].url FROM realities WHERE id IN (SELECT unnest($i))", {"i": ids}))
        cites = [{"label": f"Marvel Database: {k['id']}", "url": k["url"]} for k in known[:12]]
        yield emit(_event("graph", nodes=[k["id"] for k in known[:20]], edges=[]))
        yield emit(_event("step", id="ground", label="Grounding the answer in sources", status="running"))
        answer, grounded = _table_answer(sql_rows, plan[2]), True
        if sql_rows and llm.configured():
            numbered = "\n".join(f"[{i + 1}] {c['label']}" for i, c in enumerate(cites))
            text, _ = await llm.complete(ANSWER_SYSTEM, f"Question: {question}\nRows: {json.dumps(sql_rows[:40], default=str)}"
                                         f"\nCitations:\n{numbered}", max_tokens=400)
            if text and not verify(text, sql_rows, question):
                answer = text
        yield emit(_event("answer", text=answer, grounded=grounded))
        yield emit(_event("citations", items=cites))
        yield emit(_event("step", id="ground", status="done", detail=f"{len(cites)} sources"))
        yield emit(_event("done", ok=True))
    _cache[key] = (time.monotonic(), events)
    while len(_cache) > settings.ASK_CACHE_SIZE:
        _cache.popitem(last=False)
