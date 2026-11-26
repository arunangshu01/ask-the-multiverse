"""Graph tables -> one DuckDB serving file that also contains the realities
snapshot, plus quality checks. Relationship rows whose endpoints are not
known entities are counted per reason (never silently lost)."""

from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import asdict
from pathlib import Path

import duckdb

from ingest import mcu
from ingest.graph import Graph, write_jsonl

log = logging.getLogger("ingest.graph_build")
MAX_DROP = 0.02

# Facts checked on every build (taken from the wiki pages themselves).
GOLDEN = [
    ("Peter Parker (Earth-616) first appears in Amazing Fantasy Vol 1 15",
     "SELECT count(*) FROM characters WHERE id = 'Peter Parker (Earth-616)' AND first_work = 'Amazing Fantasy Vol 1 15'"),
    ("Anthony Stark (Earth-616) is or was a member of Avengers (Earth-616)",
     "SELECT count(*) FROM relations WHERE src = 'Anthony Stark (Earth-616)' AND dst = 'Avengers (Earth-616)' "
     "AND type IN ('member', 'former_member', 'leader', 'former_leader')"),
    ("Peter Parker (Earth-199999) is in the Peter Parker variant group",
     "SELECT count(*) FROM characters WHERE id = 'Peter Parker (Earth-199999)' AND variant_group = 'Peter Parker'"),
    ("Galan (Earth-616) is an antagonist in Fantastic Four Vol 1 48",
     "SELECT count(*) FROM appearances WHERE work = 'Fantastic Four Vol 1 48' AND entity = 'Galan (Earth-616)' "
     "AND role = 'antagonist'"),
    ("Thanos (Earth-616) is an antagonist of Infinity Gauntlet (Event)",
     "SELECT count(*) FROM relations WHERE src = 'Thanos (Earth-616)' AND dst = 'Infinity Gauntlet (Event)' "
     "AND type = 'event_antagonist'"),
    ("Peter Parker (Earth-616) has an Origin and named powers",
     "SELECT count(*) FROM characters WHERE id = 'Peter Parker (Earth-616)' AND origin ILIKE '%spider%' AND len(powers) > 0"),
]

TABLES = {
    "characters": {"id": "VARCHAR", "name": "VARCHAR", "base_name": "VARCHAR", "current_alias": "VARCHAR",
                   "aliases": "VARCHAR[]", "reality": "VARCHAR", "gender": "VARCHAR", "identity": "VARCHAR",
                   "first_appearance": "VARCHAR", "first_work": "VARCHAR", "creators": "VARCHAR[]",
                   "description": "VARCHAR", "description_shortened": "BOOLEAN", "variant_group": "VARCHAR",
                   "origin": "VARCHAR", "place_of_birth": "VARCHAR", "citizenship": "VARCHAR",
                   "occupation": "VARCHAR[]", "base": "VARCHAR[]", "marital_status": "VARCHAR",
                   "powers": "VARCHAR[]", "abilities": "VARCHAR[]", "death": "VARCHAR", "cause_of_death": "VARCHAR",
                   "origin_story": "VARCHAR",
                   "revid": "BIGINT", "url": "VARCHAR", "permalink": "VARCHAR"},
    "teams": {"id": "VARCHAR", "kind": "VARCHAR", "name": "VARCHAR", "base_name": "VARCHAR", "aliases": "VARCHAR[]",
              "reality": "VARCHAR", "first_appearance": "VARCHAR", "first_work": "VARCHAR", "creators": "VARCHAR[]",
              "description": "VARCHAR", "description_shortened": "BOOLEAN", "revid": "BIGINT", "url": "VARCHAR",
              "permalink": "VARCHAR"},
    "events": {"id": "VARCHAR", "name": "VARCHAR", "reality": "VARCHAR", "first_appearance": "VARCHAR",
               "first_work": "VARCHAR", "last_appearance": "VARCHAR", "description": "VARCHAR", "revid": "BIGINT",
               "url": "VARCHAR", "permalink": "VARCHAR"},
    "works": {"id": "VARCHAR", "kind": "VARCHAR", "medium": "VARCHAR", "format": "VARCHAR", "series": "VARCHAR",
              "mcu": "VARCHAR",
              "year": "INTEGER", "url": "VARCHAR", "revid": "BIGINT"},
    "relations_raw": {"src": "VARCHAR", "dst": "VARCHAR", "type": "VARCHAR", "note": "VARCHAR",
                      "evidence": "VARCHAR", "field": "VARCHAR"},
    "variant_groups": {"id": "VARCHAR", "main": "VARCHAR", "members": "VARCHAR[]", "url": "VARCHAR",
                       "permalink": "VARCHAR"},
    "names": {"name": "VARCHAR", "entity": "VARCHAR", "kind": "VARCHAR", "source": "VARCHAR"},
    "graph_issues": {"page": "VARCHAR", "stage": "VARCHAR", "reason": "VARCHAR", "detail": "VARCHAR"},
}

