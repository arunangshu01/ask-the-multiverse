"""Fetch every page the knowledge graph needs, group by group, into the run's
response cache. Parsing (ingest/graph.py) re-reads the same requests from the
cache, so this stage can be interrupted and resumed with the same --run-id."""

from __future__ import annotations

import logging
from typing import Iterator

from ingest.client import WikiClient

log = logging.getLogger("ingest.graph_fetch")

# group -> (root category, subcategory depth). Order = fetch order (small, high-value first).
GROUPS = {
    "events": ("Category:Events", 2),
    "teams": ("Category:Teams", 0),
    "organizations": ("Category:Organizations", 0),
    "disambiguation": ("Category:Disambiguation Pages", 0),
    "characters": ("Category:Characters", 0),
    "films": ("Category:Feature Films", 0),
    "short_films": ("Category:Short Films", 0),
    "episodes": ("Category:Episodes", 0),
    "video_games": ("Category:Video Games", 0),
    "novels": ("Category:Novels", 0),
    "comics": ("Category:Comics", 0),
}
# Content only: categories would multiply the calls (comic pages carry hundreds).
PROPS = "revisions|info"


def titles(client: WikiClient, group: str) -> list[str]:
    root, depth = GROUPS[group]
    seen_cats, queue, out = {root}, [(root, 0)], {}
    while queue:
        cat, d = queue.pop(0)
        for m in client.category_members(cat, namespace="0|14"):
            if m["ns"] == 14:
                name = m["title"]
                if d < depth and name not in seen_cats and "/" not in name:
                    seen_cats.add(name)
                    queue.append((name, d + 1))
            elif "/" not in m["title"]:
                out.setdefault(m["title"], None)
    return list(out)


def pages(client: WikiClient, group: str) -> Iterator[dict[str, dict]]:
    yield from client.iter_pages(titles(client, group), props=PROPS)


def fetch(client: WikiClient, groups: list[str]) -> dict:
    stats = {}
    for g in groups:
        n = 0
        names = titles(client, g)
        log.info("%s: %d pages to fetch", g, len(names))
        for batch in client.iter_pages(names, props=PROPS):
            n += len(batch)
        stats[g] = {"listed": len(names), "fetched": n}
        log.info("%s done: %s (api calls so far %d)", g, stats[g], client.calls)
    return stats
