"""Typed, read-only query tools over the knowledge graph.

Each tool resolves its names, runs parameterised SQL and returns the rows it
used, the SQL (shown to the user), citations to the exact pages, a templated
answer built only from those rows, and graph nodes/edges to highlight."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.qa import resolve
from app.store import Store

NOT_PRESENT_FLAGS = ("mentioned", "recap", "image", "vision", "fictional", "voice", "corpse", "impersonation", "offpanel", "narration")
NOT_PRESENT = "[" + ",".join(f"'{f}'" for f in NOT_PRESENT_FLAGS) + "]"
WIKI = "https://marvel.fandom.com/wiki/"
MEMBER_TYPES = "('member','former_member','leader','former_leader')"


def url(title: str) -> str:
    return WIKI + title.replace(" ", "_").replace("?", "%3F")


@dataclass
class Result:
    tool: str
    ok: bool
    answer: str
    rows: list[dict] = field(default_factory=list)
    sql: str = ""
    citations: list[dict] = field(default_factory=list)
    nodes: list[str] = field(default_factory=list)
    edges: list[list[str]] = field(default_factory=list)
    resolved: dict = field(default_factory=dict)
    note: str | None = None


def show_sql(sql: str, params: dict) -> str:
    """The SQL with parameters inlined, for display only (execution stays parameterised)."""
    def lit(v):
        return "'" + str(v).replace("'", "''") + "'" if isinstance(v, str) else str(v)
    out = re.sub(r"\$(\w+)", lambda m: lit(params[m.group(1)]) if m.group(1) in params else m.group(0), sql)
    return re.sub(r"\n\s+", "\n  ", out.strip())


def _cite(label, title=None, link=None):
    return {"label": label, "url": link or url(title or label)}


def _name(e: dict) -> str:
    """'Silver Surfer (Norrin Radd, Earth-616)', 'Thanos (Earth-616)', 'Avengers (Earth-616)'."""
    lab = e.get("label") or e.get("name") or e["id"]
    m = re.match(r"^(.*?) \(([^()]*)\)$", e["id"])
    if not m or lab == e["id"]:
        return e["id"]
    base, reality = m.groups()
    return f"{lab} ({reality})" if lab == base else f"{lab} ({base}, {reality})"


def _missing(tool, what, name, alts=None) -> Result:
    msg = f"I couldn't find {what} called \"{name}\" in the index, so I can't answer that."
    return Result(tool, False, msg, note="unresolved name")


def _alts_note(alts) -> str | None:
    if not alts:
        return None
    return "Other matches: " + ", ".join(a["id"] for a in alts[:4]) + "."


# ------------------------------------------------------------------ realities

def reality_info(store: Store, reality: str) -> Result:
    rid = resolve.reality_id(store, reality) or reality
    r = store.one("SELECT * FROM realities WHERE id = $id", {"id": rid})
    sql = show_sql("SELECT id, name, kind, medium, first_appearance, first_year, status, description\nFROM realities WHERE id = $id", {"id": rid})
    if not r:
        return Result("reality_info", False, f"{reality} is not in the reality index.", sql=sql)
    counts = store.one("""SELECT count(*) FILTER (WHERE TRUE) AS characters FROM characters WHERE reality = $id""", {"id": rid})
    kind = {"numbered": "an officially numbered reality", "temporary": "a reality with a temporary (wiki-assigned) number",
            "dimension": "a dimension", "realm": "a realm", "named": "a named reality",
            "variant_suffix": "a reality with a variant designation", "bucket": "a bucket for unknown realities"}[r["kind"]]
    parts = [f"**{rid}**{' - ' + r['name'] if r['name'] and r['name'] != rid else ''} is {kind} "
             f"({r['medium'].lower() if r['medium'] != 'Unclassified' else 'medium not classified'})."]
    if r["description"]:
        parts.append(r["description"])
    facts = []
    if r["first_appearance"]:
        facts.append(f"- First appearance: {r['first_appearance']}" + (f" ({r['first_year']})" if r["first_year"] else ""))
    if r["parents"]:
        facts.append(f"- Branched from: {', '.join(r['parents'])}")
    if counts and counts["characters"]:
        facts.append(f"- Character pages from it: {counts['characters']:,}")
    if r["status"] not in ("unknown", "bucket"):
        facts.append(f"- Status: {r['status']}")
    cites = [{"label": s["label"], "url": s["permalink"] or s["url"]} for s in r["sources"]]
    return Result("reality_info", True, "\n".join(parts + facts), rows=[{k: r[k] for k in (
        "id", "name", "kind", "medium", "first_appearance", "first_year", "status")}], sql=sql, citations=cites,
        resolved={"reality": rid})


def count_realities(store: Store, medium: str | None = None, kind: str | None = None) -> Result:
    where, params = [], {}
    if medium:
        where.append("medium = $medium"); params["medium"] = medium
    if kind:
        where.append("kind = $kind"); params["kind"] = kind
    clause = "WHERE " + " AND ".join(where) if where else ""
    sql = f"SELECT medium, kind, count(*) AS n FROM realities {clause}\nGROUP BY medium, kind ORDER BY n DESC"
    rows = store.rows(sql, params)
    total = sum(r["n"] for r in rows)
    by_kind, by_medium = {}, {}
    for r in rows:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + r["n"]
        by_medium[r["medium"]] = by_medium.get(r["medium"], 0) + r["n"]
    label = " ".join(x for x in (medium, kind) if x)
    lines = [f"The index holds **{total:,}** {label + ' ' if label else ''}entries" +
             (" (realities, dimensions and realms)." if not label else ".")]
    names = {"numbered": "officially numbered", "temporary": "temporary (TRN)", "dimension": "dimensions",
             "realm": "realms", "named": "named, unnumbered", "variant_suffix": "variant designations",
             "bucket": "unknown-reality bucket"}
    lines += [f"- {names.get(k, k)}: {n:,}" for k, n in sorted(by_kind.items(), key=lambda kv: -kv[1])]
    if not medium:
        lines.append("By medium of first appearance: " + ", ".join(f"{m} {n:,}" for m, n in
                                                                  sorted(by_medium.items(), key=lambda kv: -kv[1])) + ".")
    und = store.scalar(f"SELECT count(*) FROM realities {clause + (' AND' if clause else 'WHERE')} status = 'undocumented'", params)
    if und:
        lines.append(f"{und:,} of them are listed numbers that have no wiki page yet.")
    return Result("count_realities", True, "\n".join(lines), rows=rows, sql=show_sql(sql, params), citations=[
        _cite("Marvel Database: Multiverse/Universe Listing", "Multiverse/Universe_Listing"),
        _cite("Marvel Database: List of Temporary Reality Numbers", "List_of_Temporary_Reality_Numbers"),
        _cite("Marvel Database: Category:Realities", "Category:Realities"),
        _cite("Marvel Database: Category:Dimensions", "Category:Dimensions")])


# ------------------------------------------------------------------ characters, teams, events

PROFILE = [("origin", "Origin"), ("place_of_birth", "Born"), ("citizenship", "Citizenship"),
           ("occupation", "Occupation"), ("base", "Base of operations"), ("marital_status", "Marital status"),
           ("powers", "Powers"), ("abilities", "Abilities"), ("death", "Died in"), ("cause_of_death", "Cause of death")]


def _profile_lines(row: dict, story: bool = True) -> list[str]:
    out = []
    for key, label in PROFILE:
        v = row.get(key)
        if v:
            out.append(f"- {label}: {', '.join(v) if isinstance(v, list) else v}")
    if story and row.get("origin_story"):
        out.append(f"Origin story (opening of the wiki's History section): {row['origin_story']}")
    return out


def origin(store: Store, name: str) -> Result:
    e, alts = resolve.best(store, name, kinds=("character",))
    if not e:
        return _missing("origin", "a character", name)
    sql = """SELECT c.id, c.origin, c.place_of_birth, c.citizenship, c.occupation, c.powers, c.abilities,
       c.first_appearance, w.year AS first_year, c.creators, c.origin_story, c.description
