# 00 — Project Charter

## Product statement

Build **SewerSense**, a locally running command-center demo for the Hyderabad Metropolitan Water Supply & Sewerage Board (HMWSSB). The system converts fragmented, synthetic sewerage reports into a smaller queue of explainable, geolocated operational incidents.

The core distinction is non-negotiable:

> A complaint is a signal. An incident is the real-world problem described by one or more signals.

SewerSense sits above existing complaint-management and GIS tools. It improves triage and explanation; it never claims to replace those systems.

## Demo outcome

At a 1440×900 desktop viewport, an operator can:

1. See database-derived KPIs, an incident queue, a dark map, and an initially selected incident.
2. Inspect why that incident has its priority, confidence, corridor, source mix, and trend.
3. Reveal report-level evidence and the reason reports were clustered together.
4. Run one simulated 100-report batch and watch the UI explain the pipeline stages.
5. Land on the Kukatpally / Road No. 5 hero incident, which is critical, rapidly escalating, and represented by an approximately 100–140 m corridor.
6. Generate a response brief that visibly separates reported facts from AI assessment and says it must be verified before action.

## Mandatory scope

- Deterministic synthetic complaint generation with hidden ground truth for tests only.
- Hybrid extraction: deterministic rules plus a constrained, cached proprietary-LLM structured extractor when its API key is configured. Rules-only operation is an explicit no-key resilience mode, not the intended enriched mode. A provider adapter prepares a later open-source model replacement.
- In-memory computation plus SQLite persistence: deduplicate, cluster, detect corridor, calculate velocity, priority, and confidence.
- FastAPI API, React/Vite/TypeScript command center, Leaflet map, evidence drawer, brief modal, simulation overlay, and architecture modal.
- A deterministic template response brief when no LLM key is configured or the LLM fails.
- Optional only after the MVP: status controls, category/status filter chips, and compact confidence badges.

## Explicit exclusions

Do not add authentication, real complaint ingestion, live social or WhatsApp integrations, queues, Redis, Celery, PostGIS, Kubernetes, vector databases, training, Telugu NLP, mobile clients, IoT ingestion, road-network snapping, user management, notifications, or any real PII.

The architecture view may show future IoT and live adapters, but no corresponding implementation is permitted in the MVP.

## Operating constraints

| Constraint | Required implementation response |
| --- | --- |
| Fully local demo | Works without API keys and without network access, apart from optional map tiles. |
| Synthetic data only | UI and README permanently label the demo data; use fabricated handles, no phone numbers or people. |
| Explainable priority | Persist factor values, weights, contributions, and human-readable sentences. |
| Truth isolation | `truth_incident` is generated and test-only. `pipeline.py` must never access or import it. |
| No hard-coded KPIs | `/api/summary` calculates all counts from SQLite on every request. |
| Fast simulation | Server-side `/api/simulate` completes in under five seconds on the 100-report batch. |
| Geospatial honesty | Coordinates and road polylines are illustrative; estimates are labelled as such. |
| Dependency hygiene | Do not install or upgrade `pip`. Keep all project-generated files inside this repository. |

## Acceptance checklist

The MVP is complete only when all of the following are demonstrated:

- Baseline data loads and produces about 35–45 mixed-status incidents.
- Simulating 100 reports produces 15–19 incidents, with 17 as the preferred deterministic result.
- The hero has at least 40 reports, at least 28 independent sources, a single cluster, priority at least 80, and a rapidly escalating label.
- The small school-adjacent open manhole has only three reports yet ranks in the top five and has priority at least 75 because of the severity floor.
- The high-volume, one-handle incident shows low independent-source count and ranks beneath the hero.
- Duplicates remain visible as evidence but do not inflate volume, velocity, or unique sources.
- Evidence can trace every displayed priority number to reports and factor contributions.
- Brief facts use only supplied data; impact estimates and recommendations are visibly labelled AI assessment.

Details of how these conditions are implemented and tested live in the later documents.
