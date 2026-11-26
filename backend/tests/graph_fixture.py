"""A small knowledge graph built through the real graph_build path.

Facts mirror the Marvel Database pages they are named after (Fantastic Four Vol 1 48,
Infinity Gauntlet (Event), the Avengers/X-Men member lists...), trimmed to a few rows."""

import json

from ingest.graph import Graph
from ingest.realities import Issue


def char(cid, alias=None, reality="Earth-616", first=None, creators=(), group=None, aliases=(), **profile):
    name = cid.rsplit(" (", 1)[0]
    return {"id": cid, "name": name, "base_name": name, "current_alias": alias, "aliases": list(aliases),
            "reality": reality, "gender": None, "identity": None, "first_appearance": first, "first_work": first,
            "creators": list(creators), "description": None, "description_shortened": False, "variant_group": group,
            "occupation": [], "base": [], "powers": [], "abilities": [], **profile,
            "revid": 1, "url": f"https://marvel.fandom.com/wiki/{cid.replace(' ', '_')}", "permalink": None}


def team(tid):
    name = tid.rsplit(" (", 1)[0]
    return {"id": tid, "kind": "team", "name": name, "base_name": name, "aliases": [], "reality": "Earth-616",
            "first_appearance": None, "first_work": None, "creators": [], "description": None,
            "description_shortened": False, "revid": 1, "url": f"https://marvel.fandom.com/wiki/{tid.replace(' ', '_')}",
            "permalink": None}


