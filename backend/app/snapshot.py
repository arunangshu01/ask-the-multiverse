"""Fetch the published DuckDB snapshot from Google Cloud Storage.

The sync workflow uploads `<prefix>/multiverse-<run>.duckdb` and then `<prefix>/latest.json`
(the pointer, written last). On Cloud Run the API downloads both at startup and re-checks the
pointer every few minutes, so new data goes live without a redeploy. Uses the GCS JSON API with
the service account token from the metadata server, so no Google client library is needed."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib.parse import quote

import httpx

log = logging.getLogger("app.snapshot")
METADATA_TOKEN = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
GCS = "https://storage.googleapis.com/storage/v1/b/{bucket}/o/{name}?alt=media"


def _token(client: httpx.Client) -> str:
    r = client.get(METADATA_TOKEN, headers={"Metadata-Flavor": "Google"}, timeout=5)
    r.raise_for_status()
    return r.json()["access_token"]


def _url(bucket: str, name: str) -> str:
    return GCS.format(bucket=bucket, name=quote(name, safe=""))


def fetch_pointer(bucket: str, prefix: str, c: httpx.Client) -> dict:
    r = c.get(_url(bucket, f"{prefix}/latest.json"), headers={"Authorization": f"Bearer {_token(c)}"}, timeout=20)
    r.raise_for_status()
    return r.json()


def sync(bucket: str, prefix: str, data_dir: Path, client: httpx.Client | None = None) -> bool:
    """Make data_dir hold the published snapshot. Returns True when latest.json changed.
    The database is downloaded to a temp name first, and latest.json is replaced only after it."""
    data_dir.mkdir(parents=True, exist_ok=True)
    with client or httpx.Client() as c:
        pointer = fetch_pointer(bucket, prefix, c)
        local = data_dir / "latest.json"
        if local.exists() and json.loads(local.read_text()).get("db") == pointer["db"]:
            return False
        db = data_dir / pointer["db"]
        if not db.exists():
            tmp = db.with_suffix(".part")
            with c.stream("GET", _url(bucket, f"{prefix}/{pointer['db']}"),
                          headers={"Authorization": f"Bearer {_token(c)}"}, timeout=300) as r:
                r.raise_for_status()
                with tmp.open("wb") as fh:
                    for chunk in r.iter_bytes(1 << 20):
                        fh.write(chunk)
            tmp.replace(db)
        local.write_text(json.dumps(pointer))
        log.info("snapshot %s ready (%s)", pointer.get("run_id"), pointer["db"])
        return True
