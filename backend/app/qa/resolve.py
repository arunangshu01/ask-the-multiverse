"""Resolve names in a question ("Thanos", "the X-Men", "Earth-616") to page ids."""

from __future__ import annotations

import re

from app.store import Store

REALITY_ID = re.compile(r"\b((?:Earth|Moira|Jubilee)-(?:TRN)?[\w.]+)\b", re.I)
REALITY_NICKNAMES = {"mcu": "Earth-199999", "marvel cinematic universe": "Earth-199999", "616": "Earth-616",
                     "ultimate universe": "Earth-1610", "x-men '97": "Earth-92131", "insomniac": "Earth-1048"}
KIND_ORDER = {"character": 0, "team": 1, "organization": 2, "event": 3, "appearance label": 4}


def _clean(name: str) -> str:
    name = re.sub(r"^(the|a|an)\s+", "", name.strip().strip("?.!,\"'"), flags=re.I)
    return re.sub(r"\s+", " ", name).lower()


def reality_id(store: Store, text: str) -> str | None:
    m = REALITY_ID.search(text)
    if m:
        row = store.one("SELECT id FROM realities WHERE lower(id) = lower($id)", {"id": m.group(1)})
        return row["id"] if row else m.group(1)
    low = text.lower()
    for nick, rid in REALITY_NICKNAMES.items():
        if re.search(rf"\b{re.escape(nick)}\b", low):
            return rid
    row = store.one("SELECT id FROM realities WHERE lower(name) = $n OR lower(id) = $n LIMIT 1", {"n": _clean(text)})
    return row["id"] if row else None


def candidates(store: Store, name: str, kinds: tuple[str, ...] | None = None, reality: str | None = None,
               limit: int = 8) -> list[dict]:
    """Entities whose name, alias or page title matches `name`, best first: exact page id,
    then kind order, then the requested reality (default Earth-616), then appearances."""
    n = full = _clean(name)
    if not n:
        return []
    m = re.match(r"^(.*?)\s*\(((?:earth|moira|jubilee)-[^)]+)\)$", n)
    if m:
        n, reality = m.group(1), m.group(2)
    kinds = kinds or ("character", "team", "organization", "event")
    rows = store.rows(f"""
        SELECT e.id, e.kind, e.label, e.name, e.reality, e.url, coalesce(c.present, 0) AS appearances,
               min(CASE WHEN nm.source IN ('name', 'title', 'current alias') THEN 0
                        WHEN nm.source = 'alias' THEN 1 ELSE 2 END) AS via_label,
               max(CASE WHEN lower(e.id) = $full THEN 1 ELSE 0 END) AS exact_id
        FROM names nm JOIN entities e ON e.id = nm.entity
        LEFT JOIN appearance_counts c ON c.entity = e.id
        WHERE nm.name = $n AND e.kind IN ({", ".join(f"'{k}'" for k in kinds)})
        GROUP BY e.id, e.kind, e.label, e.name, e.reality, e.url, c.present
        ORDER BY exact_id DESC,
                 (1 + appearances) * CASE via_label WHEN 0 THEN 1.0 WHEN 1 THEN 0.1 ELSE 0.3 END
                   * CASE WHEN lower(e.reality) = lower($r) THEN 3 ELSE 1 END DESC, e.id
        LIMIT {int(limit)}""", {"n": n, "full": full, "r": reality or "Earth-616"})
    return rows


def best(store: Store, name: str, kinds=None, reality=None) -> tuple[dict | None, list[dict]]:
    found = candidates(store, name, kinds, reality)
    return (found[0] if found else None), found[1:5]


def spans(store: Store, question: str, max_words: int = 5) -> list[dict]:
    """Every 1-5 word span of the question that is a known name (used as LLM hints)."""
    words = re.findall(r"[\w'.\-]+", question)
    grams = {" ".join(words[i:j]).lower() for i in range(len(words)) for j in range(i + 1, min(len(words), i + max_words) + 1)}
    grams = {g for g in grams if len(g) > 2 and g not in {"the", "and", "who", "has", "have", "both", "been", "also"}}
    if not grams:
        return []
    found = store.rows("""SELECT nm.name AS span, count(DISTINCT nm.entity) AS matches FROM names nm
        WHERE nm.name IN (SELECT unnest($g)) GROUP BY 1 ORDER BY length(nm.name) DESC LIMIT 12""", {"g": sorted(grams)})
    out = []
    for f in found:  # the same ranking the tools use, so the LLM sees the entity a tool would pick
        top = candidates(store, f["span"], limit=1)
        if top:
            out.append({**f, "top_entity": top[0]["id"], "kind": top[0]["kind"]})
    return out
