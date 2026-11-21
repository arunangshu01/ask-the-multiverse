from tests.conftest import P, sample_result
from ingest import build


def test_health_and_prefix(client):
    assert client.get(f"{P}/health").json() == {"status": "ok"}
    paths = client.get(f"{P}/openapi.json").json()["paths"]
    assert paths and all(p.startswith(P) for p in paths)


def test_list_filters_sort_and_facets(client):
    body = client.get(f"{P}/realities", params={"limit": 5}).json()
    assert body["total"] == 12 and len(body["items"]) == 5
    assert body["items"][0]["id"] == "Earth-616"  # numbered first, by number
    film = client.get(f"{P}/realities", params={"medium": "Film,Animation"}).json()
    assert {i["medium"] for i in film["items"]} == {"Film", "Animation"} and film["total"] == 6
    assert film["facets"]["medium"]["Comics"] >= 3  # facets ignore the medium filter
    years = [i["first_year"] for i in client.get(f"{P}/realities", params={"sort": "year"}).json()["items"]]
    known = [y for y in years if y is not None]
    assert known == sorted(known) and years[-1] is None
    assert client.get(f"{P}/realities", params={"q": "prime marvel"}).json()["items"][0]["id"] == "Earth-616"
    assert client.get(f"{P}/realities", params={"type": "time_travel"}).json()["total"] == 1
    assert client.get(f"{P}/realities", params={"status": "undocumented"}).json()["total"] == 1
    assert client.get(f"{P}/realities", params={"limit": 1000}).status_code == 422


def test_detail_parents_children_related_places_and_sources(client):
    mcu = client.get(f"{P}/realities/Earth-199999").json()
    assert [c["id"] for c in mcu["children"]] == ["Earth-TRN734"]
    trn = client.get(f"{P}/realities/Earth-TRN734").json()
    assert trn["parents"][0]["id"] == "Earth-199999"
    assert trn["sources"][0]["url"].startswith("https://marvel.fandom.com/wiki/")
    assert [r["id"] for r in client.get(f"{P}/realities/Earth-1610").json()["related"]] == ["Earth-616"]
    dark = client.get(f"{P}/realities/Dark%20Dimension").json()
    assert dark["places_total"] == 1 and dark["places"][0]["id"] == "Mines of Andvari"
    assert client.get(f"{P}/realities/Earth-616A").json() == {"redirect": "Earth-616"}
    assert client.get(f"{P}/realities/Earth-0").status_code == 404


def test_stats_coverage_credits(client):
    s = client.get(f"{P}/stats").json()
    assert s["total"] == 12 and s["by_medium"]["Film"] == 4 and s["by_kind"]["bucket"] == 1
    assert s["by_status"]["undocumented"] == 1 and s["synced_at"]
    cov = client.get(f"{P}/coverage", params={"stage": "classify"}).json()
    assert cov["total"] == 1 and cov["items"][0]["reason"] == "rejected: character page"
    assert any(c["check"] == "golden realities keep their medium" for c in cov["checks"])
    assert cov["overrides"][0]["id"] == "Earth-1048"
    cred = client.get(f"{P}/credits").json()
    assert cred["data"] == "CC BY-SA 3.0 (Unported)" and "Not affiliated" in cred["disclaimer"]


def test_build_refuses_to_publish_when_golden_medium_regresses(tmp_path):
    res = sample_result()
    next(r for r in res.realities if r["id"] == "Earth-92131")["medium"] = "Comics"
    report = build.build(res, tmp_path, "bad", "now")
    assert not report["published"]
    assert not (tmp_path / "serve" / "latest.json").exists()


def test_build_refuses_large_row_drop(tmp_path):
    assert build.build(sample_result(), tmp_path, "one", "now")["published"]
    res = sample_result()
    res.realities = [r for r in res.realities if r["id"] in build.GOLDEN_MEDIUM]  # 12 -> 9 rows
    report = build.build(res, tmp_path, "two", "now")
    assert not report["published"]
    assert any(c["status"] == "fail" and "row count" in c["check"] for c in report["checks"])
