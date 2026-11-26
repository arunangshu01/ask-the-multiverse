"""Characters, teams, events, search and the connections graph."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

import duckdb

from app.qa.tools import MEMBER_TYPES, NOT_PRESENT, pairs_sql, url

router = APIRouter()

FAMILY = "('parent','child','sibling','spouse','relative','clone','ancestor','grandparent','in_law')"
EDGE_KIND = {"member": "team", "former_member": "team", "leader": "team", "former_leader": "team", "ally": "ally",
             "enemy": "enemy", "event_protagonist": "event", "event_antagonist": "event", "event_other": "event"}


def _store(request: Request):
    return request.app.state.store


ENTITY_KINDS = ("character", "team", "organization", "event")


@router.get("/search")
def search(request: Request, q: str = Query(min_length=2, max_length=80), limit: int = Query(12, ge=1, le=100),
           offset: int = Query(0, ge=0), kinds: str | None = Query(None, max_length=60)):
    """Search across every reality: characters, teams, events (by page title, name, codename or
    alias) and, on the first page when no kinds filter is given, realities. `total` counts every match."""
    store = _store(request)
    like = f"%{q.lower()}%"
    want = [k for k in (kinds or "").split(",") if k in ENTITY_KINDS] or list(ENTITY_KINDS)
    p = {"l": like, "q": q.lower(), "k": want}
    # direct matches (page title or display name) rank above matches found only through an alias
    hits = """WITH hits AS (SELECT id, max(direct) AS direct FROM (
            SELECT id, 1 AS direct FROM entities WHERE lower(id) LIKE $l OR lower(label) LIKE $l
            UNION ALL SELECT entity, 0 FROM names WHERE name LIKE $l AND kind IN ('character','team','organization','event'))
            GROUP BY id)"""
    total = store.scalar(f"{hits} SELECT count(*) FROM hits h JOIN entities e ON e.id = h.id WHERE list_contains($k, e.kind)",
                         {"l": like, "k": want})
    ents = store.rows(f"""{hits}
        SELECT e.id, e.kind, e.label, e.reality, coalesce(c.present, 0) AS appearances, h.direct = 0 AS via_alias
        FROM hits h JOIN entities e ON e.id = h.id LEFT JOIN appearance_counts c ON c.entity = e.id
        WHERE list_contains($k, e.kind)
        ORDER BY h.direct DESC, (1 + appearances) * CASE WHEN lower(e.label) = $q THEN 4
                 WHEN lower(e.label) LIKE $q || '%' OR lower(e.id) LIKE $q || '%' THEN 2 ELSE 1 END DESC, e.id
        LIMIT {limit} OFFSET {offset}""", p)
    reals = [] if kinds or offset else store.rows("""SELECT id, 'reality' AS kind, coalesce(name, id) AS label,
        NULL AS reality, 0 AS appearances FROM realities WHERE lower(id) LIKE $l OR lower(coalesce(name, '')) LIKE $l
        ORDER BY length(id) LIMIT 6""", {"l": like})
    return {"items": ents + reals, "total": total, "offset": offset}


@router.get("/characters")
def list_characters(request: Request, reality: str | None = None, team: str | None = None,
                    q: str | None = Query(None, max_length=80), offset: int = Query(0, ge=0),
                    limit: int = Query(40, ge=1, le=200)):
    store = _store(request)
    where, params = [], {}
    if reality:
        where.append("c.reality = $r"); params["r"] = reality
    if q:
        where.append("(lower(c.id) LIKE $q OR lower(coalesce(c.current_alias, '')) LIKE $q)"); params["q"] = f"%{q.lower()}%"
    if team:
        where.append(f"c.id IN (SELECT src FROM relations WHERE dst = $t AND type IN {MEMBER_TYPES})"); params["t"] = team
    clause = "WHERE " + " AND ".join(where) if where else ""
    total = store.scalar(f"SELECT count(*) FROM characters c {clause}", params)
    items = store.rows(f"""SELECT c.id, coalesce(c.current_alias, c.name) AS label, c.name, c.reality, c.first_appearance,
        coalesce(a.present, 0) AS appearances FROM characters c LEFT JOIN appearance_counts a ON a.entity = c.id
        {clause} ORDER BY appearances DESC, c.id LIMIT {limit} OFFSET {offset}""", params)
    return {"total": total, "items": items}


@router.get("/entities/{eid:path}")
def entity(request: Request, eid: str):
    """Full panel data for a character, team or event, with every relation's source."""
    store = _store(request)
    e = store.one("SELECT * FROM entities WHERE id = $id", {"id": eid})
    if not e:
        raise HTTPException(404, f"{eid} is not in the index")
    table = {"character": "characters", "team": "teams", "organization": "teams", "event": "events"}[e["kind"]]
    row = store.one(f"SELECT * FROM {table} WHERE id = $id", {"id": eid})
    counts = store.one("SELECT works, present FROM appearance_counts WHERE entity = $id", {"id": eid}) or {}
    rel = lambda sql: store.rows(sql, {"id": eid})  # noqa: E731
    out = {"kind": e["kind"], **row, "appearances": counts.get("present", 0), "appearances_all": counts.get("works", 0)}
    if e["kind"] == "character":
        out["teams"] = rel(f"""SELECT r.dst AS id, t.name AS label, list(DISTINCT r.type) AS roles, any_value(r.evidence) AS evidence
            FROM relations r JOIN teams t ON t.id = r.dst WHERE r.src = $id AND r.type IN {MEMBER_TYPES}
            GROUP BY ALL ORDER BY bool_or(r.type IN ('member','leader')) DESC, r.dst""")
        out["family"] = rel(f"""SELECT r.type, r.dst AS id, coalesce(c.current_alias, c.name) AS label, r.note
            FROM relations r JOIN characters c ON c.id = r.dst WHERE r.src = $id AND r.type IN {FAMILY} ORDER BY r.type, r.dst""")
        out["events"] = rel("""SELECT r.dst AS id, r.type FROM relations r WHERE r.src = $id AND r.type LIKE 'event_%' ORDER BY r.dst LIMIT 40""")
        out["variants"] = rel("""SELECT c.id, coalesce(c.current_alias, c.name) AS label, c.reality FROM characters c
            LEFT JOIN appearance_counts a ON a.entity = c.id
            WHERE c.variant_group = (SELECT variant_group FROM characters WHERE id = $id) AND c.id <> $id
            ORDER BY coalesce(a.present, 0) DESC, c.id LIMIT 60""")
        out["variants_total"] = store.scalar("""SELECT count(*) - 1 FROM characters WHERE variant_group =
            (SELECT variant_group FROM characters WHERE id = $id)""", {"id": eid}) or 0
        out["first_work_year"] = store.scalar("SELECT year FROM works WHERE id = $w", {"w": row.get("first_work") or ""})
        for key, same in (("rivals", False), ("alongside", True)):
            out[key] = store.rows(f"""WITH p AS ({pairs_sql('a', same_side=same)})
                SELECT x.id, x.label, x.reality, count(DISTINCT p.work) AS stories FROM p JOIN entities x ON x.id = p.entity
                WHERE x.kind = 'character' GROUP BY ALL ORDER BY stories DESC, x.id LIMIT 12""", {"a": eid})
        out["killed_by"] = rel("""SELECT r.dst AS id, x.label, r.note FROM relations r JOIN entities x ON x.id = r.dst
            WHERE r.src = $id AND r.type = 'killed_by' ORDER BY r.dst""")
        out["killed"] = rel("""SELECT r.src AS id, x.label, r.note FROM relations r JOIN entities x ON x.id = r.src
            WHERE r.dst = $id AND r.type = 'killed_by' ORDER BY r.src LIMIT 40""")
    elif e["kind"] in ("team", "organization"):
        out["members"] = rel(f"""SELECT r.src AS id, coalesce(c.current_alias, c.name) AS label, list(DISTINCT r.type) AS roles
            FROM relations r JOIN characters c ON c.id = r.src LEFT JOIN appearance_counts a ON a.entity = c.id
            WHERE r.dst = $id AND r.type IN {MEMBER_TYPES} GROUP BY ALL ORDER BY max(coalesce(a.present, 0)) DESC LIMIT 80""")
        out["members_total"] = store.scalar(f"SELECT count(DISTINCT src) FROM relations WHERE dst = $id AND type IN {MEMBER_TYPES}", {"id": eid})
        out["allies"] = rel("SELECT dst AS id FROM relations WHERE src = $id AND type = 'ally' ORDER BY dst LIMIT 60")
        out["enemies"] = rel("SELECT dst AS id FROM relations WHERE src = $id AND type = 'enemy' ORDER BY dst LIMIT 60")
    else:
        out["sides"] = rel("""SELECT r.type, r.src AS id, x.label FROM relations r JOIN entities x ON x.id = r.src
            WHERE r.dst = $id ORDER BY r.type, r.src""")
    out["sources"] = [{"label": f"Marvel Database: {eid}", "url": row.get("url"), "permalink": row.get("permalink")}]
    return out


