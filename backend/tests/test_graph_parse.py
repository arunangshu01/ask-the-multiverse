from ingest import graph

FF48 = """
'''Featured Characters:'''
* {{a|[[Fantastic Four (Earth-616)|Fantastic Four]]}}
** {{a|[[Jonathan Storm (Earth-616)|Human Torch (Johnny Storm)]]}} {{Chronology}}
'''Supporting Characters:'''
* {{a|[[Uatu (Earth-616)|Watcher]]}} {{Chronology}}
'''Antagonists:'''
* {{1st Unnamed|[[Heralds of Galactus (Earth-616)|Heralds of Galactus]]}}
** {{apn|[[Norrin Radd (Earth-616)|Silver Surfer]]|-|Fantastic Four Vol 1 49}} {{1st}} {{Chronology}}
* {{apn|[[Galan (Earth-616)|Galactus]]|-|Fantastic Four Vol 1 49}} {{1st}}
'''Other Characters:'''
* {{Mentioned|[[Benjamin Parker (Earth-616)|Uncle Ben Parker]]}}
* {{WP|Joseph E. Levine}} {{Mentioned}}
* Numerous unnamed New Yorkers
'''Races and Species:'''
* {{a|[[Humans (Homo sapiens)|Humans]]}}
'''Locations:'''
* {{a|[[Milky Way]]}}
"""


def test_appearances_roles_flags_and_stop_headers():
    rows = graph.parse_appearances(FF48)
    by = {r[0]: r for r in rows}
    assert by["Fantastic Four (Earth-616)"][1] == "featured"
    assert by["Jonathan Storm (Earth-616)"][1] == "featured"
    assert by["Uatu (Earth-616)"][1] == "supporting"
    assert by["Norrin Radd (Earth-616)"][1:3] == ("antagonist", ["first"])
    assert by["Norrin Radd (Earth-616)"][3] == "Silver Surfer"
    assert by["Galan (Earth-616)"][1] == "antagonist"
    assert by["Benjamin Parker (Earth-616)"][1:3] == ("other", ["mentioned"])
    assert "Humans (Homo sapiens)" not in by and "Milky Way" not in by  # not characters
    assert not any("Joseph" in r[0] for r in rows)  # external Wikipedia link


def test_split_former_navigation_and_formerly_lines():
    raw = """*[[Scott Summers (Earth-616)|Cyclops]] ([[Alaska (State)|Alaska]] Team){{r|X-Men Vol 6 35}}
{{Navigation
| title                   = Formerly
| body                    =
*[[Warren Worthington III (Earth-616)|Angel]]{{Citation}}
}}"""
    cur, former = graph.split_former(raw)
    assert "Scott Summers" in cur and "Warren" not in cur and "Warren Worthington III" in former
    cur, former = graph.split_former("*The {{m|Eternity Watch}}\n*[[Heralds of Galactus (Earth-616)|Heralds]]\n"
                                     "Formerly:\n*{{m|God Squad}}")
    assert "Heralds" in cur and "God Squad" in former and "God Squad" not in cur


def test_entity_links_keep_notes():
    links = graph.entity_links("* [[Richard Parker (Earth-616)|Richard Parker]] (father, deceased)")
    assert links == [{"target": "Richard Parker (Earth-616)", "label": "Richard Parker", "note": "(father, deceased)"}]


def test_base_name_keeps_qualifiers():
    assert graph.base_name("Thanos (Earth-616)") == ("Thanos", "Earth-616")
    assert graph.base_name("Thanos (Robot) (Earth-616)") == ("Thanos (Robot)", "Earth-616")
    assert graph.base_name("Avengers (Earth-TRN734)") == ("Avengers", "Earth-TRN734")
    assert graph.base_name("Galactus") == ("Galactus", None)


def test_assign_groups_prefers_own_base_then_main_then_includes():
    chars = [{"id": i, "base_name": graph.base_name(i)[0]} for i in
             ("Peter Parker (Earth-616)", "James Howlett (Earth-616)", "James Howlett (Earth-807128)", "Ai Apaec (Earth-616)")]
    groups = [
        {"id": "Amazing Spider", "main": None, "members": ["Peter Parker (Earth-616)", "Ai Apaec (Earth-616)"]},
        {"id": "Peter Parker", "main": "Peter Parker (Earth-616)", "members": ["Peter Parker (Earth-616)"]},
        {"id": "Logan", "main": "James Howlett (Earth-616)", "members": ["James Howlett (Earth-616)", "James Howlett (Earth-807128)", "Logan (Earth-65)"]},
        {"id": "Patch", "main": "James Howlett (Earth-616)", "members": ["James Howlett (Earth-616)", "James Howlett (Earth-807128)"]},
    ]
    out = graph.assign_groups(groups, chars)
    assert out == {"Peter Parker (Earth-616)": "Peter Parker", "James Howlett (Earth-616)": "Logan",
                   "James Howlett (Earth-807128)": "Logan", "Ai Apaec (Earth-616)": "Amazing Spider"}


def test_norm_reality():
    assert graph.norm_reality("616", None) == "Earth-616"
    assert graph.norm_reality("Earth 199999", None) == "Earth-199999"
    assert graph.norm_reality("Earth-1610", "Earth-616") == "Earth-616"
    assert graph.norm_reality("", "Unknown Reality") == "Earth-Unknown"


def test_character_profile_fields():
    f = {
        "Origin": "[[Humans (Homo sapiens)|Human]] [[Glossary:Mutate|mutated]] by [[Goddess (Spider) (Earth-616)|radioactive spider]] bite",
        "PlaceOfBirth": "[[Queens]], [[New York City]]",
        "Occupation": "*Superhero\n*Inventor{{r|Some Vol 1 9}}\n\nFormerly:\n*Student",
        "Powers": "{{Quote|Unbelievable!|Nightcrawler|X}}\n*'''Spider-Physiology:''' powers of a spider\n"
                  "**'''Sub Power:''' nested\n'''{{Power|Energy Conversion}}:''' charge objects\n"
                  "He has '''Nigh'''-invulnerability.",
        "CauseOfDeath": "# Killed by Doctor Doom (revived)\n# Beaten by Terraxia (revived)",
        "Overview": "'''Peter Parker''' is a hero.",
        "History": "===Early Life===\n[[File:X.jpg|thumb|left|cap]]\n'''Peter''' was born in [[Queens]] to agents.",
    }
    p = graph.character_profile(f)
    assert p["origin"] == "Human mutated by radioactive spider bite"
    assert p["place_of_birth"] == "Queens, New York City"
    assert p["occupation"] == ["Superhero", "Inventor"]
    assert p["powers"] == ["Spider-Physiology", "Energy Conversion"]
    assert p["cause_of_death"] == "Killed by Doctor Doom (revived); Beaten by Terraxia (revived)"
    assert p["origin_story"] == "Peter was born in Queens to agents."
    assert graph.character_profile({"History": "Born somewhere far away, long ago."})["origin_story"] is None


def test_killers_links_and_bare_titles():
    assert graph.killers("[[Victor von Doom (Earth-616)|Doctor Doom]]") == [("Victor von Doom (Earth-616)", None)]
    assert graph.killers("Wade Wilson (Earth-71986);\nBlackagar Boltagon (Earth-99220)") == [
        ("Wade Wilson (Earth-71986)", None), ("Blackagar Boltagon (Earth-99220)", None)]
    assert graph.killers("Unknown assailant") == []
