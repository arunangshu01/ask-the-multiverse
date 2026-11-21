"""Record real Marvel Database / Wikidata responses for the golden realities test.

Run from backend/: `.venv/bin/python -m tests.fixtures.make_golden [--run-id m1-full]`.
Uses that run's response cache, so it makes few or no network calls. The fixture
keeps only what the pipeline reads for a handful of well-known pages."""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

from ingest import realities as r
from ingest.client import WikiClient
from ingest.wikidata import Wikidata

OUT = Path(__file__).with_name("golden.json.gz")
LISTED = ["Earth-616", "Earth-199999", "Earth-92131", "Earth-1048", "Earth-838", "Earth-10005", "Earth-26496",
          "Earth-1610", "Earth-65", "Earth-96283", "Earth-TRN734", "Earth-10530", "Earth-000001", "Framework"]
REALITY_TREE = ["Moira-1", "Earth-65B", "Earth-688B", "Abner Jenkins (Earth-TRN566)"]
DIMENSION_TREE = ["Dark Dimension", "Negative Zone", "Limbo (Otherplace)", "Asgard (Realm)", "Mines of Andvari",
                  "Hildebrandt Wood", "Muspelheim", "Inner Planes", "Otherworld"]


class Recorder(r.LiveSource):
    def __init__(self, client, wikidata):
        super().__init__(client, wikidata)
        self.data = {"wikitext": {}, "categories": {}, "pages": {}, "category_size": {}, "animated_imdb": [],
                     "animated_fandom": [], "animated_label": {}, "qids": {}}

    def wikitext(self, title):
        text, meta = super().wikitext(title)
        if title == r.LISTING:
            rows = [x for x in r.parse_listing(text) if x["id"] in LISTED]
            text = "{|\n" + "".join(f"|-\n|[[{x['id']}]]\n|{x['first_raw']}\n|{x['notes_raw']}\n" for x in rows) + "|}\n"
        else:
            rows = [x for x in r.parse_trn(text) if x["id"] in LISTED]
            text = "==Current TRNs==\n" + "".join(f"* [[{x['id']}]] - {x['first_raw']}\n" for x in rows)
        self.data["wikitext"][title] = [text, meta]
        return text, meta

    def category_members(self, category):
        # The real pages, presented as direct members of the root category (in the wiki some
        # sit in subcategories); the subcategory crawl itself is covered by test_listings.
        keep = {"Category:Realities": REALITY_TREE, "Category:Dimensions": DIMENSION_TREE}.get(category, [])
        out = [{"ns": 0, "title": t, "type": "page"} for t in keep]
        self.data["categories"][category] = out
        return out

    def pages(self, titles, props="revisions|categories|templates|info", content=True):
        out = super().pages(titles, props=props, content=content)
        store = self.data["pages"].setdefault(props, {})
        for t, p in out.items():
            store[t] = {k: v for k, v in p.items() if k in ("title", "missing", "revisions", "categories", "templates")}
        return out

    def category_size(self, category):
        self.data["category_size"][category] = n = super().category_size(category)
        return n

    def animated_imdb_ids(self, ids):
        found = super().animated_imdb_ids(ids)
        self.data["animated_imdb"] = sorted(found)
        return found

    def animated_fandom_titles(self, titles):
        found = super().animated_fandom_titles(titles)
        self.data["animated_fandom"] = sorted(found)
        return found

    def animated_by_label(self, films):
        self.data["animated_label"] = found = super().animated_by_label(films)
        return found

    def marvel_fandom_ids(self):
        all_ids = super().marvel_fandom_ids()
        wanted = set(LISTED + REALITY_TREE + DIMENSION_TREE)
        self.data["qids"] = {k: v for k, v in all_ids.items() if k in wanted}
        return self.data["qids"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="m1-full")
    args = ap.parse_args()
    cache = Path(__file__).resolve().parents[2] / "data" / "runs" / args.run_id / "cache"
    client, wd = WikiClient(cache_dir=cache), Wikidata(cache_dir=cache)
    rec = Recorder(client, wd)
    r.run(rec)
    with gzip.open(OUT, "wt", encoding="utf-8") as fh:
        json.dump(rec.data, fh)
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KiB); network calls: {client.calls}")


if __name__ == "__main__":
    main()
