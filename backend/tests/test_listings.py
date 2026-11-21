from ingest import realities as r

LISTING = """{| class="wikitable" border="2"
|+Marvel Multiverse Realities
! scope="col"| Name
! scope="col"| First Appearance
! scope="col"| Notes
|-
|[[Earth-000001]]
|{{Wc|britishcomics|2000 AD Vol 1 2374|''2000 AD'' #2374}} (2024)
|A possible future of [[Earth-001]].

|-
|[[Earth-005]]
|[[Avengers Endgame: Encore]]
|Reality monitored by the TVA
as it faced an incursion.

|-
|[[Earth-16]]
|''[[Marvel Contest of Champions]]''
|The Age of Eternal Harmony
|}
"""

TRN = """intro
==Current TRNs==
* [[Earth-TRN001]] - {{cl|Shanna the She-Devil Vol 2}}
* [[Earth-TRN003]] - ''[[X-Men: Madness in Murderworld]]''
==Former TRNs==
* [[Earth-TRN002]] - now Earth-1234
"""


def test_parse_listing_rows_and_multiline_notes():
    rows = r.parse_listing(LISTING)
    assert [x["id"] for x in rows] == ["Earth-000001", "Earth-005", "Earth-16"]
    assert "incursion" in rows[1]["notes_raw"]
    assert rows[0]["first_raw"].startswith("{{Wc|britishcomics")
    assert all(x["kind"] == "numbered" for x in rows)


def test_year_is_taken_from_parentheses_not_titles():
    # The prototype read "2000 AD #2374 (2024)" as the year 2000.
    assert r._first_paren_year("2000 AD #2374 (2024)") == 2024
    assert r._first_paren_year("Superior Spider-Man Vol 1 33") is None


def test_parse_trn_only_current_section():
    rows = r.parse_trn(TRN)
    assert [x["id"] for x in rows] == ["Earth-TRN001", "Earth-TRN003"]
    assert rows[0]["kind"] == "temporary"


def test_reality_subcategory_pruning():
    assert r._skip_reality_subcat("Category:Earth-616")  # per-reality: characters, items...
    assert r._skip_reality_subcat("Category:Earth-616/Characters")
    assert not r._skip_reality_subcat("Category:Earth-616 Diverged Realities")
    assert not r._skip_reality_subcat("Category:Pocket Universes")
    assert r._skip_dimension_subcat("Category:Dimensional Rulers")
    assert not r._skip_dimension_subcat("Category:God Realms")
