"""Knowledge graph: characters, teams, organisations, events, works, story
appearances, relationships and variant groups, parsed from the pages that
ingest/graph_fetch.py put in the run cache.

Every relationship row records the page and infobox field it came from.
Nothing is inferred: "fought" is derived at query time from story appearance
roles (Antagonists vs Featured/Supporting) and event sides, and always cites
the stories."""

from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ingest import media, wikitext as wt
from ingest.client import WikiClient
from ingest.graph_fetch import pages, titles
from ingest.realities import Issue, page_url, permalink

log = logging.getLogger("ingest.graph")

REALITY_SUFFIX = re.compile(r"\s*\(([^()]*)\)\s*$")
FAMILY_FIELDS = {"Parents": "parent", "Children": "child", "Siblings": "sibling", "Spouses": "spouse",
                 "Relatives": "relative", "Clones": "clone", "Ancestors": "ancestor",
                 "Grandparents": "grandparent", "InLaw": "in_law"}
TEAM_FIELDS = {"CurrentMembers": "member", "FormerMembers": "former_member", "Leaders": "leader",
               "Allies": "ally", "Enemies": "enemy"}
EVENT_FIELDS = {"Protagonists": "event_protagonist", "Antagonists": "event_antagonist", "Others": "event_other"}
APPEARANCE_FIELD = re.compile(r"^(Appearing|Appearances)(\d*)$")
ROLE_HEADERS = [("featured", re.compile(r"featured", re.I)), ("supporting", re.compile(r"supporting", re.I)),
                ("antagonist", re.compile(r"antagonist|villain", re.I)), ("other", re.compile(r"other char", re.I))]
STOP_HEADERS = re.compile(r"races|species|locations|items|vehicles|realities|organizations|events|groups", re.I)
# Appearance qualifier templates -> flag. Flags in NOT_PRESENT mean the entity was not
# physically there (mentioned, shown in a picture...), so it never counts as "fought".
FLAG_TEMPLATES = {
    "mentioned": "mentioned", "mention": "mentioned", "recaponly": "recap", "recap": "recap",
    "flashback": "flashback", "flashbackonly": "flashback", "flashbackandpresent": "flashback",
    "picture": "image", "imageonly": "image", "photo": "image", "pictureonly": "image", "statue": "image",
    "visiononly": "vision", "vision": "vision", "illusion": "vision", "dream": "vision", "hallucination": "vision",
    "fictional": "fictional", "voiceonly": "voice", "voice": "voice", "corpse": "corpse", "death": "death",
    "impersonated": "impersonation", "impersonation": "impersonation", "decoy": "impersonation",
    "possessed": "possessed", "cameo": "cameo", "1st": "first", "1stchrono": "first", "1st unnamed": "first",
    "bts": "offpanel", "behindthescenes": "offpanel", "narration": "narration", "ghost": "ghost",
    "unnamed": None, "chronology": None, "a": None, "apn": None, "g": None,
}
NOT_PRESENT = {"mentioned", "recap", "image", "vision", "fictional", "voice", "corpse", "impersonation",
               "offpanel", "narration"}
WORK_GROUPS = {"comics": "comic", "episodes": "episode", "films": "film", "short_films": "short film",
               "video_games": "video game", "novels": "novel"}
WORK_MEDIUM = {"comic": "Comics", "film": "Film", "short film": "Film", "video game": "Games", "novel": "Prose"}


@dataclass
class Graph:
    characters: list[dict] = field(default_factory=list)
    teams: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    works: list[dict] = field(default_factory=list)
    appearances: list[tuple] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)
    variant_groups: list[dict] = field(default_factory=list)
    names: list[dict] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


def base_name(title: str) -> tuple[str, str | None]:
    """'Thanos (Earth-616)' -> ('Thanos', 'Earth-616'); 'Thanos (Robot) (Earth-616)' -> ('Thanos (Robot)', 'Earth-616')."""
    m = REALITY_SUFFIX.search(title)
    if m and (m.group(1).startswith(("Earth-", "Moira-", "Jubilee-")) or m.group(1) in KNOWN_NON_EARTH):
        return title[:m.start()].strip(), m.group(1)
    return title, None


