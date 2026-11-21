"""Count every reality/dimension page on the Marvel Database and compare with realities.json."""
import json
import time
import urllib.parse
import urllib.request

API = "https://marvel.fandom.com/api.php"
UA = {"User-Agent": "AskTheMultiversePreview/0.1 (portfolio prototype)"}
ROOTS = ["Category:Realities", "Category:Dimensions"]


def members(cat):
    params = {"action": "query", "list": "categorymembers", "cmtitle": cat, "cmlimit": "500",
              "cmprop": "title|type", "cmnamespace": "0|14", "format": "json"}
    while True:
        url = f"{API}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
            data = json.load(r)
        yield from data["query"]["categorymembers"]
        if "continue" not in data:
            return
        params.update(data["continue"])
        time.sleep(.3)


SKIP = ("Category:Realities by Category",)


def crawl(root, max_depth=3):
    # Only follow "type" categories (Pocket Universes, Unseen Realities, ...). Per-reality categories
    # like "Category:Earth-616" hold that reality's characters, items and locations, so skip them.
    pages, seen, queue = {}, {root}, [(root, 0)]
    while queue:
        cat, depth = queue.pop()
        for m in members(cat):
            t = m["title"]
            if m["type"] == "subcat":
                per_reality = t.startswith("Category:Earth-") and "Realities" not in t
                if t not in seen and depth < max_depth and "/" not in t and t not in SKIP and not per_reality:
                    seen.add(t)
                    queue.append((t, depth + 1))
            elif "/" not in t:
                pages.setdefault(t, cat)
    return pages, seen


def main():
    known = {r["id"] for r in json.load(open("realities.json"))}
    report, union = {}, {}
    for root in ROOTS:
        pages, cats = crawl(root)
        union.update({p: c for p, c in pages.items() if p not in union})
        extra = sorted(p for p in pages if p not in known)
        report[root] = {"pages": len(pages), "categories": len(cats), "not_in_listing": len(extra), "extra": extra}
        print(f"{root}: {len(pages)} pages in {len(cats)} categories; {len(extra)} not in realities.json", flush=True)
    missing = sorted(k for k in known if k not in union)
    print(f"union: {len(union)} pages; listing entries without a category page: {len(missing)}")
    report["listing_without_page"] = missing
    json.dump(report, open("census.json", "w"), indent=1)


if __name__ == "__main__":
    main()
