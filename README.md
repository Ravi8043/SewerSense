# SewerSense

SewerSense is a local, synthetic-data command-center demo for HMWSSB. It turns many fragmented sewerage complaints into a smaller set of explainable, geolocated incidents for an operator to assess. It is an intelligence layer above existing complaint and GIS systems; it does not replace them.

This repository intentionally begins with an implementation packet rather than partially built application code. The packet is the source of truth for every subsequent coding task, so another coding agent can resume work without reconstructing decisions from chat history.

## Read in this order

1. [Project charter](docs/00-project-charter.md) — scope, constraints, and demo outcomes.
2. [System architecture](docs/01-system-architecture.md) — module boundaries, repository structure, and data flow.
3. [Data and intelligence pipeline](docs/02-data-and-intelligence-pipeline.md) — synthetic generator, extraction, clustering, scoring, and explainability.
4. [Backend API and storage](docs/03-backend-api-and-storage.md) — database schema and endpoint contracts.
5. [Command-center frontend](docs/04-command-center-frontend.md) — layout, components, interaction states, and visual rules.
6. [Build plan and quality gates](docs/05-build-plan-and-quality-gates.md) — ordered implementation work and verification criteria.
7. [Agent handoff](docs/06-agent-handoff.md) — how a new agent should pick up the work safely.
8. [Hybrid extraction design](docs/07-hybrid-extraction-design.md) — the rules + proprietary LLM implementation, validation, and future open-source adapter.

## Local runtime

`backend/.venv` is the project-local backend virtual environment. It was created with the only Python runtime currently available on this computer: Python 3.14.7. The target build specification names Python 3.11, so production code must avoid 3.14-only features and remain compatible with Python 3.11+.

No `pip` command was run, installed, upgraded, or otherwise modified while preparing this repository. The environment was created only with Python's built-in `venv` module.

To activate the local backend environment in PowerShell when implementation begins:

```powershell
& .\backend\.venv\Scripts\Activate.ps1
```

## Non-production data notice

All complaints, locations, handles, road geometry, and incident data in this demo will be synthetic. The finished interface must always display a persistent `DEMO DATA` badge. Illustrative road geometry is not authoritative HMWSSB or GIS data.

## Extraction policy

Extraction is deliberately hybrid, not a basic rules-only feature. Rules ground known Hyderabad locations, provide deterministic candidates, and remain the no-key fallback. With a proprietary LLM API key configured, each report also goes through constrained structured LLM extraction, Pydantic validation, and deterministic reconciliation before it enters the intelligence pipeline. The provider is isolated behind an adapter so a future open-source model can replace it without changing the pipeline, database contract, or frontend.