# Reality designations that are not "Earth-N" but appear as title suffixes.
KNOWN_NON_EARTH = {"Multiverse", "Mojoverse", "Otherworld", "Battleworld", "Limbo", "Microverse", "Negative Zone",
                   "Dark Dimension", "Unknown Reality", "Warp World", "Liveworld", "Heaven", "Hell"}


def norm_reality(value: str | None, suffix: str | None) -> str:
    """Infobox Reality values like '616' or 'Earth 616' -> 'Earth-616'; the page-title suffix wins when it
    is a reality designation, because it is how the wiki keys every variant page."""
    if suffix and suffix != "Unknown Reality":
        return suffix
    v = (value or "").strip()
    if re.fullmatch(r"(?:TRN)?\d+[A-Za-z]?", v):
        v = f"Earth-{v}"
    v = re.sub(r"^Earth\s+(?=\w)", "Earth-", v)
    if not v or v.lower() in ("unknown", "unknown reality") or suffix == "Unknown Reality":
        return "Earth-Unknown"
    return v


def assign_groups(groups: list[dict], characters: list[dict]) -> dict[str, str]:
    """One variant group per character page, by a fixed order of evidence:
    1. the disambiguation page titled with the character's own base name ("Peter Parker");
    2. else the largest page whose `main` has the same base name ("Logan" for James Howlett pages);
    3. else the largest page that explicitly lists it (include*). Ties break alphabetically."""
    by_id = {g["id"]: g for g in groups}
    base_of = {c["id"]: c["base_name"] for c in characters}
    by_main_base = defaultdict(list)
    containing = defaultdict(list)
    for g in groups:
        if g.get("main") in base_of:
            by_main_base[base_of[g["main"]]].append(g)
        for m in g["members"]:
            containing[m].append(g)
    rank = lambda gs: sorted(gs, key=lambda g: (-len(g["members"]), g["id"]))[0]["id"]  # noqa: E731
    out = {}
    for cid, base in base_of.items():
        if base in by_id and cid in by_id[base]["members"]:
            out[cid] = base
        elif [g for g in by_main_base.get(base, []) if cid in g["members"]]:
            out[cid] = rank([g for g in by_main_base[base] if cid in g["members"]])
        elif containing.get(cid):
            out[cid] = rank(containing[cid])
    return out


def _rev(page: dict) -> tuple[int | None, str]:
    revs = page.get("revisions") or []
    return (revs[0].get("revid") if revs else None), media.content(page)


def split_former(raw: str) -> tuple[str, str]:
    """(current, former) parts of a membership-style field. 'Formerly' appears as a
    {{Navigation|title=Formerly|body=...}} block or as a 'Formerly:' line."""
    former, kept, pos = [], [], 0
    for m in re.finditer(r"\{\{\s*Navigation\b", raw):
        if m.start() < pos:
            continue
        end = wt._match(raw, m.start(), "{{", "}}")
        p = wt.params(raw[m.end():end])
        if "former" in p.get("title", "").lower():
            former.append(p.get("body", ""))
            kept.append(raw[pos:m.start()])
            pos = end + 2
    raw = "".join(kept) + raw[pos:]
    parts = re.split(r"(?im)^[\s*'']*(?:formerly|former)\b[^\n]*$", raw, maxsplit=1)
    current = parts[0]
    if len(parts) > 1:
        former.append(parts[1])
    return current, "\n".join(former)


def entity_links(raw: str) -> list[dict]:
    """Internal page links in a field, with the qualifier text after each bullet."""
    out = []
    for line in re.split(r"\n", raw or ""):
        found = [l for l in wt.links(line) if not l["external"]]
        if not found:
            continue
        note = wt.plain(re.sub(r"\[\[[^\]]*\]\]", "", line)).strip(" *:#")[:120]
        for l in found:
            out.append({"target": l["target"], "label": l["label"], "note": note or None})
    return out


