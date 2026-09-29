# 04 — Command-Center Frontend

## Visual direction

The UI is a sober, dark command center for a 1440×900 desktop demo, still readable at 1280 px wide. Use Inter, a `#0b0f14` page background, `#111821` panels, cyan/teal highlights, red critical, orange high, amber medium, and slate low. Minimum body text is 13 px with accessible contrast. Avoid decorative charts or heavy chart libraries; source bars and velocity sparkline use simple SVG.

Every screen permanently displays a compact `DEMO DATA` badge. It should be visible in the top bar regardless of loading, error, modal, or simulation state.

## Page composition

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ SewerSense · Intelligence layer for HMWSSB · [DEMO DATA]  [Simulate] [Reset]│
├────────────────────────────────────────────────────────────────────────────┤
│ Reports Today │ Active Incidents │ Critical │ Escalating │ Resolved          │
├───────────────┬────────────────────────────────────┬───────────────────────┤
│ Incident queue│ Map: heat + priority markers       │ Incident card         │
│ ~340px        │ corridor, raw-report toggle, legend│ ~420px                │
│ filters       │ simulation overlay over this area  │ evidence / brief      │
└───────────────┴────────────────────────────────────┴───────────────────────┘
```

The three desktop columns should use CSS grid with approximately `340px minmax(420px, 1fr) 420px`. At narrower desktop widths, reduce the right card slightly before hiding critical content. A mobile experience is not required by the MVP.

## Component contract

| Component | Inputs/owned state | Required behavior |
| --- | --- | --- |
| `TopBar` | simulation/reset callbacks, busy flag | wordmark, HMWSSB subtitle, DEMO DATA, primary simulate button, reset, architecture toggle |
| `KpiStrip` | summary | animated count transition only when response values change; skeleton and retry on error |
| `IncidentQueue` | compact incidents, selected ID, filters, changed IDs | priority descending; title, category, reports/sources, velocity, age; click selects/flys map; optional `NEW` flash tag |
| `CommandMap` | incidents, selected incident, heatmap, raw-report state | CARTO dark tile map, heat, markers, selected corridor/radius, raw-report toggle, legend |
| `IncidentCard` | full selected incident | facts, estimates, source mix SVG, velocity sparkline, confidence, factor sentences, status, buttons |
| `EvidenceDrawer` | evidence response | factor bars, clustered-score explanation, representative reports, duplicate styling |
| `BriefModal` | brief request state/result | loading skeleton, facts/assessment blocks, generated-by tag, copy button, required footer |
| `SimulationOverlay` | simulation response/stage state | stage animation then large received-to-incidents result; collapse and hand control back to map |
| `ArchitectureModal` | open state | static React/SVG pipeline diagram, with future sources clearly labelled |

`api.ts` is the sole HTTP boundary. It exposes typed functions for each route and turns non-2xx responses into usable errors. `types.ts` mirrors Pydantic response schemas; no component should define competing API shape types.

## Data loading and state flow

On initial load, request summary, compact incidents, and heatmap in parallel. Select the highest-priority incident when no selection exists, then request its full details. Rendering sequence must show skeletons in the affected regions rather than a blank page.

When queue selection changes:

1. Set selected ID immediately for row/marker highlight.
2. Fly the Leaflet map to the compact incident centroid.
3. Load full incident details and replace the card only on a matching, current response.
4. Cancel or ignore stale requests if the user selects another item.

When the selected card opens evidence or brief, retain the incident ID used for the request so a later selection cannot overwrite the open modal with unrelated data.

## Map behavior

- Basemap: CARTO dark tiles at `https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png`, with required attribution.
- Heat: consume `/api/heatmap`; low opacity so incident marker and corridor symbols remain primary.
- Marker: colour by band and size by priority; apply a restrained pulse ring if critical or rapidly escalating.
- Zoom policy: when zoomed out, show priority ≥35 or top-N incidents only; when zoomed in, show all located incidents.
- Selected incident: fly to centroid, emphasize marker, render the glowing corridor and length label if one exists; otherwise render its radius circle.
- Raw reports: off by default. When toggled on, display per-report dots as a deliberately cluttered contrast view, with a short caption explaining signals versus incidents.
- Legend: explicitly distinguish heat (report density), marker (incident priority), and corridor (estimated affected stretch).

Leaflet container lifecycle must be managed correctly: mount only after a nonzero container size and invalidate size after layout/modal changes where necessary.

## Incident card semantics

The card presents title, category, priority band and ring, report count, **independent** sources, household estimate (`est.`), corridor length, unresolved hours, source mix, velocity label/sparkline, confidence, and the highest-impact priority explanations. Extraction provenance may appear as a compact secondary label in the evidence drawer (for example, `hybrid validated` or `rules fallback`); it must not distract from incident evidence or expose provider internals.

Do not represent estimates as facts. Use wording such as `~36 households est.` and distinguish direct report claims from derived system scores. The `Why critical?` list comes from stored factor sentences, ordered by contribution, not UI-authored prose.

Status control is optional until the MVP is complete. If included, optimistically update only after API success or roll back with a clear inline error.

## Evidence drawer

Evidence provides the audit trail:

1. Factor bars show contribution points and their human-readable sentence.
2. The grouping section shows average stored semantic/geographic/temporal/category scores and plain language stating that reports matched in content, proximity, recency, and category.
3. Representative reports show source icon/type, time, text snippet, geo quality, and duplicate state.
4. Duplicate reports are muted and labelled `counted once` so their presence cannot be mistaken for independent corroboration.

## Simulation interaction

`Simulate Incoming Complaints` disables while running and calls `/api/simulate` exactly once. The map-area overlay progresses through:

```text
100 reports received → Classifying → Extracting locations → Finding duplicates
→ Clustering incidents → Calculating priority
```

For each server stage, use the returned count and retain the stage for at least 600 ms. Then show the large result, for example `100 REPORTS → 17 INCIDENTS`; the actual incident number is derived from the response's batch effect, never hard-coded. Refresh summary, incidents, heatmap, and hero detail; auto-select `hero_incident_id`; flash `new_incident_ids` and `updated_incident_ids` in the queue briefly.

On failure, keep the pre-simulation map state, close the overlay into an explicit retryable error, and re-enable the button.

## Accessibility and error handling

Modals/drawers need focus management, Escape close, visible close buttons, and keyboard-operable controls. Icons cannot be the only carrier of priority/status meaning. Every data region has loading, empty, and error states. A failed map tile load must not prevent queue/card use. A failed LLM brief is a normal template-backed success when the API returns the fallback; a true request failure has retry UI.