@router.get("/timeline/earth-199999")
def mcu_timeline(request: Request):
    """MCU phases and their titles from the MCU Wiki, each linked to its Marvel Database page when
    the title matched exactly (unlinked titles are listed with work = null)."""
    store = _store(request)
    try:
        phases = store.rows('SELECT * FROM mcu_phases ORDER BY "order"')
        entries = store.rows("SELECT * FROM mcu_timeline ORDER BY phase, position")
    except duckdb.CatalogException:
        raise HTTPException(404, "This snapshot has no MCU timeline yet") from None
    for p in phases:
        p["entries"] = [{**e, "work_url": url(e["work"]) if e["work"] else None} for e in entries if e["phase"] == p["phase"]]
    return {"phases": phases, "linked": sum(1 for e in entries if e["work"]), "total": len(entries),
            "sources": [{"label": "MCU Wiki contributors on Fandom (CC BY-SA)", "url": "https://marvelcinematicuniverse.fandom.com"},
                        {"label": "Marvel Database contributors on Fandom (CC BY-SA 3.0)", "url": "https://marvel.fandom.com"}]}


@router.get("/graph/nodes")
def graph_nodes(request: Request, ids: str = Query(max_length=6000)):
    """Labels for up to 60 node ids (separated by '|'), used to draw answer highlights."""
    wanted = [i for i in ids.split("|") if i][:60]
    return {"nodes": _store(request).rows("""SELECT e.id, e.kind, e.label, e.reality, coalesce(a.present, 0) AS appearances
        FROM entities e LEFT JOIN appearance_counts a ON a.entity = e.id WHERE e.id IN (SELECT unnest($ids))""", {"ids": wanted})}