def killers(raw: str) -> list[tuple[str, str | None]]:
    """KilledBy values: wiki links, or bare page titles with a reality suffix ("Wade Wilson (Earth-71986)"),
    which is how most pages write the field. Anything else is not a page reference and is skipped."""
    out = []
    for line in re.split(r"\n|;|<br\s*/?>", raw or ""):
        found = entity_links(line)
        if found:
            out += [(l["target"], l["note"]) for l in found]
            continue
        text = wt.plain(line).strip(" *#:,")
        if text and base_name(text)[1]:
            out.append((text, None))
    return list(dict.fromkeys(out))


def parse_appearances(raw: str) -> list[tuple[str, str, list[str], str]]:
    """(entity, role, flags, label) for each bulleted entity under a role header."""
    out, role = [], None
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        header = re.match(r"^'''(.+?)'''\s*$", s) or re.match(r"^'''(.+?):?'''", s)
        if header and not s.startswith("*"):
            text = header.group(1)
            role = None if STOP_HEADERS.search(text) else next((r for r, p in ROLE_HEADERS if p.search(text)), None)
            continue
        if role is None or not s.startswith("*"):
            continue
        found = [l for l in wt.links(s) if not l["external"]]
        if not found:
            continue
        names = {n.strip().lower() for n in re.findall(r"\{\{\s*([^|{}]+?)\s*[|}]", s)}
        flags = sorted({FLAG_TEMPLATES[n] for n in names if FLAG_TEMPLATES.get(n)})
        out.append((found[0]["target"], role, flags, found[0]["label"][:80]))
    return out


def _year(fields: dict, *keys: str) -> int | None:
    for k in keys:
        m = re.search(r"\b(1[89]\d\d|20\d\d)\b", wt.plain(fields.get(k, "")))
        if m:
            return int(m.group(1))
    return None


def _desc(fields: dict) -> tuple[str | None, bool]:
    text = wt.first_paragraph(fields.get("Overview") or "") or wt.first_paragraph(fields.get("History") or "")
    if not text:
        return None, False
    return wt.shorten(text, 500)


def _headings(raw: str, limit: int = 14) -> list[str]:
    """Top-level item names in Powers/Abilities: a bold label followed by a colon that opens a line
    ("'''Spider-Physiology:''' ..."). Sub-items (** bullets) and bold words inside prose are skipped."""
    out = []
    for m in re.finditer(r"(?m)^[ \t]*\*?[ \t]*'''(.+?)'''([ \t]*:)?", raw or ""):
        if not (m.group(1).rstrip().endswith(":") or m.group(2)):
            continue
        name = wt.plain(m.group(1)).strip(" :.-\"'")
        if 2 < len(name) <= 48 and len(name.split()) <= 6 and name.lower() not in ("formerly", "former", "note"):
            out.append(name)
    return list(dict.fromkeys(out))[:limit]


def _short(raw: str, limit: int) -> str | None:
    """Plain text, shortened; numbered/bulleted lists become '; '-separated items."""
    raw = re.sub(r"(?m)^[ \t]*[#*]+[ \t]*", "\u2022", raw or "")
    text = re.sub(r"\s*\u2022\s*", "; ", wt.plain(raw)).strip("; ")
    return wt.shorten(text, limit)[0] if text and text.lower() not in ("unknown", "none", "n/a") else None


def character_profile(f: dict) -> dict:
    """Who-is-who fields as written on the infobox: origin, birthplace, citizenship, current
    occupations and bases, marital status, named powers and abilities, death, and the opening
    of the History section (the origin story). Values are shortened, never rewritten."""
    has_overview = bool(wt.first_paragraph(f.get("Overview") or ""))
    story = wt.first_paragraph(f.get("History") or "") if has_overview else ""
    return {
        "origin": _short(f.get("Origin"), 320),
        "place_of_birth": _short(f.get("PlaceOfBirth"), 160),
        "citizenship": _short(f.get("Citizenship"), 120),
        "occupation": _names(split_former(f.get("Occupation", ""))[0])[:8],
        "base": _names(split_former(f.get("BaseOfOperations", ""))[0])[:5],
        "marital_status": _short(f.get("MaritalStatus"), 120),
        "powers": _headings(f.get("Powers")),
        "abilities": _headings(f.get("Abilities")),
        "death": _short(f.get("Death"), 200),
        "cause_of_death": _short(f.get("CauseOfDeath"), 160),
        "origin_story": wt.shorten(story, 900)[0] if story else None,
    }