FROM characters c LEFT JOIN works w ON w.id = c.first_work WHERE c.id = $id"""
    row = store.one(sql, {"id": e["id"]})
    shown = show_sql(sql, {"id": e["id"]})
    cites = [_cite(f"Marvel Database: {e['id']}", link=store.scalar("SELECT coalesce(permalink, url) FROM characters WHERE id = $id", {"id": e["id"]}))]
    if not any(row.get(k) for k in ("origin", "origin_story", "description", "place_of_birth", "powers")):
        return Result("origin", True, f"The wiki page for {_name(e)} does not describe its origin.", sql=shown,
                      citations=cites, nodes=[e["id"]], resolved={"entity": e["id"]})
    lines = [f"**{_name(e)}** - who they are and where they come from, as written on the wiki:"]
    if row.get("description"):
        lines.append(row["description"])
    lines += _profile_lines(row)
    if row.get("first_appearance"):
        lines.append(f"- First appearance: {row['first_appearance']}" + (f" ({row['first_year']})" if row["first_year"] else ""))
    if row.get("creators"):
        lines.append(f"- Created by: {', '.join(row['creators'])}")
    lines.append("Text is shortened from the wiki page; follow the source for the full history.")
    return Result("origin", True, "\n".join(lines), rows=[{k: v for k, v in row.items() if k not in ("origin_story", "description")}],
                  sql=shown, citations=cites, nodes=[e["id"]], resolved={"entity": e["id"]}, note=_alts_note(alts))

def entity_info(store: Store, name: str) -> Result:
    e, alts = resolve.best(store, name)
    if not e:
        rid = resolve.reality_id(store, name)
        if rid:
            return reality_info(store, rid)
        return _missing("entity_info", "a character, team or event", name)
    table = {"character": "characters", "team": "teams", "organization": "teams", "event": "events"}[e["kind"]]
    sql = f"SELECT * FROM {table} WHERE id = $id"
    row = store.one(sql, {"id": e["id"]})
    lines = [f"**{_name(e)}** is a {e['kind']} from {row.get('reality') or 'an unknown reality'}."]
    if row.get("description"):
        lines.append(row["description"])
    if row.get("first_appearance"):
        lines.append(f"- First appearance: {row['first_appearance']}")
    if row.get("creators"):
        lines.append(f"- Created by: {', '.join(row['creators'])}")
    cites = [_cite(f"Marvel Database: {e['id']}", link=row.get("permalink") or row.get("url"))]
    if e["kind"] == "character":
        lines += _profile_lines(row)
        teams = store.rows(f"""SELECT DISTINCT r.dst AS team, r.type FROM relations r WHERE r.src = $id
            AND r.type IN {MEMBER_TYPES} ORDER BY r.type, r.dst LIMIT 12""", {"id": e["id"]})
        if teams:
            lines.append("- Teams: " + ", ".join(f"{t['team']}{' (former)' if t['type'].startswith('former') else ''}" for t in teams))
    if e["kind"] in ("team", "organization"):
        n = store.scalar(f"SELECT count(DISTINCT src) FROM relations WHERE dst = $id AND type IN {MEMBER_TYPES}", {"id": e["id"]})
        lines.append(f"- Members listed on the wiki (current and former): {n:,}")
    return Result("entity_info", True, "\n".join(lines), rows=[{k: v for k, v in row.items() if k not in ("description", "origin_story")}],
                  sql=show_sql(sql, {"id": e["id"]}), citations=cites, nodes=[e["id"]], resolved={"entity": e["id"]},
                  note=_alts_note(alts))


def first_appearance(store: Store, name: str) -> Result:
    if resolve.REALITY_ID.search(name):
        r = reality_info(store, name)
        r.tool = "first_appearance"
        return r
    e, alts = resolve.best(store, name)
    if not e:
        return _missing("first_appearance", "a character, team or event", name)
    table = {"character": "characters", "team": "teams", "organization": "teams", "event": "events"}[e["kind"]]
    sql = f"""SELECT x.id, x.first_appearance, x.first_work, w.year, w.medium, w.url AS work_url
FROM {table} x LEFT JOIN works w ON w.id = x.first_work WHERE x.id = $id"""
    row = store.one(sql, {"id": e["id"]})
    if not row or not row["first_appearance"]:
        return Result("first_appearance", False, f"The wiki page for {e['id']} does not record a first appearance.",
                      sql=show_sql(sql, {"id": e["id"]}), citations=[_cite(f"Marvel Database: {e['id']}", e["id"])])
    year = f" ({row['year']})" if row["year"] else ""
    text = f"**{_name(e)}** first appeared in **{row['first_appearance']}**{year}."
    cites = [_cite(f"Marvel Database: {e['id']}", e["id"])]
    if row["first_work"]:
        cites.append(_cite(f"Marvel Database: {row['first_work']}", row["first_work"]))
    return Result("first_appearance", True, text, rows=[row], sql=show_sql(sql, {"id": e["id"]}), citations=cites,
                  nodes=[e["id"]], resolved={"entity": e["id"]}, note=_alts_note(alts))


HERO = "('featured','supporting')"


def pairs_sql(param: str, same_side: bool = False, medium: str | None = None) -> str:
    """Story pairs for ${param}: opposite sides (one antagonist, the other featured/supporting), or the
    same hero side (both featured/supporting). Mentions, images, visions and similar never count."""
    sides = (f"s.role IN {HERO} AND x.role IN {HERO}" if same_side else
             f"((s.role = 'antagonist' AND x.role IN {HERO}) OR (s.role IN {HERO} AND x.role = 'antagonist'))")
    med = f"\n      AND s.work IN (SELECT id FROM works WHERE medium = ${medium})" if medium else ""
    return f"""SELECT x.entity, x.work, x.story FROM appearances s
    JOIN appearances x ON x.work = s.work AND x.story = s.story AND x.entity <> s.entity
    WHERE s.entity = ${param}
      AND NOT list_has_any(s.flags, {NOT_PRESENT}) AND NOT list_has_any(x.flags, {NOT_PRESENT})
      AND {sides}{med}"""


def fought_both(store: Store, a: str, b: str) -> Result:
    ea, alts_a = resolve.best(store, a)
    eb, alts_b = resolve.best(store, b)
    if not ea or not eb:
        return _missing("fought_both", "a character or team", a if not ea else b)
    params = {"a": ea["id"], "b": eb["id"]}
    sql = f"""WITH opp_a AS ({pairs_sql('a')}),
