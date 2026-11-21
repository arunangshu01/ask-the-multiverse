"""Check LLM-written SQL before it runs: one SELECT, whitelisted tables only,
no table functions or file access, wrapped in a row limit, with a time limit."""

from __future__ import annotations

import json
import threading

import duckdb

ALLOWED_TABLES = {"realities", "places", "reality_links", "characters", "teams", "events", "works", "relations",
                  "appearances", "variant_groups", "entities", "appearance_counts"}
BLOCKED_FUNCTIONS = ("read_", "glob", "getenv", "current_setting", "duckdb_", "pragma_", "sniff_", "parquet_",
                     "query", "export", "copy", "load", "install", "attach")
MAX_ROWS = 200
TIMEOUT_S = 3.0

SCHEMA_DOC = """Tables (DuckDB SQL, read-only):
realities(id, name, kind, types VARCHAR[], status, medium, first_appearance, first_year, description, parents VARCHAR[])
characters(id, name, current_alias, aliases VARCHAR[], reality, gender, first_appearance, first_work, creators VARCHAR[], variant_group,
    origin, place_of_birth, citizenship, occupation VARCHAR[], base VARCHAR[], marital_status, powers VARCHAR[],
    abilities VARCHAR[], death, cause_of_death)  -- profile text as written on the wiki infobox
teams(id, kind, name, reality, first_appearance, first_work, creators VARCHAR[])
events(id, name, reality, first_appearance, last_appearance)
works(id, kind, medium, series, year)   -- comic issues, episodes, films, games, novels
appearances(work, story, entity, role, flags VARCHAR[])  -- role: featured|supporting|antagonist|other
relations(src, dst, type, note, evidence, field)  -- type: member|former_member|leader|former_leader|ally|enemy|
    parent|child|sibling|spouse|relative|clone|event_protagonist|event_antagonist|event_other|
    killed_by (src = the character who died, dst = the killer listed on its page)
entities(id, kind, label, name, reality, url)   -- all characters, teams, organizations, events
appearance_counts(entity, works, present)
variant_groups(id, main, members VARCHAR[])
Ids are wiki page titles such as 'Thanos (Earth-616)' or 'Avengers (Earth-616)'."""


class UnsafeQuery(ValueError):
    pass


def _walk(node, tables: set, functions: set):
    if isinstance(node, dict):
        if node.get("type") == "BASE_TABLE":
            tables.add((node.get("catalog_name") or node.get("schema_name") or "", node.get("table_name", "")))
        if node.get("type") == "TABLE_FUNCTION":
            functions.add("<table function>")
        if node.get("class") == "FUNCTION" or node.get("type") == "FUNCTION":
            functions.add(str(node.get("function_name", "")).lower())
        for v in node.values():
            _walk(v, tables, functions)
    elif isinstance(node, list):
        for v in node:
            _walk(v, tables, functions)


def validate(con: duckdb.DuckDBPyConnection, sql: str) -> str:
    sql = sql.strip().rstrip(";").strip()
    if not sql or ";" in sql:
        raise UnsafeQuery("exactly one statement is allowed")
    raw = con.execute("SELECT json_serialize_sql(?::VARCHAR)", [sql]).fetchone()[0]
    ast = json.loads(raw)
    if ast.get("error"):
        raise UnsafeQuery(f"not a valid read-only SELECT: {ast.get('error_message', '')[:200]}")
    stmts = ast.get("statements", [])
    if len(stmts) != 1:
        raise UnsafeQuery("exactly one SELECT statement is allowed")
    tables, functions = set(), set()
    _walk(stmts[0], tables, functions)
    ctes = set()
    _collect_ctes(stmts[0], ctes)
    bad = sorted(f"{s}.{t}" if s else t for s, t in tables if (s and s != "main") or (t not in ALLOWED_TABLES and t not in ctes))
    if bad:
        raise UnsafeQuery(f"tables not allowed: {', '.join(bad)}")
    blocked = sorted(f for f in functions if f == "<table function>" or f.startswith(BLOCKED_FUNCTIONS))
    if blocked:
        raise UnsafeQuery(f"functions not allowed: {', '.join(blocked)}")
    return f"SELECT * FROM (\n{sql}\n) AS q LIMIT {MAX_ROWS}"


def _collect_ctes(node, out: set):
    if isinstance(node, dict):
        cte = node.get("cte_map")
        if isinstance(cte, dict):
            for item in cte.get("map", []):
                if isinstance(item, dict) and "key" in item:
                    out.add(item["key"])
        for v in node.values():
            _collect_ctes(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect_ctes(v, out)


def run(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    """Validate and execute with a time limit; returns rows as dicts."""
    safe = validate(con, sql)
    timer = threading.Timer(TIMEOUT_S, con.interrupt)
    timer.start()
    try:
        res = con.execute(safe)
        cols = [d[0] for d in res.description]
        return [dict(zip(cols, r)) for r in res.fetchall()]
    except duckdb.InterruptException as exc:
        raise UnsafeQuery(f"query took longer than {TIMEOUT_S:.0f} s") from exc
    finally:
        timer.cancel()