def _names(*raws: str) -> list[str]:
    out = []
    for raw in raws:
        for v in wt.list_items(raw or ""):
            v = re.sub(r"\s*\((?:formerly|former|currently)[^)]*\)\s*$", "", v, flags=re.I).strip(" ,.")
            if v and len(v) < 80 and v.lower() not in ("none", "unknown", "n/a"):
                out.append(v)
    return list(dict.fromkeys(out))


def build_graph(client: WikiClient, out_dir: Path) -> Graph:
    """Parse everything; story appearances stream to out_dir/appearances.jsonl."""
    g = Graph()
    out_dir.mkdir(parents=True, exist_ok=True)
    app_fh = (out_dir / "appearances.jsonl").open("w", encoding="utf-8")
    n_app = 0
    groups = {k: titles(client, k) for k in ("characters", "teams", "organizations", "events", "disambiguation")}
    team_titles = set(groups["teams"])
    g.meta["listed"] = {k: len(v) for k, v in groups.items()}

    # ---------------- characters
    for batch in pages(client, "characters"):
        for title, page in batch.items():
            revid, text = _rev(page)
            tmpl, f = wt.infobox(text)
            if tmpl != "Character Template":
                g.issues.append(Issue(title, "graph", "character page without Character Template", str(tmpl)))
                continue
            base, suffix = base_name(page["title"])
            reality = norm_reality(wt.plain(f.get("Reality", "")), suffix)
            first = wt.first_link(f.get("First", "")) if f.get("First", "").strip() else None
            desc, cut = _desc(f)
            cid = page["title"]
            g.characters.append({
                "id": cid, "name": wt.plain(f.get("Name", "")) or base, "base_name": base,
                "current_alias": wt.plain(f.get("CurrentAlias", "")) or None,
                "aliases": _names(f.get("Codenames", ""), f.get("Aliases", ""), f.get("Nicknames", ""),
                                  f.get("EditorialNames", ""))[:40],
                "reality": reality, "gender": wt.plain(f.get("Gender", "")) or None,
                "identity": wt.plain(f.get("Identity", "")) or None,
                "first_appearance": wt.plain(f.get("First", "")) or None,
                "first_work": first["target"] if first and not first["external"] else None,
                "creators": [c.strip() for c in wt.plain(f.get("Creators", "")).split(";") if c.strip()],
                "description": desc, "description_shortened": cut, **character_profile(f),
                "revid": revid, "url": page_url(cid), "permalink": permalink(cid, revid),
            })
            for target, note in killers(f.get("KilledBy", "")):
                g.relations.append({"src": cid, "dst": target, "type": "killed_by", "note": note,
                                    "evidence": cid, "field": "KilledBy"})
            for fld, rel in FAMILY_FIELDS.items():
                for l in entity_links(f.get(fld, "")):
                    g.relations.append({"src": cid, "dst": l["target"], "type": rel, "note": l["note"],
                                        "evidence": cid, "field": fld})
            current, former = split_former(f.get("Affiliation", ""))
            for raw, rel in ((current, "member"), (former, "former_member")):
                for l in entity_links(raw):
                    if l["target"] in team_titles:
                        g.relations.append({"src": cid, "dst": l["target"], "type": rel, "note": l["note"],
                                            "evidence": cid, "field": "Affiliation"})
    log.info("characters: %d", len(g.characters))

    # ---------------- teams and organisations
    seen = set()
    for group in ("teams", "organizations"):
        for batch in pages(client, group):
            for title, page in batch.items():
                tid = page["title"]
                if tid in seen:
                    continue
                seen.add(tid)
                revid, text = _rev(page)
                tmpl, f = wt.infobox(text)
                if tmpl not in ("Organization Template", "Team Template"):
                    g.issues.append(Issue(title, "graph", f"{group[:-1]} page without Organization Template", str(tmpl)))
                    continue
                base, suffix = base_name(tid)
                first = wt.first_link(f.get("First", "")) if f.get("First", "").strip() else None
                desc, cut = _desc(f)
                g.teams.append({
                    "id": tid, "kind": "team" if tid in team_titles else "organization",
                    "name": wt.plain(f.get("Name", "")) or base, "base_name": base,
                    "aliases": _names(f.get("Aliases", ""), f.get("EditorialNames", ""))[:40],
                    "reality": norm_reality(wt.plain(f.get("Reality", "")), suffix),
                    "first_appearance": wt.plain(f.get("First", "")) or None,
                    "first_work": first["target"] if first and not first["external"] else None,
                    "creators": [c.strip() for c in wt.plain(f.get("Creators", "")).split(";") if c.strip()],
                    "description": desc, "description_shortened": cut,
                    "revid": revid, "url": page_url(tid), "permalink": permalink(tid, revid),
                })
                for fld, rel in TEAM_FIELDS.items():
                    raw = f.get(fld, "")
                    if fld in ("CurrentMembers", "Leaders"):
                        cur, former = split_former(raw)
                        pairs = [(cur, rel), (former, "former_member" if fld == "CurrentMembers" else "former_leader")]
                    else:
                        pairs = [(raw, rel)]
                    for part, r in pairs:
                        for l in entity_links(part):
                            if r in ("ally", "enemy"):
                                g.relations.append({"src": tid, "dst": l["target"], "type": r, "note": l["note"],
                                                    "evidence": tid, "field": fld})
                            else:  # membership: character -> team
                                g.relations.append({"src": l["target"], "dst": tid, "type": r, "note": l["note"],
                                                    "evidence": tid, "field": fld})
    log.info("teams+organizations: %d", len(g.teams))

    # ---------------- events
    for batch in pages(client, "events"):
        for title, page in batch.items():
            revid, text = _rev(page)
            tmpl, f = wt.infobox(text)
            if tmpl != "Event Template":
                g.issues.append(Issue(title, "graph", "event category page without Event Template", str(tmpl)))
                continue
            eid = page["title"]
            first = wt.first_link(f.get("First", "")) if f.get("First", "").strip() else None
            synopsis = wt.first_paragraph(f.get("Synopsis", "") or f.get("History", ""))
            g.events.append({
                "id": eid, "name": wt.plain(f.get("Title", "")) or wt.plain(f.get("Name", "")) or base_name(eid)[0],
                "reality": norm_reality(wt.plain(f.get("Reality", "")), base_name(eid)[1]),
                "first_appearance": wt.plain(f.get("First", "")) or None,
                "first_work": first["target"] if first and not first["external"] else None,
                "last_appearance": wt.plain(f.get("Last", "")) or None,
                "description": wt.shorten(synopsis, 500)[0] if synopsis else None,
                "revid": revid, "url": page_url(eid), "permalink": permalink(eid, revid),
            })
            for fld, rel in EVENT_FIELDS.items():
                for l in entity_links(f.get(fld, "")):
                    g.relations.append({"src": l["target"], "dst": eid, "type": rel, "note": l["note"],
                                        "evidence": eid, "field": fld})
    log.info("events: %d", len(g.events))

    # ---------------- variant groups (disambiguation pages, using the wiki's own rule:
    # every character page whose base name is the disambiguation title, minus exclude*, plus include*)
    by_base = defaultdict(list)
    for c in g.characters:
        by_base[c["base_name"]].append(c["id"])
    char_ids = {c["id"] for c in g.characters}
    group_of = {}
    for batch in pages(client, "disambiguation"):
        for title, page in batch.items():
            revid, text = _rev(page)
            found = wt.find_template(text, r"Disambiguation")
            if not found:
                continue
            p = wt.params(found[1])
            did = page["title"]
            excluded = {l["target"] for k, v in p.items() if k.startswith("exclude") and v.strip()
                        and (l := wt.first_link(v))}
            included = set()
            for k, v in p.items():
                if k.startswith("include") and v.strip():
                    first = v.split(";")[0]
                    l = wt.first_link(first)
                    if l:
                        included.add(l["target"])
            main = wt.plain(p.get("main", "")) or None
            # the page lists every character titled "<base> (...)"; base comes from `main` when set
            # (the "Logan" page's main is "James Howlett (Earth-616)")
            base = base_name(main)[0] if main in char_ids else did
            auto = by_base.get(base, []) + ([] if base == did else by_base.get(did, []))
            members = [m for m in auto if m not in excluded] + \
                      sorted(t for t in included if t in char_ids and t not in auto)
            if not members:
                continue
            members = list(dict.fromkeys(members))
            g.variant_groups.append({"id": did, "main": main if main in char_ids else None, "members": members,
                                     "url": page_url(did), "permalink": permalink(did, revid)})
    group_of = assign_groups(g.variant_groups, g.characters)
    for c in g.characters:
        c["variant_group"] = group_of.get(c["id"])
    log.info("variant groups: %d", len(g.variant_groups))

    # ---------------- works + appearances
    label_counts: Counter = Counter()
    for group, kind in WORK_GROUPS.items():
        for batch in pages(client, group):
            for title, page in batch.items():
                revid, text = _rev(page)
                tmpl, f = wt.infobox(text)
                if not tmpl:
                    continue
                wid = page["title"]
                series = media.EPISODE_TITLE.match(wid).group(1) if kind == "episode" and media.EPISODE_TITLE.match(wid) else None
                g.works.append({"id": wid, "kind": kind, "medium": WORK_MEDIUM.get(kind), "series": series, "format": kind,
                                "year": _year(f, "Year", "Release Date", "US Release Date", "Published"),
                                "url": page_url(wid), "revid": revid,
                                # the page's own link to the MCU Wiki ({{Film Template}} "MCU" field)
                                "mcu": wt.plain(f.get("MCU", "")) or None})
                for k, v in f.items():
                    m = APPEARANCE_FIELD.match(k)
                    if not m:
                        continue
                    story = int(m.group(2) or 1)
                    for ent, role, flags, label in parse_appearances(v):
                        app_fh.write(json.dumps([wid, story, ent, role, flags], ensure_ascii=False) + "\n")
                        n_app += 1
                        label_counts[(label, ent)] += 1
        log.info("works after %s: %d, appearances %d", group, len(g.works), n_app)
    app_fh.close()

    # episode medium from the series page's SeriesType (animated vs live action)
    series = sorted({w["series"] for w in g.works if w["series"]})
    series_pages = client.pages(series)
    kinds = {t: media.series_kind(p) for t, p in series_pages.items()}
    for w in g.works:
        if w["kind"] == "episode":
            w["medium"], fmt = kinds.get(w["series"], (None, None))
            w["format"] = fmt

    # ---------------- name index for question resolution
    for c in g.characters:
        for n, src in [(c["name"], "name"), (c["base_name"], "title"), (c["current_alias"], "current alias")] + \
                [(a, "alias") for a in c["aliases"]]:
            if n:
                g.names.append({"name": n.lower(), "entity": c["id"], "kind": "character", "source": src})
    for t in g.teams:
        for n, src in [(t["name"], "name"), (t["base_name"], "title")] + [(a, "alias") for a in t["aliases"]]:
            if n:
                g.names.append({"name": n.lower(), "entity": t["id"], "kind": t["kind"], "source": src})
    for e in g.events:
        for n in {e["name"], base_name(e["id"])[0], re.sub(r"\s*\((?:\d{4} )?Event\)$", "", e["id"])}:
            if n:
                g.names.append({"name": n.lower(), "entity": e["id"], "kind": "event", "source": "name"})
    for (label, ent), n in label_counts.items():
        if n >= 3 and 1 < len(label) < 60:
            g.names.append({"name": label.lower(), "entity": ent, "kind": "appearance label", "source": f"label x{n}"})
    g.meta["counts"] = {"characters": len(g.characters), "teams": len(g.teams), "events": len(g.events),
                        "works": len(g.works), "appearances": n_app, "relations": len(g.relations),
                        "variant_groups": len(g.variant_groups)}
    return g


def write_jsonl(path: Path, rows) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
