"""Polite MediaWiki API client: clear User-Agent, one request at a time with a
minimum interval, retries with backoff (honouring Retry-After), and an on-disk
response cache that makes interrupted runs resumable."""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Iterable, Iterator

import httpx

log = logging.getLogger("ingest.client")

USER_AGENT = ("AskTheMultiverse/1.0 (fan-made, non-commercial; "
              "https://github.com/arunangshu01/ask-the-multiverse; arunangshu01@gmail.com)")
MARVEL_API = "https://marvel.fandom.com/api.php"
MCU_API = "https://marvelcinematicuniverse.fandom.com/api.php"
BATCH = 50  # titles per query for non-bot clients
RETRY_STATUS = {429, 500, 502, 503, 504}


class ApiError(RuntimeError):
    pass


class WikiClient:
    def __init__(self, api_url: str = MARVEL_API, cache_dir: Path | None = None,
                 min_interval: float = 1.0, max_retries: int = 6, transport=None):
        self.api_url = api_url
        self.cache_dir = cache_dir
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.calls = 0
        self.cache_hits = 0
        self._last = 0.0
        self._http = httpx.Client(headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"},
                                  timeout=90, transport=transport)
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        self._http.close()

    def _cache_path(self, params: dict) -> Path | None:
        if not self.cache_dir:
            return None
        key = json.dumps({"api": self.api_url, **params}, sort_keys=True)
        return self.cache_dir / f"{hashlib.sha256(key.encode()).hexdigest()}.json.gz"

    def get(self, **params) -> dict:
        params = {"format": "json", "formatversion": "2", **{k: str(v) for k, v in params.items()}}
        path = self._cache_path(params)
        if path and path.exists():
            self.cache_hits += 1
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                return json.load(fh)
        data = self._fetch(params)
        if path:
            tmp = path.with_suffix(".tmp")
            with gzip.open(tmp, "wt", encoding="utf-8") as fh:
                json.dump(data, fh)
            tmp.replace(path)
        return data

    def _fetch(self, params: dict) -> dict:
        if self.calls and self.calls % 50 == 0:
            log.info("%d API calls so far (%d cache hits)", self.calls, self.cache_hits)
        for attempt in range(self.max_retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            self.calls += 1
            try:
                resp = self._http.get(self.api_url, params=params)
            except httpx.TransportError as exc:
                delay, reason = 2 ** attempt * 2, repr(exc)
            else:
                if resp.status_code == 200:
                    data = resp.json()
                    err = data.get("error")
                    if not err:
                        return data
                    if err.get("code") not in ("maxlag", "ratelimited", "readonly"):
                        raise ApiError(f"{err.get('code')}: {err.get('info')}")
                    delay, reason = 2 ** attempt * 5, err.get("code")
                elif resp.status_code in RETRY_STATUS:
                    retry_after = resp.headers.get("Retry-After", "")
                    delay = float(retry_after) if retry_after.isdigit() else 2 ** attempt * 5
                    reason = f"HTTP {resp.status_code}"
                else:
                    raise ApiError(f"HTTP {resp.status_code} for {params.get('action')}")
            if attempt == self.max_retries:
                raise ApiError(f"giving up after {attempt + 1} attempts: {reason}")
            log.warning("retrying in %.0fs (%s)", delay, reason)
            time.sleep(min(delay, 300))
        raise AssertionError("unreachable")

    # ---------- helpers ----------

    def query_all(self, **params) -> Iterator[dict]:
        """Yield every response of a query, following `continue`."""
        cont: dict = {}
        while True:
            data = self.get(action="query", **params, **cont)
            yield data
            if "continue" not in data:
                return
            cont = data["continue"]

    def wikitext(self, title: str) -> tuple[str, dict]:
        data = self.get(action="parse", page=title, prop="wikitext|revid", redirects=1)
        parse = data["parse"]
        return parse["wikitext"], {"title": parse["title"], "pageid": parse["pageid"],
                                   "revid": parse.get("revid")}

    def category_members(self, category: str, kind: str = "page|subcat",
                         namespace: str = "0|14") -> list[dict]:
        out = []
        for data in self.query_all(list="categorymembers", cmtitle=category, cmtype=kind,
                                   cmnamespace=namespace, cmlimit="max", cmprop="ids|title|type"):
            out += data["query"]["categorymembers"]
        return out

    def pages(self, titles: Iterable[str], props: str = "revisions|categories|templates|info",
              content: bool = True) -> dict[str, dict]:
        """Fetch pages in batches of 50, merging continuation results.

        Returns {requested title: page dict}; redirects and normalisation are
        resolved, and the final title is in page["title"]."""
        result: dict[str, dict] = {}
        for batch in self.iter_pages(titles, props, content):
            result.update(batch)
        return result

    def iter_pages(self, titles: Iterable[str], props: str = "revisions|categories|templates|info",
                   content: bool = True) -> Iterator[dict[str, dict]]:
        """Like pages(), but yields one {requested title: page} dict per batch of 50."""
        titles = list(dict.fromkeys(t for t in titles if t))
        for i in range(0, len(titles), BATCH):
            result: dict[str, dict] = {}
            batch = titles[i:i + BATCH]
            params = {"prop": props, "titles": "|".join(batch), "redirects": 1,
                      "cllimit": "max", "tllimit": "max", "tlnamespace": 4}
            if content and "revisions" in props:
                params.update(rvprop="ids|content|timestamp", rvslots="main")
            merged: dict[str, dict] = {}
            alias: dict[str, str] = {}
            for data in self.query_all(**params):
                q = data.get("query", {})
                for kind in ("normalized", "redirects"):
                    for m in q.get(kind, []):
                        alias[m["from"]] = m["to"]
                for page in q.get("pages", []):
                    cur = merged.setdefault(page["title"], {})
                    for k, v in page.items():
                        if isinstance(v, list) and isinstance(cur.get(k), list):
                            cur[k] = cur[k] + v
                        elif k not in cur or k == "revisions":
                            cur[k] = v
            for t in batch:
                final = t
                for _ in range(5):
                    if final not in alias:
                        break
                    final = alias[final]
                if final in merged:
                    result[t] = merged[final]
            yield result
