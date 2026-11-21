from ingest import wikitext as wt

REALITY_PAGE = """{{Marvel Database:Reality Template
| Image                   = Earth-1048.jpg
| EarthNumber             = 1048
| Title                   = Insomniac Games Marvel Universe
| Aliases                 = *Insomniac Games Universe{{Citation}}
| Status                  = Existing
| Creators                = Jon Paquette; Benjamin Arfmann; [[Dan Slott]]
| First                   = Marvel's Spider-Man: Hostile Takeover
| History                 = {{Quote|x|y}}
The '''Insomniac''' universe is home to [[Peter Parker (Earth-1048)|Spider-Man]].<ref>{{r|Foo}}</ref>

Second paragraph.
| Notes                   = Not to be confused with {{cl|Earth-616}}.
}}
Trailing text"""


def test_infobox_parses_nested_fields():
    name, f = wt.infobox(REALITY_PAGE)
    assert name == "Reality Template"
    assert f["EarthNumber"] == "1048"
    assert f["First"] == "Marvel's Spider-Man: Hostile Takeover"
    assert wt.plain(f["Creators"]) == "Jon Paquette; Benjamin Arfmann; Dan Slott"
    assert wt.first_paragraph(f["History"]) == "The Insomniac universe is home to Spider-Man."
    assert wt.list_items(f["Aliases"]) == ["Insomniac Games Universe"]


def test_links_handle_link_templates_and_external_wikis():
    assert wt.first_link("{{cl|Superior Spider-Man Vol 1 33}}")["target"] == "Superior Spider-Man Vol 1 33"
    ext = wt.first_link("{{Wc|britishcomics|2000 AD Vol 1 2374|''2000 AD'' #2374}} (2024)")
    assert ext == {"target": "2000 AD Vol 1 2374", "label": "2000 AD #2374", "external": "britishcomics"}
    assert wt.first_link("{{DC|Tom Strong Vol 1 1}} (1999)")["external"] == "dc"
    assert wt.first_link("''[[Marvel Contest of Champions]]''")["target"] == "Marvel Contest of Champions"
    assert wt.first_link("[[Iron Man (film)|''Iron Man'']]") == {"target": "Iron Man (film)", "label": "Iron Man",
                                                                   "external": None}
    assert wt.first_link("Avengers: Endgame")["target"] == "Avengers: Endgame"
    assert wt.first_link("[[File:x.jpg|thumb]] [[Earth-616]]")["target"] == "Earth-616"


def test_plain_strips_refs_templates_and_markup():
    s = "Home of [[Ezekiel Sims (Earth-4)|Old Man Spider]].<ref>x</ref> {{Citation}} '''Bold''' &amp; more<br/>end"
    assert wt.plain(s) == "Home of Old Man Spider. Bold & more end"
    assert wt.plain("{{Mentioned|[[Benjamin Parker (Earth-616)|Uncle Ben]]}}") == "Uncle Ben"
    # a leading colon makes a category link visible; without it the link only categorises
    raw = "{{Image Wiki|Wanted Vol 1 1|''Wanted'' #1}}<br>([[:Category:Week 50, 2003|December, 2003]])[[Category:X]]"
    assert wt.plain(raw) == "Wanted #1 (December, 2003)"
    assert wt.plain("Foo ([[Category:Hidden]])") == "Foo"


def test_shorten_cuts_at_sentence():
    text = "One sentence here. " * 60
    short, cut = wt.shorten(text, 100)
    assert cut and short.endswith(".") and len(short) <= 100
    assert wt.shorten("short", 100) == ("short", False)