def sample_graph() -> tuple[Graph, list]:
    g = Graph()
    g.characters = [
        char("Peter Parker (Earth-616)", "Spider-Man", first="Amazing Fantasy Vol 1 15", creators=["Stan Lee", "Steve Ditko"],
             group="Peter Parker", origin="Human mutated by radioactive spider bite", place_of_birth="Queens, New York City",
             powers=["Spider-Physiology"], origin_story="Peter Benjamin Parker was born in Queens."),
        char("Peter Parker (Earth-199999)", "Spider-Man", reality="Earth-199999", group="Peter Parker"),
        char("Peter Parker (Earth-1048)", "Spider-Man", reality="Earth-1048", group="Peter Parker"),
        char("Thanos (Earth-616)", first="Iron Man Vol 1 55", creators=["Jim Starlin"], group="Thanos"),
        char("Galan (Earth-616)", "Galactus", first="Fantastic Four Vol 1 48", creators=["Stan Lee", "Jack Kirby"]),
        char("Norrin Radd (Earth-616)", "Silver Surfer", first="Fantastic Four Vol 1 48"),
        char("Thor Odinson (Earth-616)", "Thor", first="Journey into Mystery Vol 1 83"),
        char("Loki Laufeyson (Earth-616)", "Loki"),
        char("Anthony Stark (Earth-616)", "Iron Man"),
        char("James Howlett (Earth-616)", "Wolverine", aliases=["Logan"], group="James Howlett"),
        char("James Howlett (Earth-807128)", "Wolverine", reality="Earth-807128", group="James Howlett"),
        char("Henry McCoy (Earth-616)", "Beast"),
        char("Adam Warlock (Earth-616)"),
        char("Reed Richards (Earth-616)", "Mister Fantastic"),
    ]
    g.teams = [team("Avengers (Earth-616)"), team("X-Men (Earth-616)"), team("Fantastic Four (Earth-616)")]
    g.events = [{"id": "Infinity Gauntlet (Event)", "name": "Infinity Gauntlet", "reality": "Earth-616",
                 "first_appearance": "Infinity Gauntlet Vol 1 1", "first_work": "Infinity Gauntlet Vol 1 1",
                 "last_appearance": None, "description": None, "revid": 1,
                 "url": "https://marvel.fandom.com/wiki/Infinity_Gauntlet_(Event)", "permalink": None}]
    g.works = [{"id": w, "kind": "comic", "medium": "Comics", "format": "comic", "series": None, "year": y,
                "url": f"https://marvel.fandom.com/wiki/{w.replace(' ', '_')}", "revid": 1}
               for w, y in (("Fantastic Four Vol 1 48", 1966), ("Infinity Gauntlet Vol 1 4", 1991),
                            ("Thor Vol 1 160", 1969), ("Silver Surfer Vol 3 50", 1991), ("Amazing Fantasy Vol 1 15", 1962))]
    g.works.append({"id": "Iron Man (film)", "kind": "film", "medium": "Film", "format": "film", "series": None,
                    "year": 2008, "url": "https://marvel.fandom.com/wiki/Iron_Man_(film)", "revid": 1})
    apps = [
        ("Fantastic Four Vol 1 48", 1, "Fantastic Four (Earth-616)", "featured", []),
        ("Fantastic Four Vol 1 48", 1, "Reed Richards (Earth-616)", "featured", []),
        ("Fantastic Four Vol 1 48", 1, "Galan (Earth-616)", "antagonist", ["first"]),
        ("Fantastic Four Vol 1 48", 1, "Norrin Radd (Earth-616)", "antagonist", ["first"]),
        ("Infinity Gauntlet Vol 1 4", 1, "Thanos (Earth-616)", "antagonist", []),
        ("Infinity Gauntlet Vol 1 4", 1, "Norrin Radd (Earth-616)", "featured", []),
        ("Infinity Gauntlet Vol 1 4", 1, "Thor Odinson (Earth-616)", "featured", []),
        ("Infinity Gauntlet Vol 1 4", 1, "Adam Warlock (Earth-616)", "featured", []),
        ("Thor Vol 1 160", 1, "Thor Odinson (Earth-616)", "featured", []),
        ("Thor Vol 1 160", 1, "Galan (Earth-616)", "antagonist", []),
        ("Silver Surfer Vol 3 50", 1, "Norrin Radd (Earth-616)", "featured", []),
        ("Silver Surfer Vol 3 50", 1, "Galan (Earth-616)", "antagonist", ["mentioned"]),
        ("Amazing Fantasy Vol 1 15", 1, "Peter Parker (Earth-616)", "featured", ["first"]),
    ]
    rel = lambda s, d, t, f="CurrentMembers": {"src": s, "dst": d, "type": t, "note": None, "evidence": d, "field": f}  # noqa: E731
    g.relations = [
        rel("Anthony Stark (Earth-616)", "Avengers (Earth-616)", "member"),
        rel("Thor Odinson (Earth-616)", "Avengers (Earth-616)", "former_member", "FormerMembers"),
        rel("James Howlett (Earth-616)", "Avengers (Earth-616)", "former_member", "FormerMembers"),
        rel("James Howlett (Earth-616)", "X-Men (Earth-616)", "member"),
        rel("Henry McCoy (Earth-616)", "X-Men (Earth-616)", "member"),
        rel("Henry McCoy (Earth-616)", "Avengers (Earth-616)", "former_member", "FormerMembers"),
        rel("Reed Richards (Earth-616)", "Fantastic Four (Earth-616)", "member"),
        rel("Thor Odinson (Earth-616)", "Loki Laufeyson (Earth-616)", "sibling", "Siblings"),
        rel("Thanos (Earth-616)", "Infinity Gauntlet (Event)", "event_antagonist", "Antagonists"),
        rel("Norrin Radd (Earth-616)", "Infinity Gauntlet (Event)", "event_protagonist", "Protagonists"),
        rel("Adam Warlock (Earth-616)", "Infinity Gauntlet (Event)", "event_protagonist", "Protagonists"),
        rel("Avengers (Earth-616)", "Thanos (Earth-616)", "enemy", "Enemies"),
        {"src": "Loki Laufeyson (Earth-616)", "dst": "Thor Odinson (Earth-616)", "type": "killed_by", "note": None,
         "evidence": "Loki Laufeyson (Earth-616)", "field": "KilledBy"},
        rel("Thor Odinson (Earth-616)", "Alaska (State)", "relative", "Relatives"),  # not an entity: dropped + counted
    ]
    g.variant_groups = [
        {"id": "Peter Parker", "main": "Peter Parker (Earth-616)", "url": "u", "permalink": None,
         "members": ["Peter Parker (Earth-616)", "Peter Parker (Earth-199999)", "Peter Parker (Earth-1048)"]},
        {"id": "James Howlett", "main": "James Howlett (Earth-616)", "url": "u", "permalink": None,
         "members": ["James Howlett (Earth-616)", "James Howlett (Earth-807128)"]},
        {"id": "Thanos", "main": "Thanos (Earth-616)", "url": "u", "permalink": None, "members": ["Thanos (Earth-616)"]},
    ]
    for c in g.characters:
        for n in {c["name"], c["base_name"], c["current_alias"], *c["aliases"]} - {None}:
            g.names.append({"name": n.lower(), "entity": c["id"], "kind": "character", "source": "name"})
    for t in g.teams:
        g.names.append({"name": t["name"].lower(), "entity": t["id"], "kind": "team", "source": "name"})
    g.names.append({"name": "infinity gauntlet", "entity": "Infinity Gauntlet (Event)", "kind": "event", "source": "name"})
    g.issues = [Issue("Some Page", "graph", "character page without Character Template", "None")]
    g.meta = {"listed": {"characters": len(g.characters)}}
    return g, apps


PHASE_ONE = """{{Phase
|films = ''[[Iron Man (film)|Iron Man]]''<br>''[[The Avengers]]''
|one shots = ''[[Marvel One-Shot: The Consultant|The Consultant]]''
|duration = 2008 - 2012
|followed by = [[Phase Two]]}}
'''Phase One''' is the first phase of the [[Marvel Cinematic Universe]] and the first phase of [[The Infinity Saga]]."""


def sample_mcu():
    """Phase One as written on the MCU Wiki: one title with a Marvel Database page, two without."""
    from ingest import mcu
    phase, entries = mcu.parse_phase("Phase One", PHASE_ONE, 2618181)
    return [phase], entries, []


def write_appearances(clean_dir, apps):
    clean_dir.mkdir(parents=True, exist_ok=True)
    with (clean_dir / "appearances.jsonl").open("w") as fh:
        for a in apps:
            fh.write(json.dumps(list(a)) + "\n")
