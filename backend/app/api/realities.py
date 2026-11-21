"""Reality, dimension and realm endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request

from app.settings import MAX_PAGE

router = APIRouter()

KIND_ORDER = ("numbered", "temporary", "variant_suffix", "named", "dimension", "realm", "bucket")
LIST_COLUMNS = """id, name, kind, types, status, medium, medium_format, medium_source, first_appearance,
    first_year, description, in_listing, listing_kind, page_title, bucket_size,
    sources[1].url AS url"""
SORTS = {
    "designation": f"""list_position({list(KIND_ORDER)}, kind),
        TRY_CAST(regexp_extract(id, '-(?:TRN)?(\\d+)', 1) AS BIGINT) NULLS LAST, id""",
    "year": "first_year NULLS LAST, id",
    "described": "(description IS NULL), length(coalesce(description, '')) DESC, id",
}


def _store(request: Request):
    return request.app.state.store


def _filters(q, medium, kind, type_, status):
    where, params = [], []
    if q:
        where.append("""(id ILIKE $q OR coalesce(name, '') ILIKE $q OR array_to_string(aliases, ' ') ILIKE $q
            OR coalesce(description, '') ILIKE $q OR coalesce(listing_note, '') ILIKE $q
            OR coalesce(first_appearance, '') ILIKE $q)""")
        params.append(("q", f"%{q.strip()}%"))
    for col, values in (("medium", medium), ("kind", kind), ("status", status)):
        vals = [v for v in (values or "").split(",") if v]
        if vals:
            where.append(f"{col} IN ({', '.join('$' + col + str(i) for i in range(len(vals)))})")
            params += [(f"{col}{i}", v) for i, v in enumerate(vals)]
    if type_:
        where.append("list_contains(types, $type)")
        params.append(("type", type_))
    return where, dict(params)


@router.get("/realities")
def list_realities(request: Request, q: str | None = Query(None, max_length=120),
                   medium: str | None = None, kind: str | None = None,
                   type: str | None = None, status: str | None = None,
                   sort: Literal["designation", "year", "described"] = "designation",
                   offset: int = Query(0, ge=0), limit: int = Query(60, ge=1, le=MAX_PAGE)):
    """Search and filter every reality, dimension and realm. `medium`, `kind`
    and `status` accept comma-separated values."""
    store = _store(request)
    where, params = _filters(q, medium, kind, type, status)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    total = store.scalar(f"SELECT count(*) FROM realities {clause}", params)
    items = store.rows(f"SELECT {LIST_COLUMNS} FROM realities {clause} ORDER BY {SORTS[sort]} "
                       f"LIMIT {limit} OFFSET {offset}", params)
    # Facet counts ignore the medium filter so the chips can show every medium.
    fwhere, fparams = _filters(q, None, kind, type, status)
    fclause = f"WHERE {' AND '.join(fwhere)}" if fwhere else ""
    facets = store.rows(f"SELECT medium, count(*) AS n FROM realities {fclause} GROUP BY 1 ORDER BY 2 DESC",
                        fparams)
    return {"total": total, "offset": offset, "limit": limit, "items": items,
            "facets": {"medium": {f["medium"]: f["n"] for f in facets}}}


@router.get("/realities/{rid:path}")
def get_reality(request: Request, rid: str):
    store = _store(request)
    row = store.one("SELECT * EXCLUDE (categories) FROM realities WHERE id = $id", {"id": rid})
    if not row:
        alias = store.one("SELECT dst FROM reality_links WHERE src = $id AND relation = 'redirects_to'",
                          {"id": rid})
        if alias:
            return {"redirect": alias["dst"]}
        raise HTTPException(404, f"{rid} is not in the index")
    brief = "id, name, kind, medium, first_year, status"
    row["parents"] = [store.one(f"SELECT {brief} FROM realities WHERE id = $p", {"p": p}) or
                      {"id": p, "name": None, "missing": True} for p in row["parents"]]
    children = store.rows(f"""SELECT {brief}, l.relation FROM reality_links l JOIN realities r ON r.id = l.src
        WHERE l.dst = $id AND l.relation IN ('diverged_from', 'warped_from', 'dimension_of')
        ORDER BY r.first_year NULLS LAST, r.id""", {"id": rid})
    related = store.rows(f"""SELECT DISTINCT {brief} FROM reality_links l
        JOIN realities r ON r.id = CASE WHEN l.src = $id THEN l.dst ELSE l.src END
        WHERE l.relation = 'mentions' AND (l.src = $id OR l.dst = $id) ORDER BY r.id LIMIT 24""", {"id": rid})
    places = store.rows("SELECT id, name, url FROM places WHERE dimension = $id ORDER BY name LIMIT 60",
                        {"id": rid})
    places_total = store.scalar("SELECT count(*) FROM places WHERE dimension = $id", {"id": rid})
    return {**row, "children": children, "related": related, "places": places, "places_total": places_total}
