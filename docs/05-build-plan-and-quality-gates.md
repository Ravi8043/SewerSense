# 05 — Build Plan and Quality Gates

## Rule for implementation agents

Implement in the order below. Do not begin frontend polish while a lower-level quality gate is failing. Make a small, verified commit-sized change at each step; preserve unrelated user changes.

## Phase 1 — Backend foundation

Create `config.py`, `db.py`, `schemas.py`, and `gazetteer.py`. Define models and Pydantic schemas before route code. Add `test_gazetteer.py` that verifies all locality, road, and landmark points remain inside the documented Hyderabad bounds.

**Gate:** the database initializes from an empty `backend/data/` directory, and gazetteer tests pass.

## Phase 2 — Deterministic synthetic data

Implement generator fixtures and templates. Build a commandable summary in `seed.py` or a narrowly scoped generator test which validates exact batch composition, hero requirements, out-of-scope count, duplicate candidates, and determinism across two calls.

**Gate:** two identical default batch calls yield equivalent report fields and the hero/special cases satisfy their declared properties.

## Phase 3 — Hybrid extraction

Implement the rule candidate extractor and the provider-neutral hybrid orchestrator together. Add a proprietary structured-LLM adapter, strictly typed request/response schema, cache, Pydantic validation, reconciliation logic, and the rules-only resilience mode. Test provider output with recorded/mocked JSON fixtures; do not require a real key to pass the suite. Cover source styles, vague landmark-only reports, locality-only reports, non-sewerage reports, durations, household counts, road obstruction, health risk, category mapping, typo disambiguation, invalid LLM JSON, invented locations, and conflicts with explicit rule matches.

**Gate:** valid LLM responses materially enrich ambiguous reports while every accepted location maps to the local gazetteer; malformed/unavailable LLM work deterministically falls back to rules; all result fields validate through Pydantic; the `none`/unlocated path remains clear. Implement the future open-source provider interface contract now, but do not add a model runtime until requested.

## Phase 4 — Intelligence pipeline

Implement TF-IDF similarity, duplicate rules, online clustering, aggregate recomputation, PCA corridor detection, velocity, priority, and confidence. Keep every weight/threshold in config. Add post-hoc test helpers for ARI/purity and guarantee `pipeline.py` never reads `truth_incident`.

**Gate:** default batch creates 15–19 incidents (tune toward 17); hero is a single high-priority escalating cluster; dangerous small incident gets ≥75; inflated one-handle incident stays below hero; four out-of-scope reports are excluded; print ARI and purity for diagnostics.

## Phase 5 — API, baseline, and reset

Build baseline seed using the exact same pipeline. Then add all `/api` endpoints. Test them against temporary SQLite. Profile `/api/simulate` after functionality, avoiding premature complexity.

**Gate:** every read/write route returns its documented schema; reset is idempotent; server simulation is under five seconds; summary values change only by database state.

## Phase 6 — Frontend foundation

Scaffold Vite/React/TypeScript/Tailwind. Add typed API client, app query/state layer, top bar, KPIs, queue, and Leaflet map. Wire to a running backend before visual refinement.

**Gate:** cold page load shows real baseline values, selects an incident, and does not show a blank state during latency or an API failure.

## Phase 7 — Intelligence details

Add card, SVG source mix and velocity, evidence drawer, brief modal, and template/LLM tagging. Verify data labels accurately distinguish reported and estimated values.

**Gate:** a reviewer can trace priority points to evidence, see duplicates count once, and verify the brief never treats assessment as confirmed fact.

## Phase 8 — Simulation and demo polish

Add the simulation overlay, changed-item tags, hero selection, raw report contrast toggle, map legend, and architecture modal. Use the API's actual result fields in every animated message.

**Gate:** a full simulation shows all stages, lands on the hero, and refreshes queue/KPIs/map within an understandable sequence.

## Phase 9 — Fresh-run verification

From a clean database and a fresh frontend build, perform the README demo script. Check console/network errors, map fallback behaviour, keyboard modal use, API error states, and a 1280 px viewport. Record known limitations honestly.

## Required automated verification

| Layer | Checks |
| --- | --- |
| Gazetteer | geographic bounds and fixture consistency |
| Generator | determinism, 100/96/4 batch composition, hero and special cases |
| Hybrid extractor | rule candidates, validated proprietary LLM fixtures, reconciliation/conflict tests, cache keys, rules-only fallback, category/location/flags/in-scope table tests |
| Pipeline | clustering band, hero, dangerous incident, inflated incident, out-of-scope, ARI/purity diagnostic |
| API | all route schemas, 404/422 paths, reset, simulation metrics |
| Frontend | type check/build; manual smoke test for initial load, simulation, evidence, brief, reset |

## Demo script for the completed README

1. Open the dashboard and point out baseline intelligence, queue, and heat.
2. Toggle `Show raw reports` briefly: this is the cluttered signal view.
3. Run simulation and narrate extraction, dedupe, clustering, and priority; land on the returned reports-to-incidents count.
4. Highlight heat, incident markers, and the hero corridor.
5. Open the hero card: complaints are not incidents; cite source mix, velocity, and factor explanations.
6. Open evidence: show factor bars, grey duplicate evidence, and grouping score reasons.
7. Select the small open-manhole incident: few reports can still warrant high priority.
8. Generate a response brief: distinguish confirmed reports from AI assessment.
9. Open Architecture: explain how production adapters, GIS, embeddings, and sensors can feed the layer later.

## Environment policy for this repository

- All generated project artefacts stay below `C:\Users\User\Desktop\SewerSense`.
- Use `backend/.venv` for backend execution. It currently uses Python 3.14.7 because Python 3.11 was not installed locally; write Python 3.11-compatible code.
- This preparation phase did not run any `pip` command. Do not install or upgrade pip. If dependencies are needed later, first follow the user's package-management direction rather than silently changing their environment.
