import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import API_COMMON_PREFIX
from app.store import Store
from ingest import build
from ingest.realities import Issue, Result

P = API_COMMON_PREFIX


def reality(rid, **kw):
    base = {
        "id": rid, "page_title": rid, "template": "Reality Template", "kind": "numbered", "types": [],
        "status": "existing", "status_field": "Existing", "needs_number": False, "in_listing": True,
        "listing_kind": "numbered", "name": None, "designation": None, "aliases": [], "creators": [],
        "medium": "Comics", "medium_format": "comic", "medium_source": "first appearance (Comic Template)",
        "first_appearance": None, "first_work": None, "first_source": "page", "first_year": None,
        "year_source": None, "description": None, "description_shortened": False, "description_source": None,
        "listing_note": None, "listing_first": None, "parents": [], "destroyed_by": [], "home_reality": None,
        "categories": [], "qid": None, "revid": 1, "last_edited": None, "bucket_size": None,
        "sources": [{"label": f"Marvel Database: {rid}", "url": f"https://marvel.fandom.com/wiki/{rid}",
                     "permalink": None}],
    }
    base.update(kw)
    return base


def sample_result() -> Result:
    res = Result()
    res.realities = [
        reality("Earth-616", name="Earth-616", first_appearance="Ka-Zar (Manvis) Vol 1 1", first_year=1936,
                description="The primary continuity.", aliases=["Prime Marvel Universe"]),
        reality("Earth-199999", medium="Film", medium_format="feature film", first_year=2008,
                first_work="Iron Man (film)", name="Marvel Cinematic Universe", description="The MCU."),
        reality("Earth-92131", medium="Animation", first_year=1992, name="X-Men: The Animated Series"),
        reality("Earth-1048", medium="Games", medium_source="reviewed override (tie-in novel)", first_year=2018),
        reality("Earth-838", medium="Film", first_year=2022),
        reality("Earth-10005", medium="Film", first_year=2011),
        reality("Earth-26496", medium="Animation", first_year=2008),
        reality("Earth-1610", first_year=2000),
        reality("Earth-TRN734", kind="temporary", listing_kind="temporary", medium="Film", first_year=2019,
                types=["diverged", "time_travel"], parents=["Earth-199999"]),
        reality("Earth-10530", page_title=None, status="undocumented", sources=[
            {"label": "Marvel Database: Multiverse/Universe Listing", "url": "https://marvel.fandom.com/wiki/x",
             "permalink": None}]),
        reality("Dark Dimension", kind="dimension", template="Location Template", in_listing=False,
                listing_kind=None, types=["hell"], status="unknown", first_year=1964),
        reality("Earth-Unknown", kind="bucket", status="bucket", medium="Unclassified", page_title=None,
                bucket_size=924),
    ]
    res.places = [{"id": "Mines of Andvari", "name": "Mines of Andvari", "dimension": "Dark Dimension",
                   "reality": "Earth-616", "first_appearance": None, "url": "u", "revid": 2}]
    res.links = [
        {"src": "Earth-TRN734", "dst": "Earth-199999", "relation": "diverged_from", "evidence": "category"},
        {"src": "Earth-616", "dst": "Earth-1610", "relation": "mentions", "evidence": "notes"},
        {"src": "Earth-616A", "dst": "Earth-616", "relation": "redirects_to", "evidence": "redirect"},
    ]
    res.issues = [Issue("Peter Parker (Earth-616)", "classify", "rejected: character page", "Character Template"),
                  Issue("Earth-10530", "coverage", "listed reality has no wiki page yet", "")]
    res.meta = {"listing": {"official_rows": 9, "trn_rows": 1}}
    return res


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    """Tests never call real LLM providers (keys from backend/.env are ignored)."""
    from app import settings
    monkeypatch.setattr(settings, "GROQ_API_KEY", None)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory):
    from ingest import graph_build
    from tests.graph_fixture import sample_graph, write_appearances
    d = tmp_path_factory.mktemp("data")
    report = build.build(sample_result(), d, "test", "2026-11-21T00:00:00+00:00")
    assert report["published"], report["checks"]
    g, apps = sample_graph()
    write_appearances(d / "runs" / "graph-test" / "clean", apps)
    report = graph_build.build_graph_db(g, d, "graph-test", "test", "2026-11-21T00:00:00+00:00")
    assert report["published"], report["checks"]
    return d / "serve"


@pytest.fixture(scope="session")
def client(data_dir):
    store = Store(data_dir)
    store.load()
    with TestClient(create_app(store)) as c:
        yield c
