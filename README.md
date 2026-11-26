Fan-made project. Not affiliated with or endorsed by Marvel or Disney. All characters and related names are trademarks of their respective owners.

# Ask the Multiverse

A cinematic, cited explorer of every documented reality, dimension and realm in the Marvel multiverse,
built from the [Marvel Database](https://marvel.fandom.com/) and the
[MCU Wiki](https://marvelcinematicuniverse.fandom.com/) on Fandom (CC BY-SA) and [Wikidata](https://www.wikidata.org/) (CC0). Every entry links to the exact wiki page (and revision) it came from.

A Q&A bot over a Marvel knowledge graph: ask "Who has fought both Thanos and Galactus?" and an LLM (Groq, Gemini
fallback) turns the question into a typed graph query or a checked read-only DuckDB SELECT; the answer is built only
from the returned rows and links to the exact wiki pages used. An evaluation set (80 questions) scores plan and
answer accuracy.

- ETL: Marvel Database MediaWiki API + Wikidata SPARQL -> raw response cache -> Parquet -> DuckDB.
- Graph: 106k characters (with origin, birthplace, powers, deaths), 12k teams/organisations, 387 events, 78k works, 985k story appearances, 168k sourced relationships (incl. 11k "killed by"), 8k variant groups, 5.5k realities/dimensions/realms, and the MCU timeline (6 phases, 71 titles).
- Console questions: origins and powers, who fought whom (and when first), allies, how two characters are connected, deaths, variants, teams and overlaps, family, creators, who appears in a story, reality facts and counts.
- UI: cinematic opening sequence, featured realities, Multiverse Console with live steps + generated query + sources, connections star-map with search across every reality, MCU timeline, poster rows, full index, coverage and credits pages.
- Hosting: Firebase Hosting + Cloud Run (scale to zero) + a GCS data bucket, deployed by GitHub Actions with keyless Workload Identity Federation; a weekly sync rebuilds the data and publishes it only if every quality check passes. See `docs/deploy-gcp.md`.

## Run locally

```bash
# backend (Python 3.12)
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m ingest realities --run-id local          # ~15-20 min at 1 request/s; resumable
.venv/bin/python -m ingest graph-fetch --run-id graph         # ~1.5 h; resumable
.venv/bin/python -m ingest graph --run-id graph --realities-run local   # also fetches the MCU Wiki phase pages
.venv/bin/python -m eval.run                                  # evaluation set
.venv/bin/uvicorn app.main:app --port 8000                    # optional: GROQ_API_KEY / GEMINI_API_KEY in backend/.env

# frontend
cd frontend && npm ci && npm run dev                   # http://localhost:5173

# after a deploy
python3 scripts/smoke.py https://multiverse.arunangshupramanik.com
```

`prototype/` holds the approved single-file UI preview and the early data scripts.

## Data and licences

- Code: MIT (`LICENSE`).
- Data: derived from the Marvel Database and shared under CC BY-SA 3.0; see `DATA_LICENSE.md`.
- No Marvel logos, film stills, official artwork or wiki images are used; artwork is generated.
- Non-commercial: no ads, no paid tiers.