opp_b AS ({pairs_sql('b')})
SELECT e.id, e.label, e.kind, count(DISTINCT oa.work) AS stories_vs_a, count(DISTINCT ob.work) AS stories_vs_b,
       list(DISTINCT oa.work ORDER BY oa.work)[1:3] AS sample_a, list(DISTINCT ob.work ORDER BY ob.work)[1:3] AS sample_b
FROM opp_a oa JOIN opp_b ob ON ob.entity = oa.entity JOIN entities e ON e.id = oa.entity
WHERE e.kind = 'character' AND e.id NOT IN ($a, $b)
GROUP BY ALL ORDER BY least(stories_vs_a, stories_vs_b) DESC, e.id LIMIT 15"""
    rows = store.rows(sql, params)
    shown = show_sql(sql, params)
    if not rows:
        return Result("fought_both", True, f"In the story appearance data, no character appears on the opposing side "
                      f"of both {_name(ea)} and {_name(eb)}.", sql=shown,
                      citations=[_cite(f"Marvel Database: {ea['id']}", ea["id"]), _cite(f"Marvel Database: {eb['id']}", eb["id"])],
                      nodes=[ea["id"], eb["id"]], resolved={"a": ea["id"], "b": eb["id"]})
    lines = [f"Characters who appear on the opposing side of both **{_name(ea)}** and **{_name(eb)}** in the same "
             f"stories (one as an antagonist, the other as a featured or supporting character), most stories first:"]
    cites, seen = [], set()
    for r in rows[:10]:
        lines.append(f"- **{_name(r)}** - {r['stories_vs_a']} {'story' if r['stories_vs_a'] == 1 else 'stories'} against "
                     f"{ea['label']}, {r['stories_vs_b']} against {eb['label']} (e.g. {r['sample_a'][0]}; {r['sample_b'][0]})")
        for w in (r["sample_a"][0], r["sample_b"][0]):
            if w not in seen:
                seen.add(w)
                cites.append(_cite(f"Marvel Database: {w}", w))
    if len(rows) > 10:
        lines.append(f"...and {len(rows) - 10} more.")
    lines.append("This counts story appearance roles listed on the wiki's issue and episode pages; "
                 "mentions, flashback-only images and visions are excluded.")
    edges = [[r["id"], ea["id"]] for r in rows[:10]] + [[r["id"], eb["id"]] for r in rows[:10]]
    return Result("fought_both", True, "\n".join(lines), rows=rows, sql=shown, citations=cites[:12],
                  nodes=[ea["id"], eb["id"]] + [r["id"] for r in rows[:10]], edges=edges,
                  resolved={"a": ea["id"], "b": eb["id"]}, note=_alts_note(alts_a + alts_b))


MEDIA = ("Comics", "Film", "Television", "Animation", "Games", "Prose")


def _variant_in_medium(store: Store, e: dict, medium: str) -> tuple[dict, str | None]:
    """The variant (same disambiguation page) that appears most in `medium`, used when e itself has no
    opponents there. Returns (entity, original name if switched)."""
    if e["kind"] != "character":
        return e, None
    alt = store.one(f"""SELECT x.id, x.kind, x.label, x.reality, count(DISTINCT a.work) AS n
        FROM characters c JOIN entities x ON x.id = c.id JOIN appearances a ON a.entity = c.id JOIN works w ON w.id = a.work
        WHERE c.variant_group = (SELECT variant_group FROM characters WHERE id = $id) AND c.id <> $id
          AND w.medium = $m AND NOT list_has_any(a.flags, {NOT_PRESENT})
        GROUP BY ALL ORDER BY n DESC, x.id LIMIT 1""", {"id": e["id"], "m": medium})
    return (alt, _name(e)) if alt else (e, None)


def _medium(medium: str | None) -> str | None:
    if not medium:
        return None
    m = next((x for x in MEDIA if x.lower() == medium.strip().lower()), None)
    if not m:
        raise ValueError(f"medium must be one of {', '.join(MEDIA)}")
    return m


def opponents(store: Store, name: str, medium: str | None = None) -> Result:
    e, alts = resolve.best(store, name)
    if not e:
        return _missing("opponents", "a character or team", name)
    medium = _medium(medium)
    switched = None
    sql = f"""WITH opp AS ({pairs_sql('a', medium='m' if medium else None)})
