# AGENTS.md

## Layout
- `backend/`: FastAPI app in `app/` (`api/`, `store.py`, `settings.py`), ingest pipeline in `ingest/`, tests in `tests/`. Run commands from `backend/`.
  - `ingest/client.py` polite MediaWiki client (User-Agent, 1 req/s, retries/backoff, gzip response cache = raw snapshot, resumable by `--run-id`).
  - `ingest/realities.py` listings + category crawl -> accept/reject by infobox template -> classify; `ingest/media.py` work-page medium; `ingest/taxonomy.py` category -> tag maps; `ingest/wikidata.py` SPARQL.
  - `ingest/build.py` JSONL -> Parquet + DuckDB, quality checks; publishes `data/serve/latest.json` only if no check fails.
  - `ingest/overrides.json` reviewed medium overrides (evidence required); `ingest/schema_baseline.json` known infobox fields (drift detection).
- `frontend/`: React 18 + Vite + Jest/Testing Library. Run commands from `frontend/`.
- `prototype/`: approved single-file UI preview (design spec) and early scripts. Don't edit; port from it.
- `backend/data/` (git-ignored): `runs/<run_id>/cache|clean|report.json`, `serve/*.duckdb`, `serve/latest.json`.

## Verify before committing
```bash
cd backend && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest -q
cd frontend && npm test && npm run build
```
Real-data runs (from `backend/`; responses are cached per run id, so re-runs resume):
```bash
.venv/bin/python -m ingest realities --run-id <rid>                        # ~15-20 min cold
.venv/bin/python -m ingest graph-fetch --run-id <gid>                      # ~5,700 API calls, ~1.5 h at 1 req/s
.venv/bin/python -m ingest graph --run-id <gid> --realities-run <rid>      # parse + build from the cache, a few minutes; publishes latest.json
.venv/bin/python -m eval.run [--llm]                                       # 57-question evaluation on the snapshot
```
Console LLM keys (optional; without them the rule planner answers): put `GROQ_API_KEY` / `GEMINI_API_KEY` in `backend/.env` (git-ignored). Tests force them off.
Golden fixture (recorded real responses for well-known realities): `.venv/bin/python -m tests.fixtures.make_golden --run-id <id>`; regenerate when the pipeline starts reading new fields.

## Conventions
- Accuracy first: never invent facts, counts or links. Every record carries `sources` (page URL + `?oldid=` permalink). Unknown stays unknown ("Status not stated", "Unclassified"), never guessed.
- Nothing is dropped silently: rejected or unclassifiable pages go to `ingest_issues` with a reason and show on `/coverage`.
- Medium comes from the first-appearance page's infobox template (and its series page / Wikidata for animation), then the listing's link, then comic-issue naming for unwritten pages; keywords are a last resort and labelled "low confidence". Overrides need evidence in `overrides.json`.
- Knowledge graph (`ingest/graph.py`, `ingest/graph_build.py`): characters, teams/orgs, events, works, story `appearances` (role featured/supporting/antagonist/other + flags), `relations` (each with evidence page + field), `variant_groups` (the wiki's disambiguation rule, `assign_groups`), `names` (resolution). "Fought" = opposite roles in the same story (never mentions/images/visions) or opposite event sides; "same side" = both featured/supporting; both are computed at query time (`tools.pairs_sql`) and always cite stories. Character profiles (`graph.character_profile`: origin, birthplace, occupation, named powers/abilities, death, History opener) and `killed_by` relations come straight from infobox fields, shortened, never rewritten.
- Console (`app/qa/`): `resolve` names -> plan (LLM JSON tool call or SQL, else `router` rules) -> `tools` (typed, parameterised SQL) or `sqlguard` (single SELECT, whitelisted tables, no table functions, 200 rows, 3 s) -> answer built only from rows (LLM SQL answers pass `engine.verify`, else a table answer). Add a tool = function + `TOOLS` entry + router rule + eval questions (`eval/questions.json`, 80 now). Relationship tools: `opponents` (optional medium, falls back to the variant that appears in it), `allies`, `relationship`, `first_fight`, `deaths`, `origin`, `who_appears`.
- A rebuild can reuse another run's response cache: `mkdir data/runs/<new> && ln -s ../<old>/cache data/runs/<new>/cache`.
- Golden realities (`build.GOLDEN_MEDIUM`, `tests/test_golden.py`) must keep their medium; the build refuses to publish otherwise or if row counts drop more than 2%.
- Fandom web pages return 403 to scripts; use `api.php` only. Comic pages carry hundreds of `/Appearances` categories, so fetch them without `prop=categories`.
- All routes are under `API_COMMON_PREFIX = "/multiverse/api/v1"` (`backend/app/settings.py`); the frontend mirrors it in `src/api/client.js`, Vite proxies `/multiverse/api`. Firebase must rewrite `/multiverse/api/**`. Change all together.
- No UI/icon/graph libraries in the frontend; graph is plain SVG. Artwork is procedural (`lib/media.js::art`), never wiki or Marvel images.
- Footer disclaimer + data credits on every page (`components/Footer.jsx`); never put "Marvel" in the name, logo or domain.
- Use plain ASCII hyphens, not em/en dashes, in code, UI copy and docs.
- New dependencies: pin versions published at least 7 days ago. Never commit secrets; ask before creating or changing cloud resources.

## Visual checks
Check desktop (1440), tablet (~820) and phone (~390) after UI changes. Headless Chrome enforces a ~500px minimum window, so for phone shots load the page in a 390px-wide iframe.

## Deployment
- Firebase Hosting `ask-the-multiverse` + Cloud Run `multiverse-api` (asia-south1, scale to zero, max 1) + bucket `<project>-multiverse-data` in a dedicated GCP project; guide in `docs/deploy-gcp.md`.
- The API downloads `serve/latest.json` and the DuckDB it names from the bucket at start-up and re-checks every 15 min (`app/snapshot.py`, `MULTIVERSE_SNAPSHOT_BUCKET`); unset locally.
- `.github/workflows/deploy.yml` runs after successful push CI on `main`, waits for the GitHub `production` environment approval (the user approves, never the assistant), keyless WIF. `sync.yml` (weekly + manual) rebuilds the data with its own WIF pool and service account that can only write the data bucket; it uploads the database first and the pointer last, and the graph build compares row counts with the live snapshot (`serve/published.json`).
- `backend/tests/test_deployment.py` keeps prefix, site, service, bucket and account names consistent; update it with any deploy change. Keep the guards that refuse the portfolio/mahakal/doppel/flowbench projects.
- `scripts/smoke.py <origin> [--api-only]` is the post-deploy smoke test (stdlib only).
- MCU timeline (`ingest/mcu.py`): phases from the MCU Wiki `{{Phase}}` infoboxes; titles link to Marvel Database works only by exact title (or exact title minus a "(film)"-style qualifier with Earth-199999 evidence). Unlinked titles go to `graph_issues` (stage `mcu`), never guessed.
- Ask before creating or changing cloud resources; never ask for secrets in chat.
