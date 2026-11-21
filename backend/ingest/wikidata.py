"""Wikidata (CC0) via the public SPARQL endpoint, with the same polite client
rules: User-Agent, spacing between queries, retries and an on-disk cache."""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import time
from pathlib import Path

import httpx

from ingest.client import USER_AGENT

log = logging.getLogger("ingest.wikidata")
ENDPOINT = "https://query.wikidata.org/sparql"
ANIMATED_FILM = "Q202866"


class Wikidata:
    def __init__(self, cache_dir: Path | None = None, min_interval: float = 2.0, transport=None):
        self.cache_dir = cache_dir
        self.min_interval = min_interval
        self.calls = 0
        self._last = 0.0
        self._http = httpx.Client(headers={"User-Agent": USER_AGENT,
                                           "Accept": "application/sparql-results+json"},
                                  timeout=120, transport=transport)
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        self._http.close()

    def sparql(self, query: str) -> list[dict]:
        path = None
        if self.cache_dir:
            path = self.cache_dir / f"wd-{hashlib.sha256(query.encode()).hexdigest()}.json.gz"
            if path.exists():
                with gzip.open(path, "rt", encoding="utf-8") as fh:
                    return json.load(fh)
        for attempt in range(6):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            self.calls += 1
            try:
                resp = self._http.post(ENDPOINT, data={"query": query})
                if resp.status_code == 200:
                    rows = [{k: v["value"] for k, v in b.items()}
                            for b in resp.json()["results"]["bindings"]]
                    if path:
                        with gzip.open(path, "wt", encoding="utf-8") as fh:
                            json.dump(rows, fh)
                    return rows
                if resp.status_code not in (429, 500, 502, 503, 504):
                    raise RuntimeError(f"SPARQL HTTP {resp.status_code}: {resp.text[:200]}")
                retry_after = resp.headers.get("Retry-After", "")
                delay = float(retry_after) if retry_after.isdigit() else 2 ** attempt * 5
            except httpx.TransportError as exc:
                delay = 2 ** attempt * 5
                log.warning("SPARQL transport error %r", exc)
            log.warning("SPARQL retry in %.0fs", delay)
            time.sleep(min(delay, 300))
        raise RuntimeError("SPARQL failed after retries")

    def marvel_fandom_ids(self) -> dict[str, str]:
        """Marvel Database page title -> Wikidata QID, from P6262 'marvel:<Page>'."""
        rows = self.sparql('SELECT ?item ?id WHERE { ?item wdt:P6262 ?id . '
                           'FILTER(STRSTARTS(?id, "marvel:")) }')
        out: dict[str, str] = {}
        for r in rows:
            title = r["id"].split(":", 1)[1].replace("_", " ")
            out.setdefault(title, r["item"].rsplit("/", 1)[-1])
        return out

    def animated_fandom_titles(self, titles: list[str]) -> set[str]:
        """Subset of Marvel Database page titles whose Wikidata item (via P6262) is an animated film."""
        found: set[str] = set()
        ids = sorted({"marvel:" + t.replace(" ", "_") for t in titles})
        for i in range(0, len(ids), 150):
            values = " ".join(json.dumps(x) for x in ids[i:i + 150])
            rows = self.sparql(
                f"SELECT DISTINCT ?id WHERE {{ VALUES ?id {{ {values} }} ?f wdt:P6262 ?id . "
                f"?f (wdt:P31|wdt:P136)/wdt:P279* wd:{ANIMATED_FILM} . }}")
            found |= {r["id"].split(":", 1)[1].replace("_", " ") for r in rows}
        return found

    def animated_by_label(self, films: dict[str, tuple[str, int | None]]) -> dict[str, str]:
        """{page title: (English label, release year)} -> {page title: QID} for films that
        Wikidata lists as animated with exactly that English label and a release year
        within one year of the wiki's. Films without a year are never matched."""
        wanted = {t: (lbl, y) for t, (lbl, y) in films.items() if y}
        found: dict[str, str] = {}
        labels = sorted({lbl for lbl, _ in wanted.values()})
        for i in range(0, len(labels), 100):
            values = " ".join(json.dumps(x) + "@en" for x in labels[i:i + 100])
            rows = self.sparql(
                f"SELECT DISTINCT ?f ?label (YEAR(?d) AS ?y) WHERE {{ VALUES ?label {{ {values} }} "
                f"?f rdfs:label ?label ; (wdt:P31|wdt:P136)/wdt:P279* wd:{ANIMATED_FILM} ; wdt:P577 ?d . }}")
            for r in rows:
                for title, (lbl, year) in wanted.items():
                    if lbl == r["label"] and abs(int(r["y"]) - year) <= 1:
                        found[title] = r["f"].rsplit("/", 1)[-1]
        return found

    def animated_imdb_ids(self, imdb_ids: list[str]) -> set[str]:
        """Subset of IMDb IDs whose Wikidata item is an animated film (instance or genre)."""
        found: set[str] = set()
        ids = sorted({i for i in imdb_ids if i.startswith("tt")})
        for i in range(0, len(ids), 200):
            values = " ".join(f'"{x}"' for x in ids[i:i + 200])
            rows = self.sparql(
                f"SELECT DISTINCT ?imdb WHERE {{ VALUES ?imdb {{ {values} }} ?f wdt:P345 ?imdb . "
                f"?f (wdt:P31|wdt:P136)/wdt:P279* wd:{ANIMATED_FILM} . }}")
            found |= {r["imdb"] for r in rows}
        return found
