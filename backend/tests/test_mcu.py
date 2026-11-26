from ingest import mcu
from tests.graph_fixture import PHASE_ONE


class StubMcuWiki:
    """Answers action=query&redirects=1 like the MCU Wiki API does."""
    HOPS = {"Team_Thor": "Team Thor", "Team Thor": "Marvel One-Shot: Team Thor: Part 1",
            "Team Thor: Part 1": "Marvel One-Shot: Team Thor: Part 1"}

    def get(self, **params):
        titles = params["titles"].split("|")
        hops = [{"from": t, "to": self.HOPS[t]} for t in titles if t in self.HOPS]
        return {"query": {"redirects": hops}}


def test_parse_phase_infobox():
    phase, entries = mcu.parse_phase("Phase One", PHASE_ONE, 7)
    assert (phase["order"], phase["saga"], phase["start_year"], phase["end_year"]) == (1, "The Infinity Saga", 2008, 2012)
    assert [(e["kind"], e["title"], e["mcu_page"]) for e in entries] == [
        ("film", "Iron Man", "Iron Man (film)"), ("film", "The Avengers", "The Avengers"),
        ("one-shot", "The Consultant", "Marvel One-Shot: The Consultant")]


def test_mcu_field_links_through_redirects_on_both_sides():
    entries = [{"mcu_page": "Team Thor: Part 1"}, {"mcu_page": "The Avengers"}, {"mcu_page": "Item 47"}]
    works = [{"id": "Team Thor", "kind": "short film", "mcu": "Team Thor"},
             {"id": "Marvel's The Avengers", "kind": "film", "mcu": "The Avengers"},
             {"id": "Team Thor (comic)", "kind": "comic", "mcu": "Team Thor"}]  # not a film: ignored
    mcu.attach_mcu_links(StubMcuWiki(), entries, works)
    assert [e["mcu_links"] for e in entries] == [["Team Thor"], ["Marvel's The Avengers"], []]
