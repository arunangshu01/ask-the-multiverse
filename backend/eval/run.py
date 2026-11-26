"""Evaluation: plan accuracy and answer accuracy of the Multiverse Console.

    .venv/bin/python -m eval.run            # rule planner, current snapshot
    .venv/bin/python -m eval.run --llm      # LLM planner (needs GROQ_API_KEY or GEMINI_API_KEY)

Checks per question: the planned tool, ids that must appear in the result rows, strings that must
appear in the answer, numbers that must equal a SQL count, and that unsupported questions get no
grounded answer. Exit code 1 if answer accuracy is below --min."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path

from app import settings
from app.qa import engine, llm, router, tools
from app.store import Store

QUESTIONS = Path(__file__).with_name("questions.json")


def load() -> list[dict]:
    return json.loads(QUESTIONS.read_text())


def check(store: Store, case: dict, tool: str | None, result: tools.Result | None, answer: str, grounded: bool) -> list[str]:
    errors = []
    if tool != case.get("tool") and tool not in case.get("also_ok", []):
        errors.append(f"planned {tool}, expected {case.get('tool')}")
    if case.get("unsupported"):
        if grounded:
            errors.append("unsupported question got a grounded answer")
        return errors
    if result is None:
        return errors + ["no result"]
    ids = {str(v) for r in result.rows for v in r.values()}
    missing = [i for i in case.get("rows_include", []) if i not in ids]
    if missing:
        errors.append(f"rows missing {missing}")
    for s in case.get("answer_includes", []):
        if s not in answer:
            errors.append(f"answer missing '{s}'")
    if case.get("answer_sql"):
        n = store.scalar(case["answer_sql"])
        if f"{n:,}" not in answer:
            errors.append(f"answer lacks the count {n:,}")
    return errors


async def run_case(store: Store, case: dict, use_llm: bool) -> dict:
    if use_llm:
        evs = [e async for e in engine.ask(store, case["q"])]
        plan = next((e.get("plan") for e in evs if e.get("plan")), None) or {}
        tool = plan.get("tool") or ("sql" if plan.get("sql") else None)
        ans = next((e for e in evs if e["type"] == "answer"), {"text": "", "grounded": False})
        result = None
        if tool in tools.TOOLS:
            try:
                result = tools.run(store, tool, plan.get("args", {}))
            except Exception:  # noqa: BLE001 - reported as a failed case
                result = None
        return {"tool": tool, "result": result, "answer": ans["text"], "grounded": ans.get("grounded", False)}
    planned = router.plan(case["q"])
    if not planned:
        return {"tool": None, "result": None, "answer": "", "grounded": False}
    result = tools.run(store, *planned)
    return {"tool": planned[0], "result": result, "answer": result.answer, "grounded": result.ok}


async def main_async(args) -> int:
    store = Store(settings.DATA_DIR)
    store.load()
    if args.llm and not llm.configured():
        raise SystemExit("--llm needs GROQ_API_KEY or GEMINI_API_KEY in backend/.env")
    cases = load()
    plan_ok = answer_ok = 0
    for case in cases:
        out = await run_case(store, case, args.llm)
        errors = check(store, case, out["tool"], out["result"], out["answer"], out["grounded"])
        plan_ok += out["tool"] == case.get("tool") or out["tool"] in case.get("also_ok", [])
        answer_ok += not errors
        mark = "PASS" if not errors else "FAIL"
        print(f"[{mark}] {case['q']}" + ("" if not errors else f"\n       {'; '.join(errors)}"))
    n = len(cases)
    print(f"\nplanner: {'llm' if args.llm else 'rules'} | questions: {n} | plan accuracy: {plan_ok / n:.0%} "
          f"| answer accuracy: {answer_ok / n:.0%}")
    return 0 if answer_ok / n >= args.min else 1


def main():
    ap = argparse.ArgumentParser(prog="python -m eval.run")
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--min", type=float, default=0.9)
    raise SystemExit(asyncio.run(main_async(ap.parse_args())))


if __name__ == "__main__":
    main()
