# SewerSense

SewerSense is a local, synthetic-data command-center demo for HMWSSB. It turns many fragmented sewerage complaints into a smaller set of explainable, geolocated incidents for an operator to assess. It is an intelligence layer above existing complaint and GIS systems; it does not replace them.

> **A complaint is a signal. An incident is the real-world problem described by one or more signals.**

## Non-production data notice

All complaints, locations, handles, road geometry, and incident data are **synthetic**. The interface permanently displays a `DEMO DATA` badge. Road names, road geometry, and landmarks are illustrative fixtures, not authoritative HMWSSB or GIS data. No real people, phone numbers, or PII exist anywhere in the project.

## Quick start (Windows PowerShell)

Prerequisites: Python 3.11+ (the project venv uses 3.14) and Node 18+.

```powershell
# 1. Backend dependencies into the project-local venv (does not upgrade pip)
& .\backend\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r backend\requirements.txt

# 2. Frontend dependencies
npm --prefix frontend install

# 3. Start the API (seeds the baseline automatically on first start) — http://localhost:8000
& .\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --port 8000

# 4. In a second terminal, start the command center — http://localhost:5173
npm --prefix frontend run dev
```

If `backend\.venv` does not exist, create it first with `python -m venv backend\.venv`. On macOS/Linux use `backend/.venv/bin/python`; a `Makefile` wraps the same commands (`make install`, `make backend`, `make frontend`, `make test`).

Rebuild the database at any time with `cd backend; ..\backend\.venv\Scripts\python.exe seed.py` (add `--simulate` to also run one batch), or with the **Reset demo** button.

### Optional: hybrid LLM extraction

Without a key the demo runs in **rules mode** — deterministic, offline, and fully functional. To enable the enriched hybrid path, set a key before starting the API:

```powershell
$env:ANTHROPIC_API_KEY = "<your key>"      # never commit it
$env:LLM_MODEL = "claude-sonnet-5"         # default from the spec; claude-sonnet-5-5 is the current Sonnet
```

The top bar shows `Extraction: hybrid (rules + LLM)` or `Extraction: rules mode`. See `backend/.env.example` for timeout, concurrency, and latency-budget settings. The same key also enables LLM-written response briefs (validated; template fallback on any failure).

## Demo script (≈5 minutes)