SELECT x.id, x.label, x.kind, count(DISTINCT o.work) AS stories, min(o.work) AS sample
FROM opp o JOIN entities x ON x.id = o.entity WHERE x.kind = 'character'
GROUP BY ALL ORDER BY stories DESC, x.id LIMIT 15"""
    params = {"a": e["id"], **({"m": medium} if medium else {})}
    rows = store.rows(sql, params)
    if medium and not rows:
        alt, switched = _variant_in_medium(store, e, medium)
        if switched:
            e, params = alt, {**params, "a": alt["id"]}
            rows = store.rows(sql, params)
    team_enemies = [] if medium else store.rows(
        "SELECT dst AS id FROM relations WHERE src = $a AND type = 'enemy' ORDER BY dst LIMIT 20", {"a": e["id"]})
    where = f" in {medium.lower()} stories" if medium else ""
    if not rows and not team_enemies:
        return Result("opponents", True, f"The story appearance data has no opponents recorded for {_name(e)}{where}.",
                      sql=show_sql(sql, params), citations=[_cite(f"Marvel Database: {e['id']}", e["id"])],
                      nodes=[e["id"]], resolved={"entity": e["id"]})
    lines = ([f"{switched} has no opponents in {medium.lower()} stories, so this uses its variant from the same "
              f"disambiguation page with the most {medium.lower()} appearances."] if switched else []) + \
        [f"Most frequent opponents of **{_name(e)}**{where} in the story appearance data:"]
    lines += [f"- **{_name(r)}** - {r['stories']} {'story' if r['stories'] == 1 else 'stories'}" for r in rows[:12]]
    if team_enemies:
        lines.append(f"The team page lists these enemies: {', '.join(t['id'] for t in team_enemies[:12])}.")
    cites = [_cite(f"Marvel Database: {e['id']}", e["id"])] + [_cite(f"Marvel Database: {r['sample']}", r["sample"]) for r in rows[:6]]
    return Result("opponents", True, "\n".join(lines), rows=rows, sql=show_sql(sql, params), citations=cites,
                  nodes=[e["id"]] + [r["id"] for r in rows[:12]], edges=[[e["id"], r["id"]] for r in rows[:12]],
                  resolved={"entity": e["id"]}, note=_alts_note(alts))


def allies(store: Store, name: str) -> Result:
    e, alts = resolve.best(store, name)
    if not e:
        return _missing("allies", "a character or team", name)
    params = {"a": e["id"]}
    sql = f"""WITH side AS ({pairs_sql('a', same_side=True)})
SELECT x.id, x.label, x.kind, count(DISTINCT o.work) AS stories, min(o.work) AS sample
FROM side o JOIN entities x ON x.id = o.entity WHERE x.kind = 'character'
GROUP BY ALL ORDER BY stories DESC, x.id LIMIT 15"""
    rows = store.rows(sql, params)
    listed = store.rows("""SELECT src AS id FROM relations WHERE dst = $a AND type = 'ally'
        UNION SELECT dst FROM relations WHERE src = $a AND type = 'ally' ORDER BY 1 LIMIT 20""", params)
    cites = [_cite(f"Marvel Database: {e['id']}", e["id"])]
    if not rows and not listed:
        return Result("allies", True, f"The story appearance data has nobody recorded on the same side as {_name(e)}.",
                      sql=show_sql(sql, params), citations=cites, nodes=[e["id"]], resolved={"entity": e["id"]})
    lines = [f"Characters who most often appear on the same side as **{_name(e)}** (both featured or supporting "
             f"in the same story, which includes supporting cast as well as team-ups):"]
    lines += [f"- **{_name(r)}** - {r['stories']} {'story' if r['stories'] == 1 else 'stories'}" for r in rows[:12]]
    if listed:
        lines.append(f"Team pages that list them as an ally: {', '.join(t['id'] for t in listed[:12])}.")
    cites += [_cite(f"Marvel Database: {r['sample']}", r["sample"]) for r in rows[:5]]
    return Result("allies", True, "\n".join(lines), rows=rows, sql=show_sql(sql, params), citations=cites,
                  nodes=[e["id"]] + [r["id"] for r in rows[:12]], edges=[[e["id"], r["id"]] for r in rows[:12]],
                  resolved={"entity": e["id"]}, note=_alts_note(alts))


def _pair_stories(store: Store, a: str, b: str, same_side: bool) -> tuple[str, list[dict]]:
    params = {"a": a, "b": b}
    sql = f"""WITH p AS ({pairs_sql('a', same_side=same_side)})
SELECT DISTINCT p.work, w.year, w.medium FROM p LEFT JOIN works w ON w.id = p.work
WHERE p.entity = $b ORDER BY w.year NULLS LAST, p.work"""
    return show_sql(sql, params), store.rows(sql, params)


def first_fight(store: Store, a: str, b: str) -> Result:
    ea, alts_a = resolve.best(store, a)
    eb, alts_b = resolve.best(store, b)
    if not ea or not eb:
        return _missing("first_fight", "a character or team", a if not ea else b)
    sql, rows = _pair_stories(store, ea["id"], eb["id"], same_side=False)
    res = {"a": ea["id"], "b": eb["id"]}
    base_cites = [_cite(f"Marvel Database: {ea['id']}", ea["id"]), _cite(f"Marvel Database: {eb['id']}", eb["id"])]
    if not rows:
        return Result("first_fight", True, f"The story appearance data has no story where {_name(ea)} and {_name(eb)} "
                      f"appear on opposite sides.", sql=sql, citations=base_cites, nodes=[ea["id"], eb["id"]], resolved=res)
    dated = [r for r in rows if r["year"]]
    first_year = dated[0]["year"] if dated else None
    earliest = [r for r in dated if r["year"] == first_year] if dated else rows[:1]
    lines = [f"**{_name(ea)}** and **{_name(eb)}** appear on opposite sides in **{len(rows):,}** "
             f"{'story' if len(rows) == 1 else 'stories'}."]
    if first_year:
        lines.append(f"The earliest by year is {first_year}: " + "; ".join(r["work"] for r in earliest[:4]) +
                     (" (the wiki records only the year, so stories from the same year are not ordered)." if len(earliest) > 1 else "."))
    lines.append("Opposite sides means one is listed as an antagonist and the other as featured or supporting.")
    cites = base_cites + [_cite(f"Marvel Database: {r['work']}", r["work"]) for r in earliest[:4]]
    return Result("first_fight", True, "\n".join(lines), rows=rows[:200], sql=sql, citations=cites,
                  nodes=[ea["id"], eb["id"]], edges=[[ea["id"], eb["id"]]], resolved=res, note=_alts_note(alts_a + alts_b))


REL_WORDS = {"parent": "parent", "child": "child", "sibling": "sibling", "spouse": "spouse", "relative": "relative",
             "clone": "clone", "ancestor": "ancestor", "grandparent": "grandparent", "in_law": "in-law",
             "killed_by": "killed by"}


def relationship(store: Store, a: str, b: str) -> Result:
    """Everything the data records between two entities: family, deaths, shared teams, team ally/enemy
    lists, shared events and sides, stories on opposite and on the same side, shared variant page."""
    ea, alts_a = resolve.best(store, a)
    eb, alts_b = resolve.best(store, b)
    if not ea or not eb:
        return _missing("relationship", "a character or team", a if not ea else b)
    p = {"a": ea["id"], "b": eb["id"]}
    direct_sql = """SELECT src, type, dst, note, evidence, field FROM relations
WHERE (src = $a AND dst = $b) OR (src = $b AND dst = $a) ORDER BY type"""
    teams_sql = f"""SELECT ra.dst AS team, list(DISTINCT ra.type) AS a_roles, list(DISTINCT rb.type) AS b_roles
