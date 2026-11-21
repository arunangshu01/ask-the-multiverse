"""Cleaned tables -> Parquet + a read-only DuckDB serving file, with quality checks.

Layout under data/:
  runs/<run_id>/cache/        raw API responses (gzip JSON), the raw snapshot
  runs/<run_id>/clean/*.parquet
  runs/<run_id>/report.json   counts + quality checks
  serve/multiverse-<run_id>.duckdb and serve/latest.json (pointer read by the API)
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import asdict
from pathlib import Path

import duckdb

from ingest.realities import Result

log = logging.getLogger("ingest.build")

# Well-known realities whose medium must not regress (also unit-tested).
GOLDEN_MEDIUM = {
    "Earth-616": "Comics", "Earth-199999": "Film", "Earth-92131": "Animation", "Earth-1048": "Games",
    "Earth-838": "Film", "Earth-10005": "Film", "Earth-26496": "Animation", "Earth-1610": "Comics",
    "Earth-TRN734": "Film",
}
MAX_DROP = 0.02

SCHEMAS = {
    "realities": {
        "id": "VARCHAR", "page_title": "VARCHAR", "template": "VARCHAR", "kind": "VARCHAR",
        "types": "VARCHAR[]", "status": "VARCHAR", "status_field": "VARCHAR", "needs_number": "BOOLEAN",
        "in_listing": "BOOLEAN", "listing_kind": "VARCHAR", "name": "VARCHAR", "designation": "VARCHAR",
        "aliases": "VARCHAR[]", "creators": "VARCHAR[]", "medium": "VARCHAR", "medium_format": "VARCHAR",
        "medium_source": "VARCHAR", "first_appearance": "VARCHAR", "first_work": "VARCHAR",
        "first_source": "VARCHAR", "first_year": "INTEGER", "year_source": "VARCHAR",
        "description": "VARCHAR", "description_shortened": "BOOLEAN", "description_source": "VARCHAR",
        "listing_note": "VARCHAR", "listing_first": "VARCHAR", "parents": "VARCHAR[]",
        "destroyed_by": "VARCHAR[]", "home_reality": "VARCHAR", "categories": "VARCHAR[]",
        "qid": "VARCHAR", "revid": "BIGINT", "last_edited": "VARCHAR", "bucket_size": "INTEGER",
        "destruction": "VARCHAR", "last_appearance": "VARCHAR",
        "sources": "STRUCT(label VARCHAR, url VARCHAR, permalink VARCHAR)[]",
    },
    "places": {"id": "VARCHAR", "name": "VARCHAR", "dimension": "VARCHAR", "reality": "VARCHAR",
               "first_appearance": "VARCHAR", "url": "VARCHAR", "revid": "BIGINT"},
    "reality_links": {"src": "VARCHAR", "dst": "VARCHAR", "relation": "VARCHAR", "evidence": "VARCHAR"},
    "ingest_issues": {"page": "VARCHAR", "stage": "VARCHAR", "reason": "VARCHAR", "detail": "VARCHAR"},
}


def checks(result: Result, previous: dict | None) -> list[dict]:
    out = []
    by_id = {r["id"]: r for r in result.realities}

    def add(name, ok, detail, level="fail"):
        out.append({"check": name, "status": "pass" if ok else level, "detail": detail})

    ids = [r["id"] for r in result.realities]
    add("unique reality ids", len(ids) == len(set(ids)), f"{len(ids) - len(set(ids))} duplicates")
    no_source = [r["id"] for r in result.realities if not r["sources"]]
    add("every reality has a source link", not no_source, f"{len(no_source)} without: {no_source[:5]}")
    wrong = {k: (by_id.get(k) or {}).get("medium") for k, v in GOLDEN_MEDIUM.items()
             if (by_id.get(k) or {}).get("medium") != v}
    add("golden realities keep their medium", not wrong, json.dumps(wrong))
    listed = result.meta["listing"]["official_rows"] + result.meta["listing"]["trn_rows"]
    in_index = sum(1 for r in result.realities if r["in_listing"])
    redirected = sum(1 for l in result.links if l["relation"] == "redirects_to")
    dup = sum(1 for i in result.issues if i.reason == "duplicate listing entry")
    add("every listing entry is in the index", in_index + redirected + dup >= listed,
        f"{listed} listed, {in_index} indexed, {redirected} redirects, {dup} duplicates")
    unclassified = sum(1 for r in result.realities if r["medium"] == "Unclassified" and r["kind"] != "bucket")
    add("medium unclassified below 5%", unclassified <= 0.05 * len(ids), f"{unclassified} unclassified", "warn")
    if previous:
        for table in ("realities", "places"):
            before, now = previous.get("counts", {}).get(table, 0), len(getattr(result, table))
            add(f"{table} row count did not drop more than {MAX_DROP:.0%}",
                not before or now >= before * (1 - MAX_DROP), f"{before} -> {now}")
    drift = result.meta.get("field_drift", {})
    total = max(1, result.meta.get("infobox_pages", 1))
    common = {k: v for k, v in drift.items() if v > 0.01 * total}
    add("no unexpected infobox fields on more than 1% of pages", not common, json.dumps(common), "warn")
    return out


def _jsonl(path: Path, rows: list[dict], cols: dict) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps({k: r.get(k) for k in cols}, ensure_ascii=False) + "\n")


def build(result: Result, data_dir: Path, run_id: str, started: str) -> dict:
    run_dir = data_dir / "runs" / run_id
    clean = run_dir / "clean"
    clean.mkdir(parents=True, exist_ok=True)
    serve = data_dir / "serve"
    serve.mkdir(parents=True, exist_ok=True)
    latest_path = serve / "latest.json"
    previous = json.loads(latest_path.read_text()) if latest_path.exists() else None

    tables = {"realities": result.realities, "places": result.places, "reality_links": result.links,
              "ingest_issues": [asdict(i) for i in result.issues]}
    results = checks(result, previous)
    counts = {k: len(v) for k, v in tables.items()}
    finished = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    report = {"run_id": run_id, "started": started, "finished": finished, "counts": counts,
              "meta": result.meta, "checks": results}

    db_name = f"multiverse-{run_id}.duckdb"
    db_path = serve / db_name
    db_path.unlink(missing_ok=True)
    con = duckdb.connect(str(db_path))
    try:
        for name, rows in tables.items():
            cols = SCHEMAS[name]
            src = clean / f"{name}.jsonl"
            _jsonl(src, rows, cols)
            col_spec = "{" + ", ".join(f"'{k}': '{v}'" for k, v in cols.items()) + "}"
            con.execute(f"CREATE TABLE {name} AS SELECT * FROM read_json('{src}', format='newline_delimited', "
                        f"columns={col_spec})")
            con.execute(f"COPY {name} TO '{clean / (name + '.parquet')}' (FORMAT parquet, COMPRESSION zstd)")
            src.unlink()
        con.execute("CREATE TABLE sync_runs (run_id VARCHAR, started VARCHAR, finished VARCHAR, report JSON)")
        con.execute("INSERT INTO sync_runs VALUES (?, ?, ?, ?)", [run_id, started, finished, json.dumps(report)])
        con.execute("CHECKPOINT")
    finally:
        con.close()
    (run_dir / "report.json").write_text(json.dumps(report, indent=1))
    failed = [c for c in results if c["status"] == "fail"]
    if failed:
        log.error("quality checks failed; latest.json NOT updated: %s", failed)
        report["published"] = False
        return report
    latest_path.write_text(json.dumps({"db": db_name, "run_id": run_id, "built_at": finished,
                                       "counts": counts}, indent=1))
    report["published"] = True
    return report
