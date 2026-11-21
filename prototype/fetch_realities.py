"""Build realities.json from the Marvel Database (Fandom) reality listings (CC BY-SA).

Sources:
  Multiverse/Universe_Listing          - every officially numbered reality
  List_of_Temporary_Reality_Numbers    - wiki-assigned TRNs for un-numbered realities
"""
import json
import re
import time
import urllib.parse
import urllib.request

API = "https://marvel.fandom.com/api.php"
UA = {"User-Agent": "AskTheMultiversePreview/0.1 (portfolio prototype)"}


def wikitext(page):
    q = urllib.parse.urlencode({"action": "parse", "page": page, "prop": "wikitext", "format": "json"})
    with urllib.request.urlopen(urllib.request.Request(f"{API}?{q}", headers=UA), timeout=60) as r:
        return json.load(r)["parse"]["wikitext"]["*"]


def clean(s):
    s = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"\{\{(?:cl|c|Wc|wc|DC|Dc|WP|ml|el|sl|vl|g|tv|m|n)\|(?:[^|{}]*\|)*?([^|{}]*)\}\}", r"\1", s)
    for _ in range(3):
        s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[https?://\S+ ([^\]]*)\]", r"\1", s)
    s = re.sub(r"'{2,}|<[^>]+>", "", s)
    return re.sub(r"\s+", " ", s).strip(" |-")


COMIC = re.compile(r"\{\{\s*(?:cl|c|wc|dc|el)\s*\||\bvol \d", re.I)
GAMES = re.compile(r"video ?game|\(game\)|\bgames?\b|lego marvel|future fight|contest of champions|strike force|puzzle quest|"
                   r"ultimate alliance|avengers academy|battle lines|\bvr\b|pinball|role-playing|\brpg\b|playstation|xbox|nintendo|"
                   r"midnight suns|snap\b|marvel heroes|marvel rivals|super war|avengers alliance|war of heroes|mobile|telltale", re.I)
ANIM = re.compile(r"animat|cartoon|anime|what if\.\.\.\?|x-men '97|super hero squad|disk wars|spidey and his|"
                  r"earth's mightiest heroes|wolverine and the x-men|avengers assemble|ultimate spider-man|spectacular spider-man|"
                  r"hulk and the agents|x-men: evolution|fantastic four: world's|iron man: armored|marvel action hour|"
                  r"spider-man unlimited|silver surfer \(|avengers: united|moon girl|i am groot|eyes of wakanda|"
                  r"your friendly neighborhood|hit-monkey|m\.o\.d\.o\.k\.|marvel zombies \(tv|future avengers|spider-verse", re.I)
FILM = re.compile(r"\(film\)|\{\{\s*ml\s*\||\bfilm\b|movie|motion picture|serial", re.I)
TV = re.compile(r"\(tv series\)|season \d|episode|television|\btv\b|series|netflix|disney\+|hulu|\{\{\s*sl\s*\|", re.I)
PROSE = re.compile(r"novel|\(book\)|\bbook\b|prose|audio|podcast|short story", re.I)


OVERRIDES = {"Earth-838": "Film", "Earth-616": "Comics"}


def medium(first_raw, notes):
    if re.search(r"chaos engine", first_raw, re.I):
        return "Prose"
    if re.search(r"unpublished", first_raw, re.I):
        return "Comics"
    if COMIC.search(first_raw):
        return "Comics"
    text = f"{first_raw} {notes}"
    for name, pat in (("Games", GAMES), ("Animation", ANIM), ("Film", FILM), ("Television", TV), ("Prose", PROSE)):
        if pat.search(text):
            return name
    return "Other media"


def year_of(*parts):
    m = re.search(r"\b(19[3-9]\d|20[0-3]\d)\b", " ".join(parts))
    return int(m.group(1)) if m else None


def parse_official(text):
    for row in text.split("\n|-")[1:]:
        cells = [c.strip() for c in re.split(r"\n\|(?!\})", "\n" + row.strip()) if c.strip()]
        m = cells and re.search(r"\[\[([^|\]]+)", cells[0])
        if not m:
            continue
        first_raw = cells[1] if len(cells) > 1 else ""
        notes_raw = " ".join(cells[2:])
        yield {"id": m.group(1).strip(), "kind": "official", "medium": medium(first_raw, notes_raw),
               "first": clean(first_raw)[:120], "notes": clean(notes_raw)[:220], "year": year_of(first_raw)}


def parse_trn(text):
    current = text.split("==Current TRNs==", 1)[-1]
    current = re.split(r"\n==[^=]", current, 1)[0]
    for line in current.splitlines():
        m = re.match(r"\*\s*\[\[(Earth-TRN[^|\]]+)\]\]\s*-?\s*(.*)", line.strip())
        if not m:
            continue
        rest = m.group(2)
        yield {"id": m.group(1).strip(), "kind": "temporary", "medium": medium(rest, rest),
               "first": clean(rest)[:120], "notes": "", "year": year_of(rest)}


def main():
    rows, seen = [], set()
    for page, parser in (("Multiverse/Universe_Listing", parse_official), ("List_of_Temporary_Reality_Numbers", parse_trn)):
        for r in parser(wikitext(page)):
            if r["id"] not in seen:
                seen.add(r["id"])
                r["medium"] = OVERRIDES.get(r["id"], r["medium"])
                rows.append(r)
        time.sleep(1)
    with open("realities.json", "w") as f:
        json.dump(rows, f, separators=(",", ":"))
    by = {}
    for r in rows:
        by[(r["kind"], r["medium"])] = by.get((r["kind"], r["medium"]), 0) + 1
    print(len(rows), "realities")
    for k, v in sorted(by.items()):
        print(" ", k, v)


if __name__ == "__main__":
    main()