FROM relations ra JOIN relations rb ON rb.dst = ra.dst
WHERE ra.src = $a AND rb.src = $b AND ra.type IN {MEMBER_TYPES} AND rb.type IN {MEMBER_TYPES} GROUP BY 1 ORDER BY 1"""
    events_sql = """SELECT ra.dst AS event, ra.type AS a_side, rb.type AS b_side FROM relations ra JOIN relations rb ON rb.dst = ra.dst
WHERE ra.src = $a AND rb.src = $b AND ra.type LIKE 'event_%' AND rb.type LIKE 'event_%' ORDER BY 1"""
    direct = store.rows(direct_sql, p)
    teams = store.rows(teams_sql, p)
    events = store.rows(events_sql, p)
    opp_sql, opp = _pair_stories(store, ea["id"], eb["id"], same_side=False)
    _, same = _pair_stories(store, ea["id"], eb["id"], same_side=True)
    group = store.scalar("""SELECT a.variant_group FROM characters a JOIN characters b ON b.variant_group = a.variant_group
        WHERE a.id = $a AND b.id = $b""", p)
    na, nb = _name(ea), _name(eb)
    lines = [f"What the Marvel Database records between **{na}** and **{nb}**:"]
    cites = [_cite(f"Marvel Database: {ea['id']}", ea["id"]), _cite(f"Marvel Database: {eb['id']}", eb["id"])]
    for r in direct:
        who = na if r["src"] == ea["id"] else nb
        other = nb if r["src"] == ea["id"] else na
        note = f" ({r['note'].strip('()')})" if r["note"] else ""
        if r["type"] == "killed_by":
            lines.append(f"- {who}'s page lists {other} under **Killed By**{note}")
        elif r["type"] in REL_WORDS:
            lines.append(f"- {who}'s page lists {other} as a **{REL_WORDS[r['type']]}**{note} ({r['field']} field)")
        elif r["type"] in ("ally", "enemy"):
            lines.append(f"- The {r['evidence']} page lists {other} under **{r['field']}**")
        elif r["type"] in ("member", "former_member", "leader", "former_leader"):
            lines.append(f"- {who} is listed as **{r['type'].replace('_', ' ')}** of {other}")
    if group:
        lines.append(f"- Both are variants on the wiki's **{group}** disambiguation page")
    if teams:
        lines.append(f"- Shared teams ({len(teams)}): " + ", ".join(t["team"] for t in teams[:10]) + (" ..." if len(teams) > 10 else ""))
    side = {"event_protagonist": "protagonist", "event_antagonist": "antagonist", "event_other": "other"}
    for ev in events[:6]:
        rel_word = ("opposite sides" if {ev["a_side"], ev["b_side"]} == {"event_protagonist", "event_antagonist"}
                    else "same side" if ev["a_side"] == ev["b_side"] != "event_other" else "both listed")
        lines.append(f"- {ev['event']}: {na} as {side[ev['a_side']]}, {nb} as {side[ev['b_side']]} ({rel_word})")
    if opp:
        first = next((r for r in opp if r["year"]), opp[0])
        lines.append(f"- Opposite sides in **{len(opp):,}** {'story' if len(opp) == 1 else 'stories'}"
                     + (f", earliest by year {first['year']} ({first['work']})" if first["year"] else f" (e.g. {first['work']})"))
        cites.append(_cite(f"Marvel Database: {first['work']}", first["work"]))
    if same:
        first = next((r for r in same if r["year"]), same[0])
        lines.append(f"- Same side (both featured or supporting) in **{len(same):,}** {'story' if len(same) == 1 else 'stories'}"
                     + (f", earliest by year {first['year']} ({first['work']})" if first["year"] else ""))
        cites.append(_cite(f"Marvel Database: {first['work']}", first["work"]))
    if len(lines) == 1:
        lines = [f"The data records no family link, shared team, event or shared story between {na} and {nb}."]
    elif opp or same:
        verdict = ("mostly as opponents" if len(opp) > len(same) else "mostly on the same side" if len(same) > len(opp)
                   else "as often opposed as on the same side")
        lines.append(f"By story roles they appear {verdict}.")
    rows = ([{"kind": "relation", **r} for r in direct] + [{"kind": "team", **t} for t in teams] +
            [{"kind": "event", **e} for e in events] +
            [{"kind": "opposed", "stories": len(opp)}, {"kind": "same_side", "stories": len(same)}])
    sql = "\n\n".join([show_sql(direct_sql, p), show_sql(teams_sql, p), show_sql(events_sql, p), opp_sql,
                       "-- plus the same query with both sides featured/supporting"])
    for t in teams[:3]:
        cites.append(_cite(f"Marvel Database: {t['team']}", t["team"]))
    kind_edge = [[ea["id"], eb["id"]]]
    return Result("relationship", True, "\n".join(lines), rows=rows, sql=sql, citations=cites[:12],
                  nodes=[ea["id"], eb["id"]] + [t["team"] for t in teams[:8]],
                  edges=kind_edge + [[ea["id"], t["team"]] for t in teams[:8]] + [[eb["id"], t["team"]] for t in teams[:8]],
                  resolved={"a": ea["id"], "b": eb["id"]}, note=_alts_note(alts_a + alts_b))


def deaths(store: Store, name: str, direction: str = "victim") -> Result:
    """direction=victim: who killed `name` (its KilledBy field); direction=killer: whose pages list `name` as killer."""
    e, alts = resolve.best(store, name)
    if not e:
        return _missing("deaths", "a character", name)
    p = {"id": e["id"]}
    cites = [_cite(f"Marvel Database: {e['id']}", e["id"])]
    if direction == "killer":
        sql = """SELECT r.src AS id, x.label, x.kind, x.reality, r.note, coalesce(ac.present, 0) AS appearances
FROM relations r JOIN entities x ON x.id = r.src LEFT JOIN appearance_counts ac ON ac.entity = r.src
WHERE r.dst = $id AND r.type = 'killed_by' ORDER BY appearances DESC, r.src"""
        rows = store.rows(sql, p)
        if not rows:
            return Result("deaths", True, f"No character page lists {_name(e)} in its Killed By field.",
                          sql=show_sql(sql, p), citations=cites, nodes=[e["id"]], resolved={"entity": e["id"]})
        lines = [f"**{len(rows):,}** character pages list **{_name(e)}** in their Killed By field:"]
        lines += [f"- {_name(r)}" + (f" - {r['note']}" if r["note"] else "") for r in rows[:25]]
        if len(rows) > 25:
            lines.append(f"...and {len(rows) - 25} more.")
        lines.append("Many characters on the wiki have died and returned; this lists what each page records.")
        cites += [_cite(f"Marvel Database: {r['id']}", r["id"]) for r in rows[:6]]
        return Result("deaths", True, "\n".join(lines), rows=rows, sql=show_sql(sql, p), citations=cites,
                      nodes=[e["id"]] + [r["id"] for r in rows[:20]], edges=[[e["id"], r["id"]] for r in rows[:20]],
                      resolved={"entity": e["id"]}, note=_alts_note(alts))
    sql = """SELECT c.id, c.death, c.cause_of_death, r.dst AS killer, x.label AS killer_label, r.note