1. **Baseline** — KPIs, the priority-sorted queue, heat (report density) and incident markers on the dark map. Everything is computed from SQLite.
2. **Show raw reports** (map, top right) — each dot is one complaint signal; the caption contrasts ~250 signals with ~35 incidents.
3. **Simulate incoming complaints** — 100 synthetic reports pass through *received → classifying → extracting locations → finding duplicates → clustering → calculating priority* with real server counts and timings, landing on **100 REPORTS → 18 INCIDENTS** (17 new, 1 update to an existing incident).
4. **The hero** — *Overflow — Road No. 5, Kukatpally* is auto-selected: CRITICAL (~94), rapidly escalating, 46 reports from 38 independent sources, 8 repeat posts counted once, a ~127 m estimated corridor near Kukatpally Government School.
5. **View evidence** — every priority point traced to a factor (value × weight), the stored grouping scores (content, proximity, recency, category), representative reports, and muted duplicates labelled *counted once*.
6. **Hafeezpet Road, Miyapur** (#2 in the queue) — only **3 reports**, yet priority 75: an open manhole beside a school triggers the severity floor. Few reports can still be urgent.
7. **Generate response brief** — *Reported facts* vs *AI assessment* in separate blocks; estimates labelled; *AI-generated. Verify before action.*
8. **Architecture** — how live complaint systems, social adapters, GIS, embeddings, and sensors could feed the same extraction contract later (marked *Future*).
9. **Reset demo** to return to the baseline for the next run.

## How the acceptance criteria are met

Measured by `backend/tests` on the deterministic data (rules mode):

| Criterion | Result |
| --- | --- |
| Baseline produces ~35–45 mixed-status incidents | 39 incidents: open, verified, dispatched, resolved |
| 100-report simulation → 15–19 incidents (17 preferred) | **17 new incidents** (18 touched); ARI 0.97, purity 1.00 |
| Hero: ≥40 reports, ≥28 sources, one cluster, priority ≥80, rapidly escalating | 46 reports, 38 sources, single cluster, priority 94, RAPIDLY ESCALATING, 127 m corridor |
| School-adjacent open manhole: 3 reports, top five, priority ≥75 via floor | 3 reports, priority 75 (base 36 + severity floor), rank #2 |
| One-handle high-volume incident ranks beneath the hero | 10 reports, 1 independent source, priority 19 |
| Duplicates are evidence, not volume | 8 hero reposts linked to originals; excluded from sources, velocity, and households |
| Four out-of-scope reports excluded | garbage, water pressure, spam, streetlight — stored for audit, never clustered |
| Priority traceable to reports and factors | 8 stored factors (value, weight, contribution, sentence) sum to the base priority |
| Brief separates facts from AI assessment | template tested to use only numbers present in the fact payload |
| `/api/simulate` under 5 s | ~0.9 s server time |

## Architecture

```text
generator.py ─► IncomingReport (no ground truth)
                     │
           extract.py: rule candidates ─► provider adapter (LLM, optional) ─► Pydantic validation ─► reconciliation ─► cache
                     │
           pipeline.py: dedupe (same handle, TF-IDF > 0.8) ─► online clustering (score ≥ 0.55 vs active incidents)
                        ─► recompute incident: PCA corridor, velocity, priority (8 factors + severity floor), confidence
                     │
                  SQLite ─► FastAPI /api/* ─► React + Leaflet command center
```

- **Truth isolation** — the pipeline's input type (`IncomingReport`) has no ground-truth field, and `pipeline.py` reads/writes an explicit column list that excludes it. `service.py` records generator truth only after a batch is committed, purely for test metrics (ARI/purity in `tests/evaluation.py`). The hero incident returned by `/api/simulate` is chosen from pipeline output (highest-priority touched incident).
- **Hybrid extraction** — rules produce grounded candidates; the LLM (when configured) may only choose among allowed gazetteer values, cannot supply coordinates or invent numbers, and an explicit safety cue such as *open manhole* is never overridden. LLM calls run concurrently under a wall-clock budget (default 3.5 s per batch); stragglers, timeouts, invalid JSON, refusals and missing keys all fall back to rules with recorded provenance. Provider code lives only in `app/extraction_providers/` (Anthropic adapter now; open-source adapter interface stubbed).
- **Explainability** — per-report grouping scores and their four components, per-incident factor contributions and sentences, confidence reasons, and extraction provenance are persisted and rendered as stored — the browser never recomputes them.

API (all JSON, errors as `{"detail": ...}`): `GET /api/summary`, `GET /api/incidents?status=&min_priority=` (`status` also accepts `active`), `GET /api/incidents/{id}`, `GET /api/incidents/{id}/evidence`, `GET /api/heatmap`, `POST /api/simulate`, `POST /api/incidents/{id}/brief`, `POST /api/incidents/{id}/status`, `POST /api/reset`, `GET /api/health`. Interactive docs at http://localhost:8000/docs.

## Tests and verification

```powershell
cd backend; ..\backend\.venv\Scripts\python.exe -m pytest -q      # 72 tests, no key or network needed
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Tests cover gazetteer bounds, generator determinism and composition, the rule/LLM extraction matrix using recorded provider fixtures (valid enrichment, typo disambiguation, invented places, coordinates in LLM output, malformed responses, number conflicts, the open-manhole rule, cache keys, the latency budget), all pipeline acceptance criteria, template-brief number safety, and every API route including 404/422 paths, reset idempotency and simulate timing.

## Implementation notes and deliberate deviations from `docs/`

| Spec | Implementation | Why |
| --- | --- | --- |
| SQLAlchemy models | Standard-library `sqlite3` with an explicit schema (`app/db.py`) | Fewer dependencies; same tables and a PostGIS-friendly shape |
| scikit-learn TF-IDF, NumPy PCA | Pure-Python smooth-IDF TF-IDF and closed-form 2×2 PCA (`app/pipeline.py`) | Identical maths, no heavy wheels on Python 3.14 |
| CARTO dark basemap | Esri Dark Gray Canvas by default; any URL via `VITE_TILE_URL` | CARTO now returns an *API key required* tile for keyless requests |
| `sim_geo` distance | Distance to the incident *footprint* (centroid or nearest precisely located member); locality-level positions get a 350 m uncertainty allowance | Linear corridors otherwise split at their ends; locality mentions are genuinely imprecise |
| Velocity labels | Fewer than 3 reports in the 6-hour window → STEADY | Two reports cannot establish a trend |
| — | Device location pins (WhatsApp/field/portal) as optional report metadata, used only if within 350 m of the text-named place | Gives exact reports the 5–25 m jitter the spec describes, without trusting pins blindly |
| "Reports today" | Rolling last 24 hours | Stable during a demo that crosses midnight |

## Known limitations

- Geography and data are synthetic and illustrative; corridors are statistical estimates, not network-snapped pipe segments.
- Household numbers are estimates (`est.`) derived from report claims, independent sources, and corridor length.
- Online clustering is order-dependent; a vague locality-only report can occasionally attach to a nearby compatible incident (1 of 96 in the demo batch).
- The live LLM path is covered by fixture tests; it has not been exercised against the real API in this repository because no key is bundled.
- SQLite with a process-level write lock is sized for a single-machine demo, not concurrent production load.
- Desktop-only layout (designed for 1440×900, readable at 1280 px).

## Project documents

The implementation packet in `docs/` remains the source of truth for scope and intent: [charter](docs/00-project-charter.md), [architecture](docs/01-system-architecture.md), [pipeline](docs/02-data-and-intelligence-pipeline.md), [API and storage](docs/03-backend-api-and-storage.md), [frontend](docs/04-command-center-frontend.md), [build plan](docs/05-build-plan-and-quality-gates.md), [agent handoff](docs/06-agent-handoff.md), [hybrid extraction](docs/07-hybrid-extraction-design.md).
