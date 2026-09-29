# 06 — Agent Handoff

## Purpose

This document is the entry point for a coding agent continuing SewerSense. It makes the current state, constraints, and next safe action explicit.

## Current repository state

- **MVP implemented and verified (2026-09-29).** Backend (FastAPI + SQLite pipeline, hybrid extraction with provider adapters, brief generation) and frontend (React/Vite/TypeScript/Tailwind + Leaflet command center) are complete; see the README for run instructions, the demo script, acceptance results, and deliberate deviations.
- Verification: `backend/tests` (72 tests: gazetteer, generator, extraction with provider fixtures, pipeline acceptance criteria with ARI/purity, brief safety, every API route) pass; `npm run typecheck` and `npm run build` pass; the full demo flow was exercised in a browser against the running API.
- `backend/.venv` uses Python 3.14.7 with the packages in `backend/requirements.txt` installed; pip itself was not upgraded. Code stays Python 3.11-compatible.
- The live LLM path has only been tested with recorded fixtures (no key is bundled). Set `ANTHROPIC_API_KEY` to exercise it.
- Optional post-MVP items already present: status controls and queue filter chips. Not implemented: anything in the charter's exclusion list.

## Required reading

Read these files in order before editing code:

1. `README.md`
2. `docs/00-project-charter.md`
3. `docs/01-system-architecture.md`
4. `docs/02-data-and-intelligence-pipeline.md`
5. `docs/03-backend-api-and-storage.md`
6. `docs/04-command-center-frontend.md`
7. `docs/05-build-plan-and-quality-gates.md`
8. `docs/07-hybrid-extraction-design.md`

The pasted build specification is reflected in these documents. If a later coding choice conflicts with them, preserve the charter and pipeline invariants unless the user changes scope.

## Next safe actions

The build phases in `05-build-plan-and-quality-gates.md` are complete. Further work should start by running the test suite, then make small verified changes. Tune clustering or scoring only through `backend/app/config.py` constants and re-run `pytest` (the acceptance tests print ARI/purity).

## Non-negotiable implementation rules

- Never use `truth_incident` in runtime pipeline code. It is test evaluation data only.
- Never hard-code summary KPIs or simulation results in the frontend.
- Never turn duplicate evidence into independent volume, velocity, or source count.
- Never label household estimates or AI assessment as confirmed.
- Never omit the `DEMO DATA` UI badge or imply data is live.
- Never add excluded systems/features merely because they are common in production architectures.
- Keep all tunable numerical values in `config.py` and all API shapes in Pydantic plus TypeScript types.
- Build hybrid extraction as the normal enriched path: rules produce grounded candidates and the proprietary LLM returns structured semantic interpretation. Preserve a no-key, no-network rules-only resilience path, with explicit provenance.
- Keep proprietary and future open-source model code behind the same provider interface; neither may change the normalized extraction contract used by the pipeline.

## Completion evidence an agent must provide

For each implemented phase, report changed files, test command(s) run, observed outcome, and any intentional deviation. Before calling the MVP complete, include:

- generator/pipeline test output including ARI and the required special-case assertions;
- API test output for all endpoints;
- frontend type-check/build result;
- a manual demo walkthrough covering simulation, hero selection, evidence, brief fallback, reset, and error/loading states;
- known limitations, particularly illustrative geography and synthetic-only data.