FROM characters c LEFT JOIN relations r ON r.src = c.id AND r.type = 'killed_by' LEFT JOIN entities x ON x.id = r.dst
WHERE c.id = $id ORDER BY r.dst"""
    rows = store.rows(sql, p)
    if not rows or not (rows[0]["death"] or rows[0]["cause_of_death"] or rows[0]["killer"]):
        return Result("deaths", True, f"The wiki page for {_name(e)} records no death.", sql=show_sql(sql, p),
                      citations=cites, nodes=[e["id"]], resolved={"entity": e["id"]}, note=_alts_note(alts))
    r0 = rows[0]
    lines = [f"Death recorded on the wiki page for **{_name(e)}**:"]
    if r0["death"]:
        lines.append(f"- Died in: {r0['death']}")
    if r0["cause_of_death"]:
        lines.append(f"- Cause: {r0['cause_of_death']}")
    killers = [r for r in rows if r["killer"]]
    if killers:
        lines.append("- Killed by: " + ", ".join(_name({"id": r["killer"], "label": r["killer_label"]}) +
                                                 (f" ({r['note']})" if r["note"] else "") for r in killers))
    lines.append("Many characters on the wiki have died and returned; this is what the page records.")
    return Result("deaths", True, "\n".join(lines), rows=rows, sql=show_sql(sql, p), citations=cites,
                  nodes=[e["id"]] + [r["killer"] for r in killers], edges=[[e["id"], r["killer"]] for r in killers],
                  resolved={"entity": e["id"]}, note=_alts_note(alts))


def team_overlap(store: Store, team_a: str, team_b: str) -> Result:
    ta, _ = resolve.best(store, team_a, kinds=("team", "organization"))
    tb, _ = resolve.best(store, team_b, kinds=("team", "organization"))
    if not ta or not tb:
        return _missing("team_overlap", "a team", team_a if not ta else team_b)
    params = {"a": ta["id"], "b": tb["id"]}
    sql = f"""SELECT c.id, coalesce(c.current_alias, c.name) AS label,
       list(DISTINCT ra.type) AS in_a, list(DISTINCT rb.type) AS in_b, coalesce(ac.present, 0) AS appearances
FROM relations ra JOIN relations rb ON rb.src = ra.src
JOIN characters c ON c.id = ra.src LEFT JOIN appearance_counts ac ON ac.entity = c.id
WHERE ra.dst = $a AND rb.dst = $b AND ra.type IN {MEMBER_TYPES} AND rb.type IN {MEMBER_TYPES}
GROUP BY ALL ORDER BY appearances DESC, c.id"""
    rows = store.rows(sql, params)
    shown = show_sql(sql, params)
    cites = [_cite(f"Marvel Database: {ta['id']}", ta["id"]), _cite(f"Marvel Database: {tb['id']}", tb["id"])]
    if not rows:
        return Result("team_overlap", True, f"No character is listed as a member of both {ta['id']} and {tb['id']}.",
                      sql=shown, citations=cites, resolved={"a": ta["id"], "b": tb["id"]})
    lines = [f"**{len(rows):,}** characters are listed (currently or formerly) as members of both **{ta['id']}** and "
             f"**{tb['id']}**, by appearances:"]
    lines += [f"- {_name(r)}" for r in rows[:25]]
    if len(rows) > 25:
        lines.append(f"...and {len(rows) - 25} more.")
    return Result("team_overlap", True, "\n".join(lines), rows=rows, sql=shown, citations=cites,
                  nodes=[ta["id"], tb["id"]] + [r["id"] for r in rows[:20]],
                  edges=[[r["id"], ta["id"]] for r in rows[:20]] + [[r["id"], tb["id"]] for r in rows[:20]],
                  resolved={"a": ta["id"], "b": tb["id"]})


def team_members(store: Store, team: str, status: str = "all") -> Result:
    t, alts = resolve.best(store, team, kinds=("team", "organization"))
    if not t:
        return _missing("team_members", "a team", team)
    types = {"current": "('member','leader')", "former": "('former_member','former_leader')"}.get(status, MEMBER_TYPES)
    params = {"t": t["id"]}
    sql = f"""SELECT c.id, coalesce(c.current_alias, c.name) AS label, list(DISTINCT r.type) AS roles,
       coalesce(ac.present, 0) AS appearances
FROM relations r JOIN characters c ON c.id = r.src LEFT JOIN appearance_counts ac ON ac.entity = c.id
WHERE r.dst = $t AND r.type IN {types} GROUP BY ALL ORDER BY appearances DESC, c.id"""
    rows = store.rows(sql, params)
    word = {"current": "current", "former": "former"}.get(status, "current and former")
    lines = [f"**{t['id']}** has **{len(rows):,}** {word} members listed on the wiki" + (":" if rows else ".")]
    lines += [f"- {_name(r)}{' - former' if all(x.startswith('former') for x in r['roles']) else ''}" for r in rows[:30]]
    if len(rows) > 30:
        lines.append(f"...and {len(rows) - 30} more.")
    return Result("team_members", True, "\n".join(lines), rows=rows, sql=show_sql(sql, params),
                  citations=[_cite(f"Marvel Database: {t['id']}", t["id"])], nodes=[t["id"]] + [r["id"] for r in rows[:25]],
                  edges=[[r["id"], t["id"]] for r in rows[:25]], resolved={"team": t["id"]}, note=_alts_note(alts))


def variants(store: Store, name: str) -> Result:
    e, alts = resolve.best(store, name, kinds=("character",))
    params = {}
    group = None
    if e:
        group = store.scalar("SELECT variant_group FROM characters WHERE id = $id", {"id": e["id"]})
    if not group:
        group = store.scalar("SELECT id FROM variant_groups WHERE lower(id) = lower($n)", {"n": name.strip()})
    if not group:
        what = f"{_name(e)} is not on any of the wiki's disambiguation pages" if e else f"No character called \"{name}\" was found"
        return Result("variants", True if e else False, f"{what}, so I have no variant list for it.",
                      citations=[_cite(f"Marvel Database: {e['id']}", e["id"])] if e else [], resolved={"entity": e and e["id"]})
    params["g"] = group
    sql = """SELECT c.id, coalesce(c.current_alias, c.name) AS label, c.reality, r.medium, coalesce(ac.present, 0) AS appearances
