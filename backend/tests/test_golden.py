"""Runs the full realities pipeline offline on recorded real API responses
(tests/fixtures/golden.json.gz, made by tests/fixtures/make_golden.py)."""

import gzip
import json
from pathlib import Path

import pytest

from ingest import build
from ingest import realities as r

FIXTURE = Path(__file__).parent / "fixtures" / "golden.json.gz"


class FixtureSource:
    def __init__(self, data):
        self.d = data

    def wikitext(self, title):
        text, meta = self.d["wikitext"][title]
        return text, meta

    def category_members(self, category):
        return self.d["categories"].get(category, [])

    def pages(self, titles, props="revisions|categories|templates|info", content=True):
        store = self.d["pages"].get(props, {})
        return {t: store[t] for t in titles if t in store}

    def category_size(self, category):
        return self.d["category_size"][category]

    def animated_imdb_ids(self, ids):
        return set(self.d["animated_imdb"])

    def animated_fandom_titles(self, titles):
        return set(self.d["animated_fandom"])

    def animated_by_label(self, films):
        return dict(self.d["animated_label"])

    def marvel_fandom_ids(self):
        return dict(self.d["qids"])

    def counters(self):
        return {"api_calls": 0, "cache_hits": 0, "wikidata_calls": 0}


@pytest.fixture(scope="module")
def result():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as fh:
        return r.run(FixtureSource(json.load(fh)))


@pytest.fixture(scope="module")
def by_id(result):
    return {x["id"]: x for x in result.realities}


@pytest.mark.parametrize("rid,medium", sorted(build.GOLDEN_MEDIUM.items()) + [
    ("Earth-65", "Comics"), ("Earth-65B", "Animation"), ("Earth-96283", "Film"), ("Earth-000001", "Comics")])
def test_golden_medium(by_id, rid, medium):
    assert by_id[rid]["medium"] == medium, by_id[rid]["medium_source"]


def test_medium_evidence_is_recorded(by_id):
    assert by_id["Earth-199999"]["first_work"] == "Iron Man (film)"
    assert by_id["Earth-199999"]["medium_source"] == "first appearance (Film Template)"
    assert by_id["Earth-92131"]["medium_format"] == "episode (animated series)"
    assert "animated per" in by_id["Earth-65B"]["medium_source"]
    assert by_id["Earth-1048"]["medium_source"].startswith("reviewed override")
    assert by_id["Earth-000001"]["medium_source"].startswith("first appearance (external britishcomics")


def test_years_come_from_structured_fields(by_id):
    # "2000 AD #2374 (2024)": the year is 2024, not 2000 (prototype bug)
    assert by_id["Earth-000001"]["first_year"] == 2024
    assert by_id["Earth-199999"]["first_year"] == 2008
    assert by_id["Earth-199999"]["year_source"] == "wiki debut category"


def test_kinds_types_status_and_parents(by_id, result):
    assert by_id["Moira-1"]["kind"] == "named" and by_id["Moira-1"]["status"] == "destroyed"
    assert by_id["Moira-1"]["parents"] == ["Earth-616"]
    assert by_id["Earth-65B"]["kind"] == "variant_suffix"
    trn = by_id["Earth-TRN734"]
    assert trn["kind"] == "temporary" and {"diverged", "time_travel"} <= set(trn["types"])
    assert trn["parents"] == ["Earth-199999"]
    assert by_id["Earth-10530"]["status"] == "undocumented" and by_id["Earth-10530"]["page_title"] is None
    assert by_id["Earth-Unknown"]["kind"] == "bucket" and by_id["Earth-Unknown"]["bucket_size"] > 0
    assert {"src": "Earth-TRN734", "dst": "Earth-199999", "relation": "diverged_from",
            "evidence": "category or infobox"} in result.links


def test_dimensions_realms_and_places(by_id, result):
    assert by_id["Negative Zone"]["kind"] == "dimension"  # its Dimension field names itself
    assert by_id["Dark Dimension"]["kind"] == "realm" and "hell" in by_id["Dark Dimension"]["types"]
    assert by_id["Asgard (Realm)"]["kind"] == "realm" and "god_realm" in by_id["Asgard (Realm)"]["types"]
    assert by_id["Limbo (Otherplace)"]["kind"] == "realm"
    places = {p["id"]: p for p in result.places}
    assert places["Mines of Andvari"]["dimension"] == "Asgard (Realm)"
    assert "Hildebrandt Wood" in places and "Hildebrandt Wood" not in by_id


def test_non_reality_pages_are_rejected_with_reason(result, by_id):
    issues = {(i.page, i.reason) for i in result.issues}
    assert ("Abner Jenkins (Earth-TRN566)", "rejected: character page") in issues
    assert "Abner Jenkins (Earth-TRN566)" not in by_id
    assert ("Framework", "listed reality page uses unexpected template") in issues
    assert by_id["Framework"]["page_title"] == "Framework" and by_id["Framework"]["status"] == "unknown"


def test_every_row_links_to_its_source(by_id):
    mcu = by_id["Earth-199999"]["sources"]
    assert mcu[0]["url"] == "https://marvel.fandom.com/wiki/Earth-199999"
    assert "?oldid=" in mcu[0]["permalink"]
    assert any("Multiverse/Universe_Listing" in s["url"] for s in mcu)
    assert all(row["sources"] for row in by_id.values())