# Allowed (source kind, target kind) for each relation type.
RELATION_KINDS = {
    "member": ("character|team", "team"), "former_member": ("character|team", "team"),
    "leader": ("character", "team"), "former_leader": ("character", "team"),
    "ally": ("team", "character|team"), "enemy": ("team", "character|team"),
    "event_protagonist": ("character|team", "event"), "event_antagonist": ("character|team", "event"),
    "event_other": ("character|team", "event"), "killed_by": ("character", "character|team"),
    **{t: ("character", "character") for t in ("parent", "child", "sibling", "spouse", "relative", "clone",
                                                 "ancestor", "grandparent", "in_law")},
}


def _many(con, sql: str, rows: list) -> None:
    if rows:
        con.executemany(sql, rows)


def _load(con, name, path, cols):
    spec = "{" + ", ".join(f"'{k}': '{v}'" for k, v in cols.items()) + "}"
    con.execute(f"CREATE TABLE {name} AS SELECT * FROM read_json('{path}', format='newline_delimited', "
                f"columns={spec}, maximum_object_size=104857600)")


def build_graph_db(g: Graph, data_dir: Path, run_id: str, realities_run: str, started: str,
                   mcu_data: tuple[list, list, list] | None = None) -> dict:
    run_dir = data_dir / "runs" / run_id
    clean = run_dir / "clean"
    clean.mkdir(parents=True, exist_ok=True)
    serve = data_dir / "serve"
    serve.mkdir(parents=True, exist_ok=True)
    rows = {"characters": g.characters, "teams": g.teams, "events": g.events, "works": g.works,
            "relations_raw": g.relations, "variant_groups": g.variant_groups, "names": g.names,
            "graph_issues": [asdict(i) for i in g.issues]}
    db_name = f"multiverse-{run_id}.duckdb"
    db_path = serve / db_name
    db_path.unlink(missing_ok=True)
    con = duckdb.connect(str(db_path))
    try:
        rclean = data_dir / "runs" / realities_run / "clean"
        for t in ("realities", "places", "reality_links", "ingest_issues"):
            con.execute(f"CREATE TABLE {t} AS SELECT * FROM read_parquet('{rclean / (t + '.parquet')}')")
        rsnap = duckdb.connect(str(serve / f"multiverse-{realities_run}.duckdb"), read_only=True)
        r_report = rsnap.execute("SELECT report FROM sync_runs ORDER BY finished DESC LIMIT 1").fetchone()[0]
        rsnap.close()
        for name, data in rows.items():
            path = clean / f"{name}.jsonl"
            write_jsonl(path, ({k: r.get(k) for k in TABLES[name]} for r in data))
            _load(con, name, path, TABLES[name])
            path.unlink()
        con.execute("""CREATE TABLE appearances AS SELECT json_extract_string(json, '$[0]') AS work,
            json_extract(json, '$[1]')::INTEGER AS story, json_extract_string(json, '$[2]') AS entity,
            json_extract_string(json, '$[3]') AS role, from_json(json_extract(json, '$[4]'), '["VARCHAR"]') AS flags
            FROM read_json_objects(?, format='newline_delimited')""", [str(clean / "appearances.jsonl")])
        con.execute("""CREATE TABLE entities AS
            SELECT id, 'character' AS kind, coalesce(current_alias, name) AS label, name, reality, url FROM characters
            UNION ALL SELECT id, kind, name, name, reality, url FROM teams
            UNION ALL SELECT id, 'event', name, name, reality, url FROM events""")
        # keep relations whose endpoints are known entities of the allowed kinds; count the rest
        kinds = [(t, s, d) for t, (s, d) in RELATION_KINDS.items()]
        con.execute("CREATE TEMP TABLE rel_kinds (type VARCHAR, src_kinds VARCHAR, dst_kinds VARCHAR)")
        con.executemany("INSERT INTO rel_kinds VALUES (?, ?, ?)", kinds)
        con.execute("""CREATE TABLE relations AS SELECT DISTINCT r.src, r.dst, r.type, r.note, r.evidence, r.field
            FROM relations_raw r JOIN rel_kinds k USING (type)
            JOIN entities s ON s.id = r.src JOIN entities d ON d.id = r.dst
            WHERE list_contains(string_split(k.src_kinds, '|'), CASE WHEN s.kind = 'organization' THEN 'team' ELSE s.kind END)
              AND list_contains(string_split(k.dst_kinds, '|'), CASE WHEN d.kind = 'organization' THEN 'team' ELSE d.kind END)
              AND r.src <> r.dst""")
        dropped = con.execute("""SELECT r.type, CASE WHEN s.id IS NULL THEN 'source is not a known entity'
                WHEN d.id IS NULL THEN 'target is not a character, team or event page' ELSE 'wrong entity kind' END,
                count(*) FROM relations_raw r LEFT JOIN entities s ON s.id = r.src LEFT JOIN entities d ON d.id = r.dst
            WHERE NOT EXISTS (SELECT 1 FROM relations x WHERE x.src = r.src AND x.dst = r.dst AND x.type = r.type)
            GROUP BY 1, 2 ORDER BY 3 DESC""").fetchall()
        con.execute("DROP TABLE relations_raw")
        con.execute("""CREATE TABLE appearance_counts AS SELECT entity, count(DISTINCT work) AS works,
            count(DISTINCT work) FILTER (WHERE NOT list_has_any(flags, ['mentioned','recap','image','vision',
                'fictional','voice','corpse','impersonation','offpanel','narration'])) AS present
            FROM appearances GROUP BY 1""")
        mcu_phases, mcu_entries, mcu_issues = mcu_data or ([], [], [])
        mcu_issues = list(mcu_issues) + mcu.link_works(con, mcu_phases, mcu_entries)
        con.execute("""CREATE TABLE mcu_phases ("order" INTEGER, phase VARCHAR, saga VARCHAR, start_year INTEGER,
            end_year INTEGER, url VARCHAR, permalink VARCHAR)""")
        _many(con, "INSERT INTO mcu_phases VALUES (?, ?, ?, ?, ?, ?, ?)",
                        [[p["order"], p["phase"], p["saga"], p["start_year"], p["end_year"], p["url"], p["permalink"]]
                         for p in mcu_phases])
        cols = ["phase", "position", "kind", "title", "mcu_page", "season", "mcu_url", "work", "work_kind", "year", "match"]
        con.execute("""CREATE TABLE mcu_timeline (phase VARCHAR, position INTEGER, kind VARCHAR, title VARCHAR,
            mcu_page VARCHAR, season INTEGER, mcu_url VARCHAR, work VARCHAR, work_kind VARCHAR, year INTEGER, match VARCHAR)""")
        _many(con, f"INSERT INTO mcu_timeline VALUES ({', '.join('?' * len(cols))})", [[e[c] for c in cols] for e in mcu_entries])
        _many(con, "INSERT INTO graph_issues VALUES (?, ?, ?, ?)", [[i.page, i.stage, i.reason, i.detail] for i in mcu_issues])
        unknown_app = con.execute("""SELECT count(*) FROM appearances a WHERE NOT EXISTS
            (SELECT 1 FROM entities e WHERE e.id = a.entity)""").fetchone()[0]
        counts = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                  for t in ("characters", "teams", "events", "works", "appearances", "relations", "variant_groups",
                            "names", "realities", "places", "mcu_timeline")}
        checks = []
        for label, sql in GOLDEN:
            n = con.execute(sql).fetchone()[0]
            checks.append({"check": label, "status": "pass" if n else "fail", "detail": f"{n} rows"})
        # compared with the snapshot that is live now (the sync job downloads it to published.json)
        live = serve / "published.json"
        if live.exists():
            before = json.loads(live.read_text()).get("counts", {})
            for t in ("characters", "teams", "events", "works", "appearances", "relations"):
                if before.get(t):
                    ok = counts[t] >= before[t] * (1 - MAX_DROP)
                    checks.append({"check": f"{t} row count did not drop more than {MAX_DROP:.0%}",
                                   "status": "pass" if ok else "fail", "detail": f"{before[t]} -> {counts[t]}"})
        if mcu_entries:
            linked = sum(1 for e in mcu_entries if e["work"])
            checks.append({"check": "MCU timeline titles linked to Marvel Database pages (90%+)",
                           "status": "pass" if linked >= 0.9 * len(mcu_entries) else "warn",
                           "detail": f"{linked} of {len(mcu_entries)}"})
        listed = g.meta["listed"]["characters"]
        checks.append({"check": "at least 95% of Category:Characters pages parsed",
                       "status": "pass" if counts["characters"] >= 0.95 * listed else "fail",
                       "detail": f"{counts['characters']} of {listed}"})
        finished = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        report = {"run_id": run_id, "started": started, "finished": finished, "counts": counts,
                  "meta": {**g.meta, "realities_run": realities_run,
                           "relations_dropped": [{"type": t, "reason": r, "n": n} for t, r, n in dropped],
                           "appearances_of_non_entities": unknown_app},
                  "checks": checks, "realities_report": json.loads(r_report)}
        con.execute("CREATE TABLE sync_runs (run_id VARCHAR, started VARCHAR, finished VARCHAR, report JSON)")
        con.execute("INSERT INTO sync_runs VALUES (?, ?, ?, ?)", [run_id, started, finished, json.dumps(report)])
        for t in ("characters", "teams", "events", "works", "relations", "variant_groups", "appearances"):
            con.execute(f"COPY {t} TO '{clean / (t + '.parquet')}' (FORMAT parquet, COMPRESSION zstd)")
        con.execute("CHECKPOINT")
    finally:
        con.close()
    (clean / "appearances.jsonl").unlink(missing_ok=True)
    (run_dir / "report.json").write_text(json.dumps(report, indent=1))
    report["published"] = not any(c["status"] == "fail" for c in checks)
    if report["published"]:
        (serve / "latest.json").write_text(json.dumps({"db": db_name, "run_id": run_id, "built_at": finished,
                                                        "counts": counts, "realities_run": realities_run}, indent=1))
    return report