FROM characters c LEFT JOIN realities r ON r.id = c.reality LEFT JOIN appearance_counts ac ON ac.entity = c.id
WHERE c.variant_group = $g ORDER BY appearances DESC, c.id"""
    rows = store.rows(sql, params)
    vg = store.one("SELECT url, permalink FROM variant_groups WHERE id = $g", params)
    lines = [f"The wiki's **{group}** disambiguation page lists **{len(rows):,}** variants across realities, by appearances:"]
    lines += [f"- {r['label']} - {r['reality']}" + (f" ({r['medium']})" if r["medium"] else "") for r in rows[:30]]
    if len(rows) > 30:
        lines.append(f"...and {len(rows) - 30} more.")
    nodes = [r["id"] for r in rows[:24]]
    return Result("variants", True, "\n".join(lines), rows=rows, sql=show_sql(sql, params),
                  citations=[_cite(f"Marvel Database: {group} (disambiguation)", link=(vg or {}).get("permalink") or url(group))],
                  nodes=nodes, edges=[[nodes[0], n] for n in nodes[1:]], resolved={"group": group})


def relatives(store: Store, name: str, relation: str | None = None) -> Result:
    e, alts = resolve.best(store, name, kinds=("character",))
    if not e:
        return _missing("relatives", "a character", name)
    params = {"id": e["id"]}
    rel = (relation or "").rstrip("s").lower()
    rel = {"parent": "parent", "father": "parent", "mother": "parent", "child": "child", "son": "child",
           "daughter": "child", "children": "child", "sibling": "sibling", "brother": "sibling", "sister": "sibling",
           "spouse": "spouse", "wife": "spouse", "husband": "spouse", "relative": "relative", "clone": "clone"}.get(rel)
    filt = "AND r.type = $rel" if rel else ""
    if rel:
        params["rel"] = rel
    sql = f"""SELECT r.type, r.dst AS id, coalesce(c.current_alias, c.name) AS label, r.note
FROM relations r JOIN characters c ON c.id = r.dst
WHERE r.src = $id AND r.type IN ('parent','child','sibling','spouse','relative','clone','ancestor','grandparent','in_law') {filt}
ORDER BY r.type, r.dst"""
    rows = store.rows(sql, params)
    if not rows:
        return Result("relatives", True, f"The wiki page for {_name(e)} lists no {rel or 'family'} relations.",
                      sql=show_sql(sql, params), citations=[_cite(f"Marvel Database: {e['id']}", e["id"])])
    lines = [f"Family of **{_name(e)}** listed on the wiki:"]
    lines += [f"- {r['type'].replace('_', '-')}: {_name(r)}" + (f" - {r['note']}" if r["note"] else "") for r in rows[:30]]
    return Result("relatives", True, "\n".join(lines), rows=rows, sql=show_sql(sql, params),
                  citations=[_cite(f"Marvel Database: {e['id']}", e["id"])], nodes=[e["id"]] + [r["id"] for r in rows[:20]],
                  edges=[[e["id"], r["id"]] for r in rows[:20]], resolved={"entity": e["id"]}, note=_alts_note(alts))


def creators_of(store: Store, name: str) -> Result:
    e, alts = resolve.best(store, name)
    if not e or e["kind"] == "event":
        return _missing("creators_of", "a character or team", name)
    table = "characters" if e["kind"] == "character" else "teams"
    sql = f"SELECT id, creators, first_appearance FROM {table} WHERE id = $id"
    row = store.one(sql, {"id": e["id"]})
    if not row["creators"]:
        return Result("creators_of", True, f"The wiki page for {_name(e)} does not list its creators.",
                      sql=show_sql(sql, {"id": e["id"]}), citations=[_cite(f"Marvel Database: {e['id']}", e["id"])])
    return Result("creators_of", True, f"**{_name(e)}** was created by **{', '.join(row['creators'])}**"
                  + (f" (first appearance: {row['first_appearance']})." if row["first_appearance"] else "."),
                  rows=[row], sql=show_sql(sql, {"id": e["id"]}), citations=[_cite(f"Marvel Database: {e['id']}", e["id"])],
                  nodes=[e["id"]], resolved={"entity": e["id"]}, note=_alts_note(alts))


def created_by(store: Store, creator: str) -> Result:
    params = {"c": creator.strip()}
    sql = """SELECT c.id, coalesce(c.current_alias, c.name) AS label, c.first_appearance, coalesce(ac.present, 0) AS appearances
FROM characters c LEFT JOIN appearance_counts ac ON ac.entity = c.id
WHERE list_contains(list_transform(c.creators, x -> lower(x)), lower($c))
ORDER BY appearances DESC, c.id LIMIT 40"""
    rows = store.rows(sql, params)
    total = store.scalar("SELECT count(*) FROM characters WHERE list_contains(list_transform(creators, x -> lower(x)), lower($c))", params)
    if not rows:
        return Result("created_by", True, f"No character page lists \"{creator}\" as a creator.", sql=show_sql(sql, params))
    lines = [f"**{total:,}** character pages list **{creator}** as a creator. Most frequently appearing:"]
    lines += [f"- {_name(r)}" for r in rows[:20]]
    return Result("created_by", True, "\n".join(lines), rows=rows, sql=show_sql(sql, params),
                  citations=[_cite(f"Marvel Database: {creator}", creator)] + [_cite(f"Marvel Database: {r['id']}", r["id"]) for r in rows[:5]],
                  nodes=[r["id"] for r in rows[:15]])


def event_sides(store: Store, event: str) -> Result:
    e, alts = resolve.best(store, event, kinds=("event",))
    if not e:
        return _missing("event_sides", "an event", event)
    params = {"e": e["id"]}
    sql = """SELECT r.type, r.src AS id, x.label FROM relations r JOIN entities x ON x.id = r.src
