"""Run an ingest: `python -m ingest realities [--run-id ID] [--data-dir DIR]`.

Re-running with the same --run-id reuses that run's response cache, so an
interrupted run resumes without repeating API calls."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
from pathlib import Path

from ingest import build, graph_fetch, realities
from ingest.client import WikiClient
from ingest.wikidata import Wikidata

DEFAULT_DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m ingest")
    ap.add_argument("target", choices=["realities", "graph-fetch", "graph"])
    ap.add_argument("--groups", default=",".join(graph_fetch.GROUPS), help="graph-fetch: comma-separated groups")
    ap.add_argument("--realities-run", default=None, help="graph: run id whose realities snapshot to include")
    ap.add_argument("--run-id", default=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between Fandom API calls")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    cache = args.data_dir / "runs" / args.run_id / "cache"
    client = WikiClient(cache_dir=cache, min_interval=args.interval)
    if args.target == "graph":
        if not args.realities_run:
            raise SystemExit("--realities-run is required (the run id of a published realities build)")
        from ingest import graph, graph_build
        g = graph.build_graph(client, args.data_dir / "runs" / args.run_id / "clean")
        report = graph_build.build_graph_db(g, args.data_dir, args.run_id, args.realities_run, started)
        client.close()
        print(json.dumps({k: report[k] for k in ("run_id", "counts", "published")}, indent=1))
        for c in report["checks"]:
            print(f"  [{c['status']:4}] {c['check']}: {c['detail'][:160]}")
        print("relations dropped:", json.dumps(report["meta"]["relations_dropped"][:12]))
        raise SystemExit(0 if report["published"] else 1)
    if args.target == "graph-fetch":
        stats = graph_fetch.fetch(client, [g for g in args.groups.split(",") if g])
        print(json.dumps({"stats": stats, "api_calls": client.calls, "cache_hits": client.cache_hits}, indent=1))
        client.close()
        return
    wd = Wikidata(cache_dir=cache)
    try:
        result = realities.run(realities.LiveSource(client, wd))
    finally:
        client.close()
        wd.close()
    report = build.build(result, args.data_dir, args.run_id, started)
    print(json.dumps({k: report[k] for k in ("run_id", "counts", "published")}, indent=1))
    for c in report["checks"]:
        print(f"  [{c['status']:4}] {c['check']}: {c['detail'][:160]}")
    raise SystemExit(0 if report["published"] else 1)


if __name__ == "__main__":
    main()
