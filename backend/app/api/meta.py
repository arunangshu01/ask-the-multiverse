"""Health, stats, coverage and credits."""

from __future__ import annotations

import json

from fastapi import APIRouter, Query, Request

from app.settings import MAX_PAGE

router = APIRouter()

LICENCE = {
    "data": "CC BY-SA 3.0 (Unported)",
    "data_url": "https://creativecommons.org/licenses/by-sa/3.0/",
    "code": "MIT",
    "sources": [
        {"name": "Marvel Database on Fandom", "url": "https://marvel.fandom.com/",
         "licence": "CC BY-SA 3.0", "licence_url": "https://marvel.fandom.com/wiki/Marvel_Database:Copyrights",
         "used_for": "realities, dimensions, realms, characters, teams, events, story appearances, relationships, "
                     "profiles, first appearances, creators, descriptions"},
        {"name": "MCU Wiki on Fandom", "url": "https://marvelcinematicuniverse.fandom.com/",
         "licence": "CC BY-SA", "licence_url": "https://www.fandom.com/licensing",
         "used_for": "which films, series, specials and one-shots belong to each MCU phase (Earth-199999 timeline)"},
        {"name": "Wikidata", "url": "https://www.wikidata.org/", "licence": "CC0 1.0",
         "licence_url": "https://creativecommons.org/publicdomain/zero/1.0/",
         "used_for": "cross-links to Marvel Database pages (P6262), animated-film flags via IMDb IDs (P345)"},
    ],
}
KNOWN_GAPS = [
    "The medium comes from each reality's first-appearance page; a reality that later appears mostly in "
    "another medium keeps the medium of its debut unless a reviewed override says otherwise.",
    "Descriptions are taken from the first paragraph of the wiki's History or Overview field and may be shortened.",
    "Listed reality numbers without a wiki page are kept with status 'undocumented'.",
]


GRAPH_GAPS = [
    "'Fought' means two entities appear on opposite sides (Antagonists vs Featured/Supporting) of the same story on "
    "the wiki's issue, episode, film or game pages, or on opposite sides of an event page. Stories whose pages list no "
    "appearances are not counted.",
    "Character pages have no allies/enemies fields; listed allies and enemies come from team pages only.",
    "Variants come only from the wiki's disambiguation pages; characters without one show no variant list.",
    "MCU phases come from the MCU Wiki phase pages. A title is linked to a Marvel Database page when that page's own "
    "'MCU' field points to the same MCU Wiki page, else by exact title (or exact title without a '(film)'-style "
    "qualifier when that page has Earth-199999 characters). Unlinked titles are listed here, not guessed.",
    "Relationship links that point to pages that are not characters, teams or events are counted and dropped "
    "(see 'Relations dropped').",
    "Wikidata links exist for only a few thousand Marvel Database pages.",
]


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/stats")
def stats(request: Request):
    store = request.app.state.store
    group = lambda col: {r["k"]: r["n"] for r in store.rows(  # noqa: E731
        f"SELECT {col} AS k, count(*) AS n FROM realities GROUP BY 1 ORDER BY 2 DESC")}
    types = {r["k"]: r["n"] for r in store.rows(
        "SELECT t AS k, count(*) AS n FROM (SELECT unnest(types) AS t FROM realities) GROUP BY 1 ORDER BY 2 DESC")}
    snap = store.snapshot
    graph = {}
    if store.scalar("SELECT count(*) FROM information_schema.tables WHERE table_name = 'characters'"):
        graph = {t: store.scalar(f"SELECT count(*) FROM {t}") for t in
                 ("characters", "teams", "events", "works", "appearances", "relations", "variant_groups")}
        graph["creators"] = store.scalar("SELECT count(DISTINCT c) FROM (SELECT unnest(creators) AS c FROM characters)")
        graph["by_relation"] = {r["k"]: r["n"] for r in store.rows(
            "SELECT type AS k, count(*) AS n FROM relations GROUP BY 1 ORDER BY 2 DESC")}
    return {
        "graph": graph,
        "total": store.scalar("SELECT count(*) FROM realities"),
        "by_medium": group("medium"), "by_kind": group("kind"), "by_status": group("status"),
        "by_type": types,
        "listed": store.scalar("SELECT count(*) FROM realities WHERE in_listing"),
        "with_page": store.scalar("SELECT count(*) FROM realities WHERE page_title IS NOT NULL"),
        "places": store.scalar("SELECT count(*) FROM places"),
        "wikidata_linked": store.scalar("SELECT count(*) FROM realities WHERE qid IS NOT NULL"),
        "issues": store.scalar("SELECT count(*) FROM ingest_issues"),
        "synced_at": snap.get("built_at"), "run_id": snap.get("run_id"),
    }


@router.get("/coverage")
def coverage(request: Request, stage: str | None = None, reason: str | None = None,
             q: str | None = Query(None, max_length=120),
             offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=MAX_PAGE)):
    store = request.app.state.store
    report = json.loads(store.scalar("SELECT report FROM sync_runs ORDER BY finished DESC LIMIT 1"))
    graph_report = None
    if "realities_report" in report:  # graph build: merge both reports
        graph_report, report = report, report["realities_report"]
        report = {**report, "checks": report.get("checks", []) + graph_report.get("checks", [])}
    issues_table = "(SELECT * FROM ingest_issues UNION ALL SELECT * FROM graph_issues)" if graph_report else "ingest_issues"
    summary = store.rows(f"SELECT stage, reason, count(*) AS n FROM {issues_table} GROUP BY 1, 2 ORDER BY 3 DESC")
    where, params = [], {}
    for key, val in (("stage", stage), ("reason", reason)):
        if val:
            where.append(f"{key} = ${key}")
            params[key] = val
    if q:
        where.append("(page ILIKE $q OR detail ILIKE $q)")
        params["q"] = f"%{q}%"
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    total = store.scalar(f"SELECT count(*) FROM {issues_table} {clause}", params)
    items = store.rows(f"SELECT * FROM {issues_table} {clause} ORDER BY stage, reason, page "
                       f"LIMIT {limit} OFFSET {offset}", params)
    overrides = store.rows("SELECT id, medium, medium_source FROM realities "
                           "WHERE medium_source LIKE 'reviewed override%' ORDER BY id")
    low = store.scalar("SELECT count(*) FROM realities WHERE medium_source LIKE 'keywords%'")
    graph = None
    if graph_report:
        gm = graph_report["meta"]
        graph = {"run_id": graph_report["run_id"], "finished": graph_report["finished"], "counts": graph_report["counts"],
                 "listed": gm.get("listed"), "relations_dropped": gm.get("relations_dropped", []),
                 "appearances_of_non_entities": gm.get("appearances_of_non_entities")}
    return {"run": {k: report.get(k) for k in ("run_id", "started", "finished", "counts", "meta")},
            "graph": graph, "checks": report.get("checks", []), "summary": summary, "total": total, "items": items,
            "overrides": overrides, "keyword_classified": low, "known_gaps": KNOWN_GAPS + (GRAPH_GAPS if graph else [])}


@router.get("/credits")
def credits(request: Request):
    return {**LICENCE, "synced_at": request.app.state.store.snapshot.get("built_at"),
            "disclaimer": ("Fan-made project. Not affiliated with or endorsed by Marvel or Disney. All characters "
                           "and related names are trademarks of their respective owners.")}