@router.get("/graph/neighbourhood")
def neighbourhood(request: Request, node: str, limit: int = Query(30, ge=5, le=80),
                  types: str = Query("enemy,team,ally,family,variant")):
    """The nearest neighbours of one node (never the whole graph): team links, family, variants,
    listed allies/enemies, and the most frequent story opponents."""
    store = _store(request)
    want = set(types.split(","))
    center = store.one("SELECT id, kind, label, reality FROM entities WHERE id = $id", {"id": node})
    if not center:
        raise HTTPException(404, f"{node} is not in the index")
    edges = []
    per = max(4, limit // 4)
    p = {"id": node}
    if "team" in want:
        for r in store.rows(f"""SELECT CASE WHEN src = $id THEN dst ELSE src END AS other, any_value(type) AS t
                FROM relations WHERE (src = $id OR dst = $id) AND type IN {MEMBER_TYPES} GROUP BY 1
                ORDER BY 1 LIMIT {per * 2}""", p):
            edges.append((r["other"], "team"))
    if "family" in want:
        for r in store.rows(f"SELECT dst AS other FROM relations WHERE src = $id AND type IN {FAMILY} LIMIT {per}", p):
            edges.append((r["other"], "family"))
    if "variant" in want and center["kind"] == "character":
        for r in store.rows(f"""SELECT c.id AS other FROM characters c LEFT JOIN appearance_counts a ON a.entity = c.id
                WHERE c.variant_group = (SELECT variant_group FROM characters WHERE id = $id) AND c.id <> $id
                ORDER BY coalesce(a.present, 0) DESC LIMIT {per}""", p):
            edges.append((r["other"], "variant"))
    if "ally" in want or "enemy" in want:
        for r in store.rows(f"""SELECT CASE WHEN src = $id THEN dst ELSE src END AS other, type FROM relations
                WHERE (src = $id OR dst = $id) AND type IN ('ally','enemy') LIMIT {per * 2}""", p):
            if r["type"] in want:
                edges.append((r["other"], r["type"]))
    if "enemy" in want:
        for r in store.rows(f"""SELECT x.entity AS other, count(DISTINCT x.work) AS n FROM appearances s
                JOIN appearances x ON x.work = s.work AND x.story = s.story AND x.entity <> s.entity
                JOIN characters c ON c.id = x.entity
                WHERE s.entity = $id AND NOT list_has_any(s.flags, {NOT_PRESENT}) AND NOT list_has_any(x.flags, {NOT_PRESENT})
                  AND ((s.role = 'antagonist' AND x.role IN ('featured','supporting'))
                    OR (s.role IN ('featured','supporting') AND x.role = 'antagonist'))
                GROUP BY 1 ORDER BY n DESC LIMIT {per}""", p):
            edges.append((r["other"], "enemy"))
    seen, uniq = set(), []
    for other, kind in edges:
        if other != node and (other, kind) not in seen:
            seen.add((other, kind))
            uniq.append((other, kind))
    uniq = uniq[:limit]
    ids = sorted({o for o, _ in uniq} | {node})
    nodes = store.rows("""SELECT e.id, e.kind, e.label, e.reality, coalesce(a.present, 0) AS appearances
        FROM entities e LEFT JOIN appearance_counts a ON a.entity = e.id WHERE e.id IN (SELECT unnest($ids))""", {"ids": ids})
    known = {n["id"] for n in nodes}
    return {"center": node, "nodes": nodes,
            "edges": [{"a": node, "b": o, "kind": k} for o, k in uniq if o in known]}
