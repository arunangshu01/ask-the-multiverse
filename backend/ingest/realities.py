"""Realities, dimensions and realms: listings + category trees -> classified rows.

Every candidate page ends up in exactly one place: `realities` (accepted),
`places` (locations inside a dimension) or `issues` (rejected or not
classifiable, with the reason). Nothing is dropped silently."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

from ingest import media, taxonomy as tx, wikitext as wt
from ingest.client import WikiClient
from ingest.wikidata import Wikidata

log = logging.getLogger("ingest.realities")

WIKI = "https://marvel.fandom.com/wiki/"
LISTING = "Multiverse/Universe Listing"
TRN_LISTING = "List of Temporary Reality Numbers"
UNKNOWN_BUCKET = "Earth-Unknown"
UNKNOWN_CATEGORY = "Unknown Reality/Characters"
OVERRIDES = Path(__file__).with_name("overrides.json")
REALITY_ID = re.compile(r"^(Earth|Moira|Jubilee)-[\w.]+$")
# Infobox fields seen when the ingest was written; new fields are reported as schema drift.
SCHEMA_BASELINE = Path(__file__).with_name("schema_baseline.json")


def load_schema_baseline() -> dict[str, set[str]]:
    if not SCHEMA_BASELINE.exists():
        return {}
    return {k: set(v) for k, v in json.loads(SCHEMA_BASELINE.read_text()).items()}


def dimension_ids(locations: dict[str, tuple[set[str], dict]]) -> dict[str, str]:
    """Which Location Template pages are dimensions or realms, and why:
    'direct'    - listed directly in a dimension-type category (Dimensions, God Realms, Hell...)
    'self'      - its Dimension field names itself (e.g. Negative Zone)
    'container' - another accepted dimension names it as its Dimension (e.g. Inner Planes)
    Everything else is a place inside a dimension."""
    own = {rid: wt.plain(f.get("Dimension", "")) for rid, (_, f) in locations.items()}
    out = {}
    for rid, (cats, _) in locations.items():
        if cats & set(tx.DIMENSION_TYPE_CATEGORIES):
            out[rid] = "direct"
        elif own[rid] == rid:
            out[rid] = "self"
    while True:
        new = {own[r] for r in out if own[r] and own[r] in locations and own[r] not in out}
        if not new:
            return out
        out.update({r: "container" for r in new})


FIELD_DATE = re.compile(r"Category:(?:Comics Released in |Week \d+, )?(?:[A-Z][a-z]+,? )?(1[89]\d\d|20\d\d)\b|"
                        r"\((?:[A-Z][a-z]+ (?:\d{1,2}, )?)?(1[89]\d\d|20\d\d)\)")


def imdb_id(raw: str) -> str:
    """The wiki stores IMDb title IDs without the 'tt' prefix ('4633694'); Wikidata P345 uses 'tt4633694'."""
    value = wt.plain(raw).strip()
    return value if value.startswith("tt") or not value.isdigit() else f"tt{value}"


def field_year(raw: str) -> int | None:
    """A release date written next to the first appearance, e.g. '([[:Category:Week 50, 2003|December, 2003]])'."""
    m = FIELD_DATE.search(raw or "")
    return int(m.group(1) or m.group(2)) if m else None


def page_url(title: str) -> str:
    return WIKI + quote(title.replace(" ", "_"), safe="/:()',!-.")


def permalink(title: str, revid: int | None) -> str | None:
    return f"{page_url(title)}?oldid={revid}" if revid else None


@dataclass
class Issue:
    page: str
    stage: str
    reason: str
    detail: str = ""


@dataclass
class Result:
    realities: list[dict] = field(default_factory=list)
    places: list[dict] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


# ---------------------------------------------------------------- listings

def parse_listing(text: str) -> list[dict]:
    """Rows of the official Multiverse/Universe Listing wikitable."""
    rows = []
    for chunk in text.split("\n|-")[1:]:
        cells, cur = [], None
        for line in chunk.split("\n"):
            if line.startswith("|}"):
                break
            if line.startswith("|") and not line.startswith("|+"):
                if cur is not None:
                    cells.append(cur)
                cur = line[1:]
            elif cur is not None:
                cur += "\n" + line
        if cur is not None:
            cells.append(cur)
        if not cells:
            continue
        m = re.match(r"\s*\[\[([^|\]]+)", cells[0])
        if not m:
            continue
        rows.append({"id": wt._norm(m.group(1)), "first_raw": cells[1].strip() if len(cells) > 1 else "",
                     "notes_raw": "\n".join(cells[2:]).strip(), "kind": "numbered"})
    return rows


def parse_trn(text: str) -> list[dict]:
    """Entries of the 'Current TRNs' section of the Temporary Reality Numbers list."""
    section = text.split("==Current TRNs==", 1)[-1]
    section = re.split(r"\n==[^=]", section, maxsplit=1)[0]
    rows = []
    for line in section.splitlines():
        m = re.match(r"\*\s*\[\[(Earth-TRN[^|\]]+)(?:\|[^\]]*)?\]\]\s*[-:]?\s*(.*)", line.strip())
        if m:
            rows.append({"id": wt._norm(m.group(1)), "first_raw": m.group(2).strip(),
                         "notes_raw": "", "kind": "temporary"})
    return rows


# ---------------------------------------------------------------- category crawl

def crawl(client: WikiClient, root: str, max_depth: int, skip) -> tuple[dict[str, set[str]], set[str]]:
    """Pages under `root` (following subcategories up to max_depth) -> the
    categories they were found in. `skip(category)` prunes subcategories."""
    pages: dict[str, set[str]] = {}
    seen, queue = {root}, [(root, 0)]
    while queue:
        cat, depth = queue.pop(0)
        for m in client.category_members(cat):
            t = m["title"]
            if m["ns"] == 14:
                if t not in seen and depth < max_depth and not skip(t):
                    seen.add(t)
                    queue.append((t, depth + 1))
            elif m["ns"] == 0 and "/" not in t:
                pages.setdefault(t, set()).add(cat.split(":", 1)[1])
    return pages, seen


def _skip_reality_subcat(cat: str) -> bool:
    name = cat.split(":", 1)[1]
    return ("/" in name or name in ("Realities by Category", "Realities by Year of Debut")
            or (REALITY_ID.match(name) is not None and "Realities" not in name))


def _skip_dimension_subcat(cat: str) -> bool:
    name = cat.split(":", 1)[1]
    return "/" in name or name in tx.DIMENSION_NON_PLACE_CATEGORIES


# ---------------------------------------------------------------- helpers

def template_of(page: dict) -> str | None:
    names = [t["title"].split(":", 1)[1].strip() for t in page.get("templates", [])
             if t["title"].endswith(" Template")]
    for group in (tx.REALITY_TEMPLATES, tx.PLACE_TEMPLATES, set(tx.REJECT_TEMPLATES)):
        for n in names:
            if n in group:
                return n
    return names[0] if names else None


def load_overrides() -> dict:
    with OVERRIDES.open() as fh:
        return json.load(fh)


KEYWORDS = [  # last resort only; results are marked medium_source="keywords"
    ("Games", re.compile(r"video ?game|\(game\)|lego marvel|contest of champions|strike force|"
                         r"puzzle quest|ultimate alliance|future fight|marvel rivals|pinball|\brpg\b", re.I)),
    ("Animation", re.compile(r"animat|cartoon|anime\b", re.I)),
    ("Film", re.compile(r"\(film\)|\bmovie\b|motion picture", re.I)),
    ("Television", re.compile(r"\(tv series\)|television|live[- ]action series", re.I)),
    ("Prose", re.compile(r"\bnovel\b|\bprose\b|podcast|audio drama|short story", re.I)),
]


def keyword_medium(*texts: str) -> str | None:
    text = " ".join(t for t in texts if t)
    for name, pat in KEYWORDS:
        if pat.search(text):
            return name
    return None


def _first_paren_year(text: str) -> int | None:
    m = re.search(r"\((1[89]\d\d|20\d\d)\)", text or "")
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------- sources

class LiveSource:
    """Marvel Database API + Wikidata. Tests replace this with recorded pages."""

    def __init__(self, client: WikiClient, wikidata: Wikidata | None):
        self.client, self.wikidata = client, wikidata

    def wikitext(self, title):
        return self.client.wikitext(title)

    def category_members(self, category):
        return self.client.category_members(category)

    def pages(self, titles, props="revisions|categories|templates|info", content=True):
        return self.client.pages(titles, props=props, content=content)

    def category_size(self, category) -> int:
        page = self.client.get(action="query", prop="categoryinfo", titles=category)["query"]["pages"][0]
        return page.get("categoryinfo", {}).get("pages", 0)

    def animated_imdb_ids(self, ids):
        return self.wikidata.animated_imdb_ids(ids) if self.wikidata else set()

    def animated_fandom_titles(self, titles):
        return self.wikidata.animated_fandom_titles(titles) if self.wikidata else set()

    def animated_by_label(self, films):
        return self.wikidata.animated_by_label(films) if self.wikidata else {}

    def marvel_fandom_ids(self):
        return self.wikidata.marvel_fandom_ids() if self.wikidata else {}

    def counters(self) -> dict:
        return {"api_calls": self.client.calls, "cache_hits": self.client.cache_hits,
                "wikidata_calls": self.wikidata.calls if self.wikidata else 0}


# ---------------------------------------------------------------- pipeline

def run(src, overrides: dict | None = None) -> Result:
    res = Result()
    overrides = load_overrides() if overrides is None else overrides
    client = src

    listing_text, listing_meta = client.wikitext(LISTING)
    trn_text, trn_meta = client.wikitext(TRN_LISTING)
    listed = parse_listing(listing_text)
    trn = parse_trn(trn_text)
    res.meta["listing"] = {"official_rows": len(listed), "trn_rows": len(trn),
                           "listing_revid": listing_meta["revid"], "trn_revid": trn_meta["revid"]}
    listing_src = {"numbered": (LISTING, listing_meta["revid"]),
                   "temporary": (TRN_LISTING, trn_meta["revid"])}
    entries: dict[str, dict] = {}
    for row in listed + trn:
        if row["id"] in entries:
            res.issues.append(Issue(row["id"], "listing", "duplicate listing entry",
                                    f"listed again in {row['kind']} list"))
            continue
        entries[row["id"]] = row

    reality_tree, reality_cats = crawl(client, "Category:Realities", 3, _skip_reality_subcat)
    dim_tree, dim_cats = crawl(client, "Category:Dimensions", 3, _skip_dimension_subcat)
    res.meta["categories"] = {"realities_tree_pages": len(reality_tree),
                              "realities_tree_categories": len(reality_cats),
                              "dimensions_tree_pages": len(dim_tree),
                              "dimensions_tree_categories": len(dim_cats)}
    candidates = list(dict.fromkeys([*entries, *reality_tree, *dim_tree]))
    log.info("candidates: %d (listing %d, realities tree %d, dimensions tree %d)",
             len(candidates), len(entries), len(reality_tree), len(dim_tree))

    light = client.pages(candidates, props="templates|info", content=False)
    want, resolved = [], {}
    for title in candidates:
        page = light.get(title)
        if not page or page.get("missing") is not None:
            continue
        resolved[title] = page["title"]
        tmpl = template_of(page)
        if tmpl in tx.REALITY_TEMPLATES or tmpl in tx.PLACE_TEMPLATES:
            want.append(page["title"])
    full = client.pages(list(dict.fromkeys(want)))

    # -------- accept / reject every candidate
    accepted: dict[str, dict] = {}
    for title in candidates:
        page = light.get(title)
        listed_row = entries.get(title)
        if not page or page.get("missing") is not None:
            if listed_row:
                accepted[title] = {"id": title, "page": None, "listing": listed_row}
            else:
                res.issues.append(Issue(title, "fetch", "page missing", "category member not found"))
            continue
        final = page["title"]
        if final != title:
            if listed_row:
                res.links.append({"src": title, "dst": final, "relation": "redirects_to",
                                  "evidence": f"{page_url(title)} redirects to {final}"})
            if final in accepted or final in entries:
                continue
        tmpl = template_of(page)
        if tmpl in tx.REALITY_TEMPLATES or tmpl in tx.PLACE_TEMPLATES:
            if final not in accepted:
                accepted[final] = {"id": final, "page": full.get(final), "template": tmpl,
                                   "listing": entries.get(final) or listed_row}
        elif listed_row:
            accepted[final] = {"id": final, "page": None, "listing": listed_row,
                               "other_page": final, "page_template": tmpl}
            res.issues.append(Issue(final, "classify", "listed reality page uses unexpected template",
                                    str(tmpl)))
        else:
            what = tx.REJECT_TEMPLATES.get(tmpl or "", None)
            res.issues.append(Issue(final, "classify",
                                    f"rejected: {what} page" if what else "rejected: no reality/location infobox",
                                    str(tmpl)))

    # -------- pages named as the containing Dimension of an accepted page but not in any
    # crawled category (e.g. Inner Planes) are fetched too, so containers can be recognised
    parsed = {rid: wt.infobox(media.content(item["page"])) if item.get("page") else (None, {})
              for rid, item in accepted.items()}
    for _ in range(3):
        named = {wt.plain(f.get("Dimension", "")) for t, f in parsed.values() if t == "Location Template"}
        missing = sorted(n for n in named if n and n not in accepted and n not in light)
        if not missing:
            break
        extra = client.pages(missing)
        light.update(extra)
        for title, page in extra.items():
            if page.get("missing") is None and template_of(page) in tx.PLACE_TEMPLATES and page["title"] not in accepted:
                accepted[page["title"]] = {"id": page["title"], "page": page, "template": "Location Template",
                                           "listing": None}
                parsed[page["title"]] = wt.infobox(media.content(page))
    res.meta["categories"]["containing_pages_fetched"] = sum(1 for k in accepted if k not in set(candidates))

    # -------- which Location pages are dimensions? (see dimension_ids)
    dims = dimension_ids({rid: (set(media.categories(accepted[rid]["page"])), f)
                          for rid, (t, f) in parsed.items() if t == "Location Template"})

    # -------- parse accepted pages
    rows: dict[str, dict] = {}
    first_links: dict[str, list[dict]] = {}
    drift: dict[str, int] = {}
    infobox_pages = 0
    known_fields = load_schema_baseline()
    for rid, item in accepted.items():
        page, listing = item.get("page"), item.get("listing")
        template, fields = parsed[rid]
        if template:
            infobox_pages += 1
            known = known_fields.get(template, set())
            for k in fields:
                if k not in known:
                    drift[f"{template}.{k}"] = drift.get(f"{template}.{k}", 0) + 1
        cats = media.categories(page) if page else []
        catset = set(cats)
        row = {
            "id": rid, "page_title": page["title"] if page else item.get("other_page"),
            "template": template, "in_listing": listing is not None,
            "listing_kind": listing["kind"] if listing else None,
            "name": " - ".join(wt.list_items(fields.get("Title", ""))) or None,
            "designation": wt.plain(fields.get("EarthNumber", "")) or None,
            "aliases": [a for a in wt.list_items(fields.get("Aliases", "")) if a.lower() != "none"],
            "creators": [c for c in (s.strip() for s in wt.plain(fields.get("Creators", "")).split(";")) if c],
            "status_field": wt.plain(fields.get("Status", "")) or None,
            "categories": cats, "types": [], "parents": [], "destroyed_by": [],
            "revid": page["revisions"][0]["revid"] if page and page.get("revisions") else None,
            "last_edited": page["revisions"][0].get("timestamp") if page and page.get("revisions") else None,
            "listing_note": wt.plain(listing["notes_raw"]) if listing and listing["notes_raw"] else None,
            "listing_first": wt.plain(listing["first_raw"]) if listing else None,
            "home_reality": None,
            "destruction": wt.shorten(wt.plain(fields.get("Destruction", "")), 400)[0] or None,
            "last_appearance": wt.plain(fields.get("Last", "")) or None,
        }
        # kind
        if template == "Location Template":
            direct = catset & set(tx.DIMENSION_TYPE_CATEGORIES)
            own_dim = wt.plain(fields.get("Dimension", ""))
            if rid not in dims:
                containers = sorted(catset & tx.DIMENSION_CONTAINER_CATEGORIES)
                res.places.append({"id": rid, "name": (wt.list_items(fields.get("Name", "")) or [rid])[0],
                                   "dimension": own_dim or (containers[0] if containers else None),
                                   "reality": wt.plain(fields.get("Reality", "")) or None,
                                   "first_appearance": wt.plain(fields.get("First", "")) or None,
                                   "url": page_url(rid), "revid": row["revid"]})
                continue
            tags = {tx.DIMENSION_TYPE_CATEGORIES[c] for c in direct if tx.DIMENSION_TYPE_CATEGORIES[c]}
            if dims[rid] == "container":
                tags.add("container")
            row["types"] = sorted(tags)
            row["kind"] = "realm" if tags & tx.REALM_TAGS else "dimension"
            names = wt.list_items(fields.get("Name", ""))
            row["name"] = names[0] if names else None
            row["aliases"] = list(dict.fromkeys(row["aliases"] + names[1:]))
            row["home_reality"] = wt.plain(fields.get("Reality", "")) or None
            if own_dim and own_dim != rid:
                row["parents"].append(own_dim)
        elif listing:
            row["kind"] = listing["kind"]
        elif rid.startswith("Earth-TRN") or "Temporary Reality Numbers" in catset:
            row["kind"] = "temporary"
        elif re.match(r"^Earth-\d+[A-Za-z]+$", rid):
            row["kind"] = "variant_suffix"
        else:
            row["kind"] = "named"
        # type tags, parents, status, debut year
        for c in cats:
            if c in tx.REALITY_TYPE_CATEGORIES:
                row["types"].append(tx.REALITY_TYPE_CATEGORIES[c])
            if (m := tx.DIVERGED.match(c)):
                row["types"].append("diverged")
                row["parents"].append(m.group(1))
            if (m := tx.WARPED.match(c)):
                row["types"].append("warped")
                row["parents"].append(m.group(1))
            if (m := tx.DESTROYED_BY.match(c)):
                row["types"].append("destroyed")
                row["destroyed_by"].append(m.group(1))
        row["types"] = sorted(set(row["types"]))
        row["parents"] = list(dict.fromkeys(p for p in row["parents"] if p != rid))
        status = next((tx.STATUS_CATEGORIES[c] for c in cats if c in tx.STATUS_CATEGORIES), None)
        if not status and row["status_field"]:
            status = tx.STATUS_FIELD_VALUES.get(row["status_field"].lower(), row["status_field"].lower())
        if "destroyed" in row["types"] and status is None:
            status = "destroyed"
        row["status"] = "undocumented" if not row["page_title"] else (status or "unknown")
        row["needs_number"] = tx.NEEDS_NUMBER_CATEGORY in catset
        row["debut_year_category"] = next((int(m.group(1)) for c in cats if (m := tx.DEBUT_YEAR.match(c))), None)
        # description
        body = fields.get("History") or fields.get("Overview") or ""
        desc = wt.first_paragraph(body)
        short, cut = wt.shorten(desc) if desc else ("", False)
        row["description"] = short or row["listing_note"]
        row["description_shortened"] = cut
        row["description_source"] = "page" if short else ("listing" if row["listing_note"] else None)
        # first appearance: the page's First field, then the listing's column (tried in order)
        first_raw = fields.get("First", "") if page else ""
        candidates_ = []
        if first_raw.strip():
            candidates_.append(("page", wt.first_link(first_raw)))
        if listing and listing["first_raw"].strip():
            candidates_.append(("listing", wt.first_link(listing["first_raw"])))
        seen_t, links_ = set(), []
        for src_name, l in candidates_:
            if l and l["target"] and l["target"] not in seen_t:
                seen_t.add(l["target"])
                links_.append({**l, "source": src_name})
        row["first_appearance"] = wt.plain(first_raw) or (wt.plain(listing["first_raw"]) if listing else None)
        row["first_field_year"] = field_year(first_raw)
        first_links[rid] = links_
        # mentions of other realities (for "related")
        mention_text = " ".join(x for x in (listing["notes_raw"] if listing else "", fields.get("Notes", ""),
                                             body) if x)
        row["mentions"] = list(dict.fromkeys(l["target"] for l in wt.links(mention_text)
                                             if REALITY_ID.match(l["target"]) and l["target"] != rid))
        rows[rid] = row

    res.meta["field_drift"] = dict(sorted(drift.items(), key=lambda kv: -kv[1]))
    res.meta["infobox_pages"] = infobox_pages

    # -------- first-appearance works -> medium
    work_titles = sorted({l["target"] for ls in first_links.values() for l in ls if not l["external"]})
    # No categories here: comic pages carry hundreds of '/Appearances' categories.
    works = client.pages(work_titles, props="revisions|info")
    series_titles = sorted({s for p in works.values() if (s := media.series_of_episode(p))})
    series_pages = client.pages(series_titles)
    # Animated films: the wiki's Film Template has no animation flag, so use (1) an animation
    # studio among ProductionCompanies/Distributors, (2) Wikidata via IMDb ID or P6262, (3)
    # Wikidata by exact title + release year.
    imdb, films, by_studio = {}, {}, set()
    for w in works.values():
        tmpl, f = wt.infobox(media.content(w))
        if tmpl == "Film Template":
            films[w["title"]] = (re.sub(r" \((?:\d{4} )?film\)$", "", w["title"]),
                                 media.classify_work(w, {}, set())["year"])
            if f.get("IMDB ID"):
                imdb[w["title"]] = imdb_id(f["IMDB ID"])
            if re.search(r"\bAnimation\b", wt.plain(f.get("ProductionCompanies", "") + ";" + f.get("Distributors", ""))):
                by_studio.add(w["title"])
    animated_ids = client.animated_imdb_ids(list(imdb.values()))
    by_wikidata = {t for t, i in imdb.items() if i in animated_ids} | client.animated_fandom_titles(sorted(films))
    rest = {t: v for t, v in films.items() if t not in by_studio | by_wikidata}
    by_label = client.animated_by_label(rest)
    animated = {**{t: f"Wikidata {q} (title and year)" for t, q in by_label.items()},
                **{t: "Wikidata (IMDb ID or Marvel Database ID)" for t in by_wikidata},
                **{t: "animation studio in the film's infobox" for t in by_studio}}
    res.meta["works"] = {"first_appearance_pages": len(work_titles), "series_pages": len(series_titles),
                         "films": len(films), "films_with_imdb": len(imdb),
                         "animated_by_studio": len(by_studio), "animated_by_wikidata_id": len(by_wikidata),
                         "animated_by_wikidata_title_and_year": len(by_label)}
    res.meta["animated_by_label"] = by_label

    qids = client.marvel_fandom_ids()
    res.meta["wikidata_links_total"] = len(qids)
    med_over = overrides.get("medium", {})

    for rid, row in rows.items():
        work, row["first_work"], row["first_source"], tried = None, None, None, []
        for link in first_links.get(rid, []):
            wp = None if link["external"] else works.get(link["target"])
            if link["external"]:
                attempt = media.classify_external(link)
            elif wp and wp.get("missing") is None:
                attempt = media.classify_work(wp, series_pages, animated)
            else:
                attempt = media.classify_unwritten_comic(link["target"]) or \
                    {"medium": None, "format": None, "year": None, "reason": "first-appearance page missing"}
            tried.append(f"{link['source']}: {attempt['reason']}")
            if wp and wp.get("missing") is None and not row["first_work"]:
                row["first_work"] = wp["title"]
            if work is None or (not work["medium"] and attempt["medium"]):
                work = attempt
                row["first_source"] = link["source"]
            if attempt["medium"]:
                break
        medium = work["medium"] if work else None
        row["medium_format"] = work["format"] if work else None
        row["medium_source"] = f"first appearance ({work['reason']})" if medium else None
        if medium and row["first_source"] == "listing" and len(tried) > 1:
            row["medium_source"] = f"first appearance in the listing ({work['reason']}); page link: {tried[0]}"
        if not medium:
            kw = keyword_medium(row["listing_first"] or "", row["first_appearance"] or "",
                                row["listing_note"] or "", row["name"] or "")
            if kw:
                medium, row["medium_source"] = kw, "keywords (low confidence)"
            reason = "; ".join(tried) if tried else "no first appearance recorded"
            res.issues.append(Issue(rid, "medium", "medium not determined from first appearance",
                                    f"{reason}; " + (f"keyword fallback: {kw}" if kw else "left unclassified")))
        if rid in med_over:
            o = med_over[rid]
            if medium and medium != o["medium"]:
                res.issues.append(Issue(rid, "medium", "override differs from first-appearance medium",
                                        f"{medium} -> {o['medium']}: {o['reason']}"))
            medium, row["medium_source"] = o["medium"], f"reviewed override ({o['reason']})"
        row["medium"] = medium or "Unclassified"
        if row["medium"] == "Film" and row["first_work"] in films and row["first_work"] not in imdb \
                and row["first_work"] not in by_wikidata and rid not in med_over:
            res.issues.append(Issue(rid, "medium", "film not checked for animation",
                                    f"{row['first_work']} has no IMDb ID and no Wikidata link; it may be animated"))
        work_year = work["year"] if work else None
        listing_year = _first_paren_year(row["listing_first"] or "")
        if row["debut_year_category"]:
            row["first_year"], row["year_source"] = row["debut_year_category"], "wiki debut category"
        elif work_year:
            row["first_year"], row["year_source"] = work_year, "first-appearance page"
        elif row["first_field_year"]:
            row["first_year"], row["year_source"] = row["first_field_year"], "date given in the First field"
        elif listing_year:
            row["first_year"], row["year_source"] = listing_year, "listing (year in parentheses)"
        else:
            row["first_year"], row["year_source"] = None, None
        row["qid"] = qids.get(row["page_title"] or rid)
        sources = []
        if row["page_title"]:
            sources.append({"label": f"Marvel Database: {row['page_title']}", "url": page_url(row["page_title"]),
                            "permalink": permalink(row["page_title"], row["revid"])})
        if row["listing_kind"]:
            lt, lrev = listing_src[row["listing_kind"]]
            sources.append({"label": f"Marvel Database: {lt}", "url": page_url(lt), "permalink": permalink(lt, lrev)})
        if row["first_work"]:
            sources.append({"label": f"First appearance: {row['first_work']}", "url": page_url(row["first_work"]),
                            "permalink": None})
        if row["qid"]:
            sources.append({"label": f"Wikidata {row['qid']}", "url": f"https://www.wikidata.org/wiki/{row['qid']}",
                            "permalink": None})
        row["sources"] = sources
        if not row["page_title"]:
            res.issues.append(Issue(rid, "coverage", "listed reality has no wiki page yet", "status undocumented"))

    # -------- Earth-Unknown bucket (characters whose home reality is unknown)
    rows[UNKNOWN_BUCKET] = {
        "id": UNKNOWN_BUCKET, "page_title": None, "template": None, "in_listing": False, "listing_kind": None,
        "name": "Unknown reality", "designation": None, "aliases": [], "creators": [], "status_field": None,
        "categories": [], "types": [], "parents": [], "destroyed_by": [], "revid": None, "last_edited": None,
        "listing_note": None, "listing_first": None, "home_reality": None, "kind": "bucket", "status": "bucket",
        "destruction": None, "last_appearance": None,
        "needs_number": False, "debut_year_category": None,
        "description": ("Characters whose home reality the Marvel Database does not know. They are kept here so "
                        "they stay searchable."), "description_shortened": False, "description_source": "site",
        "first_appearance": None, "first_source": None, "mentions": [], "first_work": None, "medium": "Unclassified",
        "medium_format": None, "medium_source": None, "first_year": None, "year_source": None, "qid": None,
        "sources": [{"label": f"Marvel Database: Category:{UNKNOWN_CATEGORY}",
                     "url": page_url(f"Category:{UNKNOWN_CATEGORY}"), "permalink": None}],
        "bucket_size": client.category_size(f"Category:{UNKNOWN_CATEGORY}"),
    }

    # -------- links
    ids = set(rows)
    for rid, row in rows.items():
        for p in row["parents"]:
            rel = "dimension_of" if row["kind"] in ("dimension", "realm") else "diverged_from"
            if "warped" in row["types"] and p == "Earth-616" and rel == "diverged_from":
                rel = "warped_from"
            res.links.append({"src": rid, "dst": p, "relation": rel, "evidence": "category or infobox"})
            if p not in ids:
                res.issues.append(Issue(rid, "links", "parent reality not in index", p))
        for m in row.pop("mentions"):
            if m in ids:
                res.links.append({"src": rid, "dst": m, "relation": "mentions", "evidence": "listing notes or page text"})
        row["bucket_size"] = row.get("bucket_size")
        row.pop("debut_year_category", None)
        row.pop("first_field_year", None)
    res.realities = sorted(rows.values(), key=lambda r: r["id"])
    res.meta.update(client.counters())
    return res