WHERE r.dst = $e AND r.type IN ('event_protagonist','event_antagonist','event_other') ORDER BY r.type, r.src"""
    rows = store.rows(sql, params)
    side = {"event_protagonist": "Protagonists", "event_antagonist": "Antagonists", "event_other": "Others"}
    lines = [f"Sides in **{e['id']}** as listed on its event page:"]
    for t in ("event_protagonist", "event_antagonist", "event_other"):
        names = [f"{r['label']}" for r in rows if r["type"] == t]
        if names:
            lines.append(f"- {side[t]}: {', '.join(names[:25])}" + (f" and {len(names) - 25} more" if len(names) > 25 else ""))
    if len(lines) == 1:
        lines = [f"The event page for {e['id']} lists no protagonists or antagonists."]
    return Result("event_sides", True, "\n".join(lines), rows=rows, sql=show_sql(sql, params),
                  citations=[_cite(f"Marvel Database: {e['id']}", e["id"])], nodes=[e["id"]] + [r["id"] for r in rows[:25]],
                  edges=[[r["id"], e["id"]] for r in rows[:25]], resolved={"event": e["id"]}, note=_alts_note(alts))


ROLE_LABEL = {"featured": "Featured", "supporting": "Supporting", "antagonist": "Antagonists", "other": "Other characters"}


def who_appears(store: Store, work: str, role: str | None = None) -> Result:
    """Characters listed on a story page (comic issue, episode, film, game, novel) by role.
    The work is matched by exact page title, or exact title without a '(film)'-style qualifier."""
    w = work.strip().strip("'\"?").lower()
    sql_w = """SELECT id, kind, year, medium, (SELECT count(*) FROM appearances a WHERE a.work = w.id) AS n FROM works w
WHERE lower(id) = $w OR lower(regexp_replace(id, '\\s*\\([^)]*\\)$', '')) = $w ORDER BY lower(id) = $w DESC, n DESC LIMIT 3"""
    found = store.rows(sql_w, {"w": w})
    if not found and resolve.best(store, work, kinds=("team", "organization"))[0]:
        return team_members(store, work)  # "who is in the X-Men" asks about a team, not a story
    if not found:
        return Result("who_appears", False, f"I couldn't find a story page titled \"{work}\" (comic issue, episode, film, "
                      "game or novel), so I can't list who appears in it.", sql=show_sql(sql_w, {"w": w}), note="unresolved name")
    wk = found[0]
    role = {"villains": "antagonist", "villain": "antagonist", "antagonists": "antagonist", "heroes": "featured"}.get(
        (role or "").lower(), role if role in ROLE_LABEL else None)
    params = {"w": wk["id"], **({"r": role} if role else {})}
    sql = f"""SELECT a.role, a.entity AS id, x.label, x.kind, x.reality, a.flags, a.story
FROM appearances a JOIN entities x ON x.id = a.entity
WHERE a.work = $w {"AND a.role = $r" if role else ""}
ORDER BY CASE a.role WHEN 'featured' THEN 0 WHEN 'supporting' THEN 1 WHEN 'antagonist' THEN 2 ELSE 3 END, a.story, a.entity"""
    rows = store.rows(sql, params)
    head = f"**{wk['id']}**" + (f" ({wk['medium'].lower() if wk['medium'] else wk['kind']}, {wk['year']})" if wk["year"] else "")
    if not rows:
        return Result("who_appears", True, f"The page for {head} lists no {ROLE_LABEL.get(role, 'characters').lower()} "
                      "that are in the index.", sql=show_sql(sql, params), citations=[_cite(f"Marvel Database: {wk['id']}", wk["id"])])
    lines = [f"Characters listed on the wiki page for {head}:"]
    for r_ in ("featured", "supporting", "antagonist", "other"):
        names = list(dict.fromkeys(_name(r) + (" (mentioned/not present)" if set(r["flags"] or []) & set(NOT_PRESENT_FLAGS) else "")
                                   for r in rows if r["role"] == r_))
        if names:
            lines.append(f"- {ROLE_LABEL[r_]}: " + ", ".join(names[:25]) + (f" and {len(names) - 25} more" if len(names) > 25 else ""))
    return Result("who_appears", True, "\n".join(lines), rows=rows, sql=show_sql(sql, params),
                  citations=[_cite(f"Marvel Database: {wk['id']}", wk["id"])],
                  nodes=list(dict.fromkeys(r["id"] for r in rows))[:30], resolved={"work": wk["id"]})


TOOLS = {
    "reality_info": (reality_info, ["reality"], "Facts about one reality, dimension or realm (e.g. Earth-616)."),
    "count_realities": (count_realities, ["medium?", "kind?"],
                        "Count realities. medium: Comics|Film|Television|Animation|Games|Prose|Other media; "
                        "kind: numbered|temporary|named|variant_suffix|dimension|realm."),
    "entity_info": (entity_info, ["name"], "Summary of a character, team or event."),
    "first_appearance": (first_appearance, ["name"], "When/where a character, team, event or reality first appeared."),
    "fought_both": (fought_both, ["a", "b"], "Characters who opposed both a and b in the same stories."),
    "opponents": (opponents, ["name", "medium?"],
                  "Most frequent opponents (enemies, rivals, villains) of a character or team; medium: "
                  "Comics|Film|Television|Animation|Games|Prose to limit to that medium."),
    "allies": (allies, ["name"], "Characters most often on the same side as a character (team-ups, supporting cast)."),
    "relationship": (relationship, ["a", "b"],
                     "How two characters/teams are connected: family, deaths, shared teams, events, how often they "
                     "fought or teamed up. Use for 'are X and Y enemies', 'how are X and Y related', 'X vs Y'."),
    "first_fight": (first_fight, ["a", "b"], "When a first fought b (earliest story on opposite sides) and how many times."),
    "deaths": (deaths, ["name", "direction?"],
               "Deaths from the wiki's Killed By fields. direction=victim (default): who killed name and how; "
               "direction=killer: who name has killed."),
    "who_appears": (who_appears, ["work", "role?"],
                    "Characters listed in one story page (comic issue like 'Fantastic Four Vol 1 48', episode, film like "
                    "'Avengers: Endgame', game, novel); role: featured|supporting|antagonist|other."),
    "origin": (origin, ["name"], "Who a character is and their origin: origin, birthplace, powers, origin story, debut."),
    "team_overlap": (team_overlap, ["team_a", "team_b"], "Characters who were members of both teams."),
    "team_members": (team_members, ["team", "status?"], "Members of a team; status: current|former|all."),
    "variants": (variants, ["name"], "Every variant of a character across realities."),
    "relatives": (relatives, ["name", "relation?"], "Family of a character; relation: parent|child|sibling|spouse|relative|clone."),
    "creators_of": (creators_of, ["name"], "Who created a character or team."),
    "created_by": (created_by, ["creator"], "Characters created by a person (e.g. Jack Kirby)."),
    "event_sides": (event_sides, ["event"], "Protagonists and antagonists of an event (e.g. Infinity Gauntlet)."),
}


def run(store: Store, tool: str, args: dict) -> Result:
    fn, params, _ = TOOLS[tool]
    allowed = {p.rstrip("?") for p in params}
    clean = {k: v for k, v in args.items() if k in allowed and v not in (None, "")}
    missing = [p for p in params if not p.endswith("?") and p not in clean]
    if missing:
        raise ValueError(f"{tool} needs {', '.join(missing)}")
    return fn(store, **clean)
