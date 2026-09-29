# 01 — System Architecture

## Design approach

Use a deliberately small, local architecture. FastAPI owns persistence and all intelligence calculations; React owns presentation and client-side animation only. SQLite is sufficient for the demo but its fields must be shaped so a later PostGIS migration is straightforward.

```text
Synthetic report generator
        │
        ▼
Rule candidate extractor + proprietary-LLM structured extractor
        │                   │
        └── validation and deterministic reconciliation ─┘
        │
        ▼
Deduplication → online incident clustering → incident recomputation
        │                              │
        ▼                              ▼
  unlocated / out-of-scope       corridor, velocity, priority, confidence
        │                              │
        └──────────────┬───────────────┘
                       ▼
                 SQLite database
                       │
                       ▼
              FastAPI `/api/*` routes
                       │
                       ▼
    React command center, Leaflet map, evidence and brief modals
```

The frontend never recalculates priority, confidence, clustering, or KPIs. It renders server responses. The only intentional client-side illusion is a minimum ~600 ms display time per simulation stage so the pipeline can be understood even when the server is fast.

## Target repository layout

```text
SewerSense/
├── README.md
├── Makefile
├── docs/
├── backend/
│   ├── .venv/                     # local only; ignored by Git
│   ├── requirements.txt
│   ├── seed.py
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── schemas.py
│   │   ├── gazetteer.py
│   │   ├── generator.py
│   │   ├── extract.py
│   │   ├── extraction_providers/
│   │   │   ├── base.py
│   │   │   ├── proprietary.py
│   │   │   └── open_source.py
│   │   ├── pipeline.py
│   │   ├── brief.py
│   │   └── main.py
│   ├── data/                      # SQLite database and LLM cache; ignored where generated
│   └── tests/
│       ├── test_gazetteer.py
│       ├── test_extract.py
│       ├── test_pipeline.py
│       └── test_api.py
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── tailwind.config.ts
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── api.ts
        ├── types.ts
        ├── styles.css
        └── components/
            ├── TopBar.tsx
            ├── KpiStrip.tsx
            ├── IncidentQueue.tsx
            ├── CommandMap.tsx
            ├── IncidentCard.tsx
            ├── EvidenceDrawer.tsx
            ├── BriefModal.tsx
            ├── SimulationOverlay.tsx
            ├── ArchitectureModal.tsx
            └── shared.tsx
```

## Backend module responsibilities

| Module | Owns | Must not own |
| --- | --- | --- |
| `config.py` | environment variables, score weights, thresholds, paths, static limits | business logic scattered elsewhere |
| `db.py` | SQLAlchemy engine/session, models, schema lifecycle, transaction helpers | pipeline decisions |
| `schemas.py` | Pydantic request/response/extraction validation types | database ORM behaviour |
| `gazetteer.py` | locality/road/landmark fixtures and geographic utility lookup | generated reports |
| `generator.py` | deterministic synthetic raw reports and hidden test truth | extraction or clustering |
| `extract.py` | hybrid orchestration: rule candidates, provider request, Pydantic validation, reconciliation, cache | determining incident identity or silently trusting unvalidated LLM output |
| `extraction_providers/` | vendor-specific proprietary model adapter now; open-source adapter later | pipeline-facing schemas or business rules |
| `pipeline.py` | ordered dedupe, cluster assignment, incident aggregate calculations | HTTP and UI formatting |
| `brief.py` | strict fact payload assembly, LLM call, deterministic fallback | querying arbitrary database state |
| `main.py` | FastAPI lifespan, CORS, route orchestration, errors | numerical logic |

## Request and persistence lifecycle

### Baseline reset / first seed

`seed.py` clears and creates the local database, builds approximately 300 reports over three days, sends every report through the same extractor and pipeline used in simulation, then assigns a small deterministic mix of incident statuses. It never inserts pre-computed incidents directly.

### Simulate

`POST /api/simulate` captures a single UTC `now`, calls `generate_batch(n=100, now=now, hero=True)`, persists raw reports, performs hybrid extraction, dedupe, clustering, and aggregate recomputation in time order, commits once, and returns stage metrics plus incident identifiers. The frontend uses those identifiers to flash changed queue items and select the hero. When no proprietary key is configured, extraction runs in its explicit rule-resilience mode and reports that provenance internally; the rest of the demo still works.

### Operator actions

`POST /api/incidents/{id}/status` validates a transition target from `open`, `verified`, `dispatched`, or `resolved`, persists it, and returns the canonical status. Closing an incident prevents future reports from attaching to it because online clustering compares against open incidents only.

## Architectural invariants

- All timestamp handling is timezone-aware UTC in storage and API. The UI may format local display time.
- A report stays immutable after extraction except for `is_duplicate`, `duplicate_of`, `incident_id`, stored scoring details, and batch association.
- An incident is a derived aggregate. After a new assignment, recalculate all derived fields from its member reports instead of incrementally guessing values.
- `truth_incident` is unavailable to `pipeline.py`; use a separate test helper to join it only after the pipeline output is finalized.
- API payloads are typed Pydantic schemas and use one naming convention throughout (recommended: `snake_case`).
- LLM output is never applied until it passes a strict schema and deterministic reconciliation with the gazetteer/rule candidates.
- Failure of proprietary LLM work can never prevent a local demo from functioning; it produces a traceable rules-only result instead.
- Changing from the proprietary adapter to an open-source adapter cannot change the normalized extraction schema consumed by the pipeline.

## Future migration boundaries

SQLite coordinate fields and JSON blobs make the MVP simple. A future system can move reports/incidents to PostGIS, replace haversine selection with spatial indexes, feed live ingestion adapters into the same extraction schema, and replace TF-IDF with embeddings without changing the frontend contract. Those migrations are deliberately out of scope for this build.
