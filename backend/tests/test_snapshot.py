import json

import httpx

from app import snapshot
from app.store import Store


def _transport(state):
    def handler(req: httpx.Request):
        if req.url.host == "metadata.google.internal":
            assert req.headers["Metadata-Flavor"] == "Google"
            return httpx.Response(200, json={"access_token": "tok"})
        assert req.headers["Authorization"] == "Bearer tok"
        name = req.url.path.rsplit("/o/", 1)[1]
        state["calls"].append(name)
        if name == "serve%2Flatest.json" or name == "serve/latest.json":
            return httpx.Response(200, json=state["pointer"])
        return httpx.Response(200, content=state["files"][name.split("%2F")[-1].split("/")[-1]])
    return httpx.MockTransport(handler)


def test_sync_downloads_db_then_pointer_and_skips_when_unchanged(tmp_path, data_dir):
    src = next(p for p in data_dir.glob("*.duckdb"))
    pointer = json.loads((data_dir / "latest.json").read_text())
    state = {"calls": [], "pointer": pointer, "files": {pointer["db"]: src.read_bytes()}}
    out = tmp_path / "serve"
    assert snapshot.sync("bkt", "serve", out, httpx.Client(transport=_transport(state))) is True
    assert (out / pointer["db"]).read_bytes() == src.read_bytes()
    assert json.loads((out / "latest.json").read_text())["db"] == pointer["db"]
    store = Store(out)
    store.load()
    assert store.scalar("SELECT count(*) FROM realities") > 0
    state["calls"].clear()
    assert snapshot.sync("bkt", "serve", out, httpx.Client(transport=_transport(state))) is False
    assert len(state["calls"]) == 1  # only the pointer was checked
