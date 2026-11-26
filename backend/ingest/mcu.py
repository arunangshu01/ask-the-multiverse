"""MCU timeline (Earth-199999) from the MCU Wiki on Fandom (CC BY-SA, same API as the Marvel Database).

Phase membership comes from the structured {{Phase}} infobox on each phase page ("Phase One" ...).
Each title is then linked to the Marvel Database work it names, only by exact title (or exact
title without a "(film)"-style qualifier when that work has Earth-199999 characters in it).
Release years come from the Marvel Database work pages. Titles that can't be linked, and years
outside the phase's own date range, are reported as issues instead of being guessed."""

from __future__ import annotations

import re

from ingest import media, wikitext as wt
from ingest.client import WikiClient
from ingest.realities import Issue

MCU_API = "https://marvelcinematicuniverse.fandom.com/api.php"
MCU_WIKI = "https://marvelcinematicuniverse.fandom.com/wiki/"
PHASES = ["Phase One", "Phase Two", "Phase Three", "Phase Four", "Phase Five", "Phase Six"]
# infobox field -> entry kind, in display order
FIELDS = {"films": "film", "tv series": "series", "tv movies": "special", "specials": "special",
          "one shots": "one-shot", "shorts": "short", "digital series": "digital series"}
QUALIFIER = re.compile(r"\s*\((?:film|tv series|animated series|tv special|special|short film|series)\)\s*$", re.I)


def mcu_url(title: str, revid: int | None = None) -> str:
    u = MCU_WIKI + title.replace(" ", "_").replace("?", "%3F")
    return f"{u}?oldid={revid}" if revid else u


def parse_phase(title: str, text: str, revid: int | None) -> tuple[dict, list[dict]]:
    """(phase row, entries) from one phase page."""
    found = wt.find_template(text, r"Phase")
    p = wt.params(found[1]) if found else {}
    years = [int(y) for y in re.findall(r"\b(20\d\d)\b", wt.plain(p.get("duration", "")))]
    saga = re.search(r"phase of (?:the )?\[\[([^\]|]*Saga)", text)
    phase = {"phase": title, "order": PHASES.index(title) + 1 if title in PHASES else None,
             "saga": saga.group(1) if saga else None, "start_year": min(years) if years else None,
             "end_year": max(years) if years else None, "url": mcu_url(title), "permalink": mcu_url(title, revid)}
    entries, pos = [], 0
    for field, kind in FIELDS.items():
        for item in re.split(r"<br\s*/?>|\n", p.get(field, "")):
            link = wt.first_link(item)
            if not link or link["external"]:
                continue
            season = re.search(r"Season\s+(One|Two|Three|Four|Five|\d+)", item)
            pos += 1
            entries.append({"phase": title, "position": pos, "kind": kind, "title": wt.plain(link["label"]) or link["target"],
                            "mcu_page": link["target"], "season": _num(season.group(1)) if season else None,
                            "mcu_url": mcu_url(link["target"])})
    return phase, entries


def _num(word: str) -> int:
    return {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}.get(word.lower()) or int(word)


def fetch(client: WikiClient) -> tuple[list[dict], list[dict], list[Issue]]:
    phases, entries, issues = [], [], []
    pages = client.pages(PHASES, props="revisions")
    for title in PHASES:
        page = pages.get(title)
        if not page or page.get("missing"):
            issues.append(Issue(title, "mcu", "MCU Wiki phase page missing", MCU_API))
            continue
        revid = (page.get("revisions") or [{}])[0].get("revid")
        ph, es = parse_phase(title, media.content(page), revid)
        if not es:
            issues.append(Issue(title, "mcu", "phase page has no {{Phase}} title lists", str(revid)))
        phases.append(ph)
        entries += es
    return phases, entries, issues


def link_works(con, phases: list[dict], entries: list[dict]) -> list[Issue]:
    """Fill work/year/match on each entry from the DuckDB works table. Never guesses: an entry stays
    unlinked unless exactly one candidate matches by the rules in the module docstring."""
    issues = []
    span = {p["phase"]: (p["start_year"], p["end_year"]) for p in phases}
    has_199999 = """EXISTS (SELECT 1 FROM appearances a JOIN entities e ON e.id = a.entity
                    WHERE a.work = w.id AND e.reality = 'Earth-199999')"""
    for e in entries:
        names = list(dict.fromkeys(n for n in (e["mcu_page"], e["title"]) if n))
        e.update(work=None, work_kind=None, year=None, match=None)
        if e["kind"] == "series":
            bases = list(dict.fromkeys(QUALIFIER.sub("", n).lower() for n in names))
            season = f"w.id LIKE w.series || ' Season {int(e['season'])} %'" if e["season"] else "TRUE"
            rows = con.execute(f"""SELECT w.series, min(w.year) FILTER (WHERE {season}) AS year,
                    bool_or({has_199999}) AS mcu
                FROM works w WHERE w.kind = 'episode' AND (lower(w.series) IN (SELECT unnest($n))
                    OR lower(regexp_replace(w.series, '\\s*\\([^)]*\\)$', '')) IN (SELECT unnest($b)))
                GROUP BY 1""", {"n": [n.lower() for n in names], "b": bases}).fetchall()
            exact = [r for r in rows if r[0].lower() in [n.lower() for n in names]]
            pick, how = (exact, "exact title") if len(exact) == 1 else (
                [r for r in rows if r[2]], "title without qualifier, Earth-199999 episodes")
            if len(pick) == 1:
                e.update(work=pick[0][0], work_kind="series", year=pick[0][1], match=how)
        else:
            rows = con.execute(f"""SELECT w.id, w.kind, w.year, {has_199999} AS mcu FROM works w
                WHERE w.kind IN ('film', 'short film') AND (lower(w.id) IN (SELECT unnest($n))
                   OR lower(regexp_replace(w.id, '\\s*\\([^)]*\\)$', '')) IN (SELECT unnest($b)))""",
                               {"n": [n.lower() for n in names],
                                "b": list(dict.fromkeys(QUALIFIER.sub("", n).lower() for n in names))}).fetchall()
            exact = [r for r in rows if r[0].lower() in [n.lower() for n in names]]
            pick, how = (exact, "exact title") if len(exact) == 1 else (
                [r for r in rows if r[3]], "title without qualifier, Earth-199999 characters")
            if len(pick) == 1:
                e.update(work=pick[0][0], work_kind=pick[0][1], year=pick[0][2], match=how)
        if not e["work"]:
            issues.append(Issue(e["title"], "mcu", "MCU timeline title not linked to a Marvel Database page",
                                f"{e['phase']}: {e['mcu_page']}"))
        elif e["year"] and span.get(e["phase"], (None, None))[0]:
            lo, hi = span[e["phase"]]
            if not lo <= e["year"] <= hi:
                issues.append(Issue(e["title"], "mcu", "release year outside the phase's date range on the MCU Wiki",
                                    f"{e['work']} ({e['year']}) vs {e['phase']} {lo}-{hi}"))
    return issues
