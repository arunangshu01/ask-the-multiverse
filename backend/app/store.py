"""Read-only access to the DuckDB snapshot named by latest.json."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import duckdb


class DataUnavailable(RuntimeError):
    pass


class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self._lock = threading.Lock()
        self._con: duckdb.DuckDBPyConnection | None = None
        self.snapshot: dict = {}

    def load(self) -> None:
        pointer = self.data_dir / "latest.json"
        if not pointer.exists():
            raise DataUnavailable(f"no snapshot in {self.data_dir}; run `python -m ingest realities`")
        snap = json.loads(pointer.read_text())
        con = duckdb.connect(str(self.data_dir / snap["db"]), read_only=True)
        con.execute("SET enable_external_access = false")
        with self._lock:
            old, self._con, self.snapshot = self._con, con, snap
        if old:
            old.close()

    def cursor(self) -> duckdb.DuckDBPyConnection:
        with self._lock:
            if self._con is None:
                raise DataUnavailable("snapshot not loaded")
            return self._con.cursor()

    def rows(self, sql: str, params: list | None = None) -> list[dict]:
        cur = self.cursor()
        try:
            res = cur.execute(sql, params or [])
            cols = [d[0] for d in res.description]
            return [dict(zip(cols, r)) for r in res.fetchall()]
        finally:
            cur.close()

    def one(self, sql: str, params: list | None = None) -> dict | None:
        found = self.rows(sql, params)
        return found[0] if found else None

    def scalar(self, sql: str, params: list | None = None):
        cur = self.cursor()
        try:
            row = cur.execute(sql, params or []).fetchone()
            return row[0] if row else None
        finally:
            cur.close()
