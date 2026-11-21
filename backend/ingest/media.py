"""Classify a work page (comic, film, episode, series, game, novel...) into a
medium using its infobox template and fields, never free-text keywords."""

from __future__ import annotations

import re

from ingest import wikitext as wt

# Marvel Database infobox template -> (medium, format). None = decided later.
WORK_TEMPLATES = {
    "Comic Template": ("Comics", "comic"),
    "Volume Template": ("Comics", "comic series"),
    "Comic Book Template": ("Comics", "comic"),
    "Handbook Template": ("Comics", "handbook"),
    "Board Game Template": ("Games", "board game"),
    "Film Template": ("Film", None),
    "Episode Template": (None, "episode"),
    "Television Series Template": (None, "series"),
    "Series Template": (None, "series"),
    "TV Series Template": (None, "series"),
    "Video Game Template": ("Games", "video game"),
    "Game Template": ("Games", "game"),
    "Novel Template": ("Prose", "novel"),
    "Book Template": ("Prose", "book"),
    "Podcast Template": ("Prose", "podcast"),
    "Audio Template": ("Prose", "audio"),
}
SEASON_CATEGORY = re.compile(r"^(.+?) Season \d+$")
# Film Template `Type` values that are live shows, not films.
LIVE_SHOW_TYPES = {"stage performance", "theme park attraction", "live show", "ride"}
YEAR = re.compile(r"\b(1[89]\d\d|20\d\d)\b")
COVER_YEAR = re.compile(r"^(\d{4}) Cover Date$")
RELEASE_MONTH = re.compile(r"^(\d{4}), [A-Z][a-z]+$")


def categories(page: dict) -> list[str]:
    return [c["title"].split(":", 1)[1] for c in page.get("categories", [])]


def content(page: dict) -> str:
    revs = page.get("revisions") or []
    return revs[0]["slots"]["main"]["content"] if revs else ""


def _year(value: str) -> int | None:
    m = YEAR.search(wt.plain(value or ""))
    return int(m.group(1)) if m else None


EPISODE_TITLE = re.compile(r"^(.+?) Season \d+ \d+[A-Za-z]?$")


def series_of_episode(page: dict) -> str | None:
    m = EPISODE_TITLE.match(page.get("title", ""))
    if m and wt.infobox(content(page))[0] == "Episode Template":
        return m.group(1)
    for cat in categories(page):
        m = SEASON_CATEGORY.match(cat)
        if m:
            return m.group(1)
    return None


def series_kind(series_page: dict | None) -> tuple[str | None, str | None]:
    """(medium, format) from a series page's SeriesType field or categories.
    SeriesType values seen: Animated, Live Action, TV, Web, Podcast, Motion Comic."""
    if not series_page:
        return None, None
    _, fields = wt.infobox(content(series_page))
    stype = fields.get("SeriesType", "").lower()
    cats = set(categories(series_page))
    if "animated" in stype or "Animated Series" in cats:
        return "Animation", "animated series"
    if "live action" in stype or "Live Action Series" in cats:
        return "Television", "live-action series"
    if "podcast" in stype or "Podcasts" in cats:
        return "Prose", "podcast"
    if "motion comic" in stype or "Motion Comics" in cats:
        return "Other media", "motion comic"
    if "web" in stype or "Web Series" in cats:
        return "Other media", "web series"
    if "tv" in stype or "Television Series" in cats:
        return "Television", "television series"
    return None, None


def classify_work(page: dict, series_pages: dict[str, dict], animated_films: set[str]) -> dict:
    """Return {medium, format, year, template, series, reason}; medium None if unknown."""
    template, fields = wt.infobox(content(page))
    cats = categories(page)
    out = {"medium": None, "format": None, "year": None, "template": template, "series": None,
           "reason": None}
    if page.get("missing") is not None or not template:
        out["reason"] = "first-appearance page missing" if page.get("missing") is not None \
            else "first-appearance page has no infobox"
        return out
    if template not in WORK_TEMPLATES:
        out["reason"] = f"first-appearance page uses {template}"
        return out
    medium, fmt = WORK_TEMPLATES[template]
    title = page["title"]
    if template == "Film Template":
        fmt = (wt.plain(fields.get("Type", "")) or "film").lower()
        if fmt in LIVE_SHOW_TYPES:
            medium = "Other media"
        elif title in animated_films:
            medium = "Animation"
            fmt = f"animated {fmt}"
            evidence = animated_films[title] if isinstance(animated_films, dict) else None
            if evidence:
                out["reason"] = f"Film Template; animated per {evidence}"
        out["year"] = _year(fields.get("Release Date", "")) or _year(fields.get("US Release Date", ""))
    elif template == "Episode Template":
        series = series_of_episode(page)
        out["series"] = series
        medium, kind = series_kind(series_pages.get(series)) if series else (None, None)
        fmt = f"episode ({kind})" if kind else fmt
        out["year"] = _year(fields.get("Year", ""))
        if not medium:
            out["reason"] = f"episode series {series!r} has no SeriesType"
    elif fmt == "series":
        medium, fmt = series_kind(page)
        fmt = fmt or "series"
        first = wt.first_link(fields.get("First Aired", ""))
        out["year"] = _year(fields.get("First Aired", "")) if not first else None
    elif template in ("Comic Template", "Comic Book Template"):
        out["year"] = _year(fields.get("Year", ""))
        if not out["year"]:
            out["year"] = next((int(m.group(1)) for c in cats if (m := COVER_YEAR.match(c))), None)
    elif template == "Volume Template":
        out["year"] = next((int(c[:4]) for c in cats if c.endswith(" Volume Debuts") and c[:4].isdigit()), None)
    else:
        out["year"] = _year(fields.get("Release Date", "")) or _year(fields.get("Published", ""))
    if not out["year"]:
        out["year"] = next((int(m.group(1)) for c in cats if (m := RELEASE_MONTH.match(c))), None)
    out["medium"], out["format"] = medium, fmt
    if medium and not out["reason"]:
        out["reason"] = f"{template}"
    return out


COMIC_ISSUE_TITLE = re.compile(r"^.+ Vol \d+ [\w.½-]+$")


def classify_unwritten_comic(title: str) -> dict | None:
    """A red link named like a Marvel Database comic issue ('<Series> Vol N M')
    is an issue whose page has not been written yet."""
    if not COMIC_ISSUE_TITLE.match(title or ""):
        return None
    return {"medium": "Comics", "format": "comic", "year": None, "template": None, "series": None,
            "reason": "comic-issue page name; page not written yet"}


def classify_external(link: dict) -> dict:
    """First appearances on other wikis ({{Wc|...}}, {{DC|...}}): only comic
    issue titles ('... Vol N M') are classified; anything else stays unknown."""
    target = link.get("target", "")
    comic = bool(re.search(r"\bVol \d+\b", target) or re.search(r"#\s?\d", link.get("label", "")))
    return {"medium": "Comics" if comic else None, "format": "external comic" if comic else None,
            "year": None, "template": None, "series": None,
            "reason": f"external {link.get('external')} link" + ("" if comic else " (not a comic issue)")}
