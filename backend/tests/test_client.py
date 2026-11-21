import httpx
import pytest

from ingest.client import ApiError, USER_AGENT, WikiClient


def test_user_agent_cache_and_retry(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    seen = []

    def handler(request):
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(503, headers={"Retry-After": "1"})
        return httpx.Response(200, json={"query": {"pages": []}})

    c = WikiClient(cache_dir=tmp_path, min_interval=0, transport=httpx.MockTransport(handler))
    assert c.get(action="query", titles="X") == {"query": {"pages": []}}
    assert len(seen) == 2 and seen[0].headers["User-Agent"] == USER_AGENT
    assert "arunangshu01@gmail.com" in USER_AGENT
    c.get(action="query", titles="X")  # served from cache
    assert len(seen) == 2 and c.cache_hits == 1


def test_api_errors_are_raised(tmp_path):
    t = httpx.MockTransport(lambda r: httpx.Response(200, json={"error": {"code": "badvalue", "info": "no"}}))
    with pytest.raises(ApiError):
        WikiClient(min_interval=0, transport=t).get(action="query")


def test_pages_merges_continuations_and_resolves_redirects():
    calls = []

    def handler(request):
        calls.append(dict(request.url.params))
        if "clcontinue" not in request.url.params:
            return httpx.Response(200, json={
                "continue": {"clcontinue": "1|B", "continue": "||"},
                "query": {"redirects": [{"from": "Old", "to": "New"}],
                          "pages": [{"title": "New", "categories": [{"title": "Category:A"}]}]}})
        return httpx.Response(200, json={"query": {"pages": [{"title": "New",
                                                              "categories": [{"title": "Category:B"}]}]}})

    c = WikiClient(min_interval=0, transport=httpx.MockTransport(handler))
    out = c.pages(["Old"], props="categories", content=False)
    assert out["Old"]["title"] == "New"
    assert [x["title"] for x in out["Old"]["categories"]] == ["Category:A", "Category:B"]
    assert len(calls) == 2
