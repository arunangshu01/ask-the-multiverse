"""Post-deploy smoke test: python scripts/smoke.py https://multiverse.example.com [--api-only]

Checks the site shell, /health, /stats (snapshot loaded), search, an entity panel and one
streamed /ask answer with citations. Exits non-zero on the first failure. Stdlib only."""

import json
import sys
import time
import urllib.request

PREFIX = "/multiverse/api/v1"


def get(url: str, data: bytes | None = None, headers: dict | None = None) -> tuple[int, str]:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "multiverse-smoke", **(headers or {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, r.read().decode()


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'ok' if ok else 'FAIL'}] {name}{' - ' + detail if detail else ''}")
    if not ok:
        sys.exit(1)


def main(base: str, api_only: bool) -> None:
    base = base.rstrip("/")
    api = base + PREFIX
    if not api_only:
        status, html = get(base + "/")
        check("site shell", status == 200 and "Ask the Multiverse" in html)
    for attempt in range(10):  # a cold start downloads the snapshot first
        try:
            status, body = get(api + "/stats")
            if status == 200:
                break
        except Exception as exc:  # noqa: BLE001
            body = str(exc)
        time.sleep(6)
    stats = json.loads(body)
    check("stats (snapshot loaded)", stats.get("total", 0) > 5000 and stats.get("graph", {}).get("characters", 0) > 100000,
          f"run {stats.get('run_id')}")
    check("health", json.loads(get(api + "/health")[1]).get("status") == "ok")
    found = json.loads(get(api + "/search?q=thanos&kinds=character&limit=3")[1])
    check("search", found["total"] > 10 and found["items"][0]["id"] == "Thanos (Earth-616)", f"{found['total']} matches")
    ent = json.loads(get(api + "/entities/" + urllib.request.quote("Peter Parker (Earth-616)"))[1])
    check("entity panel", ent.get("first_work") == "Amazing Fantasy Vol 1 15" and ent["sources"][0]["url"])
    _, stream = get(api + "/ask", json.dumps({"question": "Who has fought both Thanos and Galactus?"}).encode(),
                    {"Content-Type": "application/json", "Accept": "text/event-stream"})
    events = [json.loads(line[6:]) for line in stream.splitlines() if line.startswith("data: ")]
    answer = next((e for e in events if e["type"] == "answer"), {})
    cites = next((e for e in events if e["type"] == "citations"), {}).get("items", [])
    check("ask", answer.get("grounded") is True and "Norrin Radd" in json.dumps(events) and len(cites) > 0,
          f"{len(events)} events, {len(cites)} citations")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], "--api-only" in sys.argv)
