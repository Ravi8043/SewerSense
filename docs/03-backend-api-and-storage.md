# 03 — Backend API and Storage

## Runtime and configuration

Use FastAPI, pip, SQLAlchemy/SQLite, scikit-learn TF-IDF/cosine similarity, and NumPy PCA. Keep dependency declarations in `backend/requirements.txt`; do not execute package installation or pip-upgrade commands as part of this documentation milestone.

All tunable values live in `app/config.py`: database/cache paths, CORS origins, clustering coefficients/threshold, duplicate threshold, corridor parameters, priority weights, simulation size, and LLM settings. Read `GROQ_LLM_KEY`, `LLM_MODEL` (default `any qwen open source model`), `USE_LLM_EXTRACTION`, and an embeddings mode from environment variables only. Never include credentials in source, seed data, API responses, or logs.

The local virtual environment is `backend/.venv`; see the README for the exact local runtime note.

## SQLite schema

Use SQLAlchemy models with a migration-free `create_all` approach for this one-day demo. Include an internal `report_cluster_details_json` field (or equivalent normalized table) for score explainability; it is required by the evidence endpoint even though it was not present in the high-level table.

### `reports`

| Column | Notes |
| --- | --- |
| `id` | text primary key, deterministic UUID or prefixed identifier |
| `source`, `source_handle`, `raw_text`, `created_at` | original synthetic signal and UTC time |
| `category`, `road`, `landmark`, `locality` | extractor output |
| `lat`, `lon`, `geo_quality` | null coordinates permitted for `none` |
| `duration_hours`, `severity`, `households` | extracted values; severity is 1–5 |
| `road_blocked`, `health_risk`, `near_sensitive`, `in_scope` | booleans and sensitive-place descriptor |
| `is_duplicate`, `duplicate_of`, `incident_id`, `batch_id` | pipeline relationships and audit fields |
| `truth_incident` | generator test-only field; never selected by pipeline logic |
| `cluster_score`, `cluster_details_json` | stored score and four components for evidence |

### `incidents`

| Column | Notes |
| --- | --- |
| identity/category/title/location | `id`, `category`, `locality`, `road`, `title`, centroid latitude/longitude |
| spatial | `corridor_json`, `radius_m` |
| timing/counts | first/last report time, count, unique sources, source mix JSON |
| operational facts | estimated households, road blocked, health risk |
| explainability | velocity JSON, priority, priority factors JSON, confidence, confidence reasons JSON |
| lifecycle | status (`open`, `verified`, `dispatched`, `resolved`), creation time |

JSON fields use stable Pydantic-compatible structures and never opaque Python repr strings. The seed script must recreate the schema/database in an idempotent, explicit manner.

## Endpoint contract

All routes live under `/api`, return JSON, and return consistent HTTP errors with `detail`. The compact incident representation omits long evidence and raw report text. Full incident and evidence routes return only incident-associated data.

### Read endpoints

| Method and path | Purpose | Response requirements |
| --- | --- | --- |
| `GET /api/summary` | KPI strip | `reports_today`, `active_incidents`, `critical`, `escalating`, `resolved`, `unlocated`, all computed from database state |
| `GET /api/incidents?status=&min_priority=` | queue and map | sorted priority-desc compact incidents; validate filters and return empty array, not an error, when no rows match |
| `GET /api/incidents/{id}` | selected intelligence card | full derived incident including factor summaries, velocity, confidence, corridor/radius, and status |
| `GET /api/incidents/{id}/evidence` | evidence drawer | factor bars, representative reports, stored cluster score aggregates/reasons |
| `GET /api/heatmap` | map heat layer | `[[lat, lon, weight], ...]`; omit null locations and report weights based on its incident priority |

Return `404` for an unknown incident ID. Keep report snippets out of the compact queue payload so map/queue polling stays fast.

### Write endpoints

#### `POST /api/simulate`

No body. Process exactly one new 100-report batch and return:

```json
{
  "batch_id": "batch-2026-09-29T12:00:00Z",
  "received": 100,
  "out_of_scope": 4,
  "duplicates": 8,
  "located": 91,
  "incidents_before": 40,
  "incidents_after": 57,
  "new_incident_ids": ["HYD-182"],
  "updated_incident_ids": ["HYD-145"],
  "stages": [
    {"name": "Reports received", "count": 100, "ms": 4},
    {"name": "Classifying", "count": 96, "ms": 12}
  ],
  "hero_incident_id": "HYD-182"
}
```

The example identifiers/counts are illustrative except `received=100` and `out_of_scope=4`. `stages` must cover receiving, classifying, extracting locations, finding duplicates, clustering incidents, and calculating priority. Timings measure server work; frontend readability delays are not included.

#### `POST /api/incidents/{id}/brief`

No body for MVP. Build a minimal fact-only source payload from the selected incident and its five representative reports. Return:

```json
{
  "facts": ["..."],
  "assessment": ["..."],
  "recommended_next_step": "AI suggestion: ...",
  "generated_by": "template"
}
```

`generated_by` is `llm` only for a successfully validated model response. The output never claims a cause, invents a number, or treats an estimate as confirmed. Include a UI footer rather than a hidden API field: `AI-generated. Verify before action.`

#### `POST /api/incidents/{id}/status`

Accept a Pydantic body:

```json
{ "status": "verified" }
```

Only allow the four documented statuses. Return the canonical compact or full updated status object. Invalid status returns `422`; missing incident returns `404`.

#### `POST /api/reset`

Rebuild the deterministic baseline using `seed.py` functionality, then return a fresh summary and optionally the selected default incident ID. This endpoint lets the frontend recover from successive demo runs without hard-coded data.

## Brief-generation safety

`brief.py` first creates a constrained fact payload containing only values from the incident and its representative report texts. Its LLM system instruction says: use supplied facts only; do not invent numbers, people, causes, or actions claimed as complete; mark recommendations as AI suggestions; distinguish reports from estimates. Validate model JSON against Pydantic and fall back to a deterministic template on every failure.

The template follows the same response shape and has two semantic groups:

- `facts`: report count, independent sources, reported location, dates, source types, direct safety cues.
- `assessment`: estimated household impact, velocity interpretation, confidence wording, verification-first recommendation, caveats.

## Backend tests

Write pure-function tests for gazetteer bounds, extraction samples, pipeline properties, and brief template safety. Add API tests using a temporary SQLite file and FastAPI's test client. Route tests must exercise every endpoint, unknown incident behavior, invalid status validation, reset idempotency, and simulate timing/count fields.
