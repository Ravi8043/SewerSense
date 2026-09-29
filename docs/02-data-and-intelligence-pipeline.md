# 02 — Data and Intelligence Pipeline

## Gazetteer and synthetic geography

`gazetteer.py` defines 18 named localities, each with an approximate Hyderabad centroid, three to five illustrative roads, and two or three landmarks positioned along each road. All locality and road coordinates must pass this sanity range before any seed is accepted:

```text
17.25 ≤ latitude ≤ 17.55
78.25 ≤ longitude ≤ 78.65
```

Required locality coverage: Kukatpally, KPHB, Miyapur, Madhapur, Gachibowli, Kondapur, Ameerpet, Begumpet, Secunderabad, Tarnaka, Uppal, LB Nagar, Dilsukhnagar, Mehdipatnam, Attapur, Charminar, Jubilee Hills, and Malkajgiri. All road names and geometry are illustrative demo fixtures, not official GIS information.

Store each road as a short start/end polyline of approximately 150–400 metres. The generator samples positions along this line, adds 5–25 m jitter to exact reports, and assigns broader uncertainty to locality-only reports.

## Generator contract

`generator.py` must expose:

```python
generate_batch(n: int = 100, now: datetime, hero: bool = True) -> list[GeneratedReport]
generate_baseline(n: int = 300, now: datetime) -> list[GeneratedReport]
```

Use an isolated `random.Random(42)` (or an explicitly seeded generator passed through helper calls), not global randomness. Identical input arguments must produce identical report content, truth labels, timing distribution, and locations.

### Simulated batch composition

| Element | Required behavior |
| --- | --- |
| In-scope reports | 96 reports belonging to 17 hidden ground-truth incidents. |
| Out-of-scope reports | 4 reports: garbage pickup, water pressure, spam, and unrelated content. |
| Duplicate evidence | About 8 near-exact reposts from the same source handle. |
| Hero incident | Kukatpally, Road No. 5, sewer overflow: 47 reports, at least 31 handles, ~18 hours, accelerating hourly pattern, ~120 m, ~36 households, blocked road, health risk, school within 100 m. |
| Small dangerous incident | Exactly three reports about an open manhole beside a school, high severity. It must receive the severity floor. |
| Inflated low-priority incident | Many reports from one repeat handle. It demonstrates why raw count does not equal independent evidence. |
| Remaining incidents | Vary categories, vocabulary, ages, sources, geography, and trends; include escalating and stale/slow patterns. |

Each source style should have at least 30 template variations across phone, social, WhatsApp, news, official portal, and field officers. Vary vocabulary for the same issue: for example, `drain overflowing outside my house`, `sewage water flooding the street`, and `manhole overflowing near Road 5`. Handles must be clearly synthetic, such as `social_kukatpally_014`; never create actual names or phone numbers.

`truth_incident` is written to reports only for post-hoc test metrics. Production pipeline code must neither read this column nor receive it in its input types.

## Hybrid extraction

The intended enriched path combines deterministic rules with a proprietary structured LLM; see [the dedicated hybrid design](07-hybrid-extraction-design.md) for provider boundaries and prompts. It is not a loose “LLM or rules” switch. Each report follows this sequence:

1. Normalize text: lower case, collapse whitespace, preserve the human-readable original.
2. Run the rule candidate extractor. It identifies locality, road, landmark, category/impact cues, explicit numeric values, and excluded-topic signals using a gazetteer, regexes, keywords, and conservative fuzzy matches.
3. If a proprietary API key is configured, submit raw text plus the rule candidates and permitted gazetteer choices to the structured LLM. The model may disambiguate vocabulary, typos, implicit locations, duration, impact, and severity, but must return only the shared extraction JSON.
4. Validate the response with Pydantic, then reconcile it deterministically. Known gazetteer identity and coordinate mapping always come from the local gazetteer; the LLM cannot invent a locality, road, landmark, coordinate, or category outside the allowed schema.
5. Resolve coordinates by the most specific reconciled match: landmark → road midpoint → locality centroid → none, and set `geo_quality` to `exact`, `road`, `locality`, or `none`.
6. Persist field-level provenance/confidence and any reconciliation conflict for evidence/debugging. Cache the reconciled result by text hash, schema version, provider, and model.
7. If no key is configured or any provider, transport, JSON, or validation error occurs, emit a rules-only extraction with provenance `rules_fallback`; do not discard the report or halt a simulation.

Suggested deterministic precedence: explicit category keywords beat broad cues; an explicit `open manhole` maps to `manhole` even when overflow is also mentioned. An explicit local location mention wins over an LLM interpretation; an LLM can improve a fuzzy or incomplete match only by selecting a valid gazetteer candidate. Return validated Pydantic models, never ad hoc dictionaries.

## Pipeline order

For each persisted report in ascending `created_at` order:

1. Extract structured fields if not already cached.
2. Keep out-of-scope reports for audit but do not cluster them.
3. Identify duplicates among reports from the same `source_handle` associated with the same incident candidate and with text cosine similarity greater than 0.80. Mark them as evidence, do not remove them.
4. For an in-scope, non-duplicate located report, compare against every **open** incident within 1 km.
5. Assign the report to the best incident at score ≥0.55; otherwise make a new incident.
6. For `geo_quality=none`, attach only if semantic similarity exceeds 0.50 and category matches. Otherwise persist as unlocated with no incident.
7. Recompute all affected incident aggregates. Do not use hidden truth at any step.

Persist `cluster_score` and the semantic, geographic, temporal, and category subscores on each attached report (as columns or a dedicated JSON field). Evidence views must render these stored values, not recompute an approximation in the browser.

## Clustering formula

For the top five most semantically similar reports in an incident, calculate:

```text
sim_sem  = mean cosine(TF-IDF(report), TF-IDF(top-5 incident reports))
sim_geo  = exp(-distance_m / 150)
           exact × 1.0, road × 0.9; locality uses a 400 m distance scale
sim_time = exp(-hours_since_incident_last_report / 24)
sim_cat  = 1.0 same category, 0.6 compatible group, 0.0 otherwise

score = 0.30·sim_sem + 0.35·sim_geo + 0.15·sim_time + 0.20·sim_cat
```

Compatible groups are:

```text
{overflow, road_flooding, sewage_in_house, drain_blockage, blockage}
{foul_smell, blockage, overflow}
{manhole, overflow}
{damaged_pipeline, overflow, road_flooding}
```

Put these weights, thresholds, and compatible-category groups in `config.py`. Tests may tune only config constants. No test is allowed to special-case a known `truth_incident` in runtime logic.

## Corridor, velocity, priority, and confidence

### Corridor

For incidents with three or more `exact` or `road` reports, project lat/lon to local metre coordinates and run PCA. Project points on the principal axis; the 10th and 90th percentile projections make the corridor endpoints. Use a 12 m fixed width. If the length is under 30 m or the first-to-second eigenvalue ratio is below 3, store no corridor and use a radius circle. Store points count, spread, eigenvalue ratio, and a human-friendly confidence reason.

### Velocity

Build six hourly buckets ending at the incident's most recent report time. Count only non-duplicates. Let `recent` be the latest three buckets and `prior` the preceding three:

```text
ratio = (recent + 1) / (prior + 1)
```

| Condition | Label |
| --- | --- |
| ratio ≥ 2.5 and recent ≥ 6 | RAPIDLY ESCALATING |
| ratio ≥ 1.5 | INCREASING |
| 0.67 ≤ ratio < 1.5 | STEADY |
| ratio < 0.67 | DECLINING |

### Priority

Every factor stores `value`, `weight`, `contribution = weight × value × 100`, and an operator-readable sentence.

| Factor | Weight | Value |
| --- | ---: | --- |
| Independent volume | .18 | `min(1, log1p(unique_sources)/log1p(30))` |
| Source diversity | .10 | distinct source types / 6; boost when official or field evidence exists |
| Duration unresolved | .12 | `min(1, duration_hours/24)` |
| Velocity | .15 | escalating 1.0; increasing .65; steady .3; declining .1 |
| Residential impact | .15 | `min(1, estimated_households/40)` |
| Road obstruction | .08 | 1 when blocked, otherwise 0 |
| Health risk | .12 | 1 when cues or contamination exist, otherwise 0 |
| Sensitive location | .10 | 1 for school/hospital/market within 150 m, otherwise 0 |

The base sum is 0–100. Apply a severity floor after summing: when any report severity is at least 4 and a sensitive location exists, set priority to `max(base_priority, 75)`. Bands are CRITICAL ≥80, HIGH 60–79, MEDIUM 35–59, LOW below 35.

`estimated_households` is `max(median reported household count, unique_sources × 0.8)`, capped by corridor length divided by four metres of frontage. It is always labelled `est.` in responses and UI.

### Confidence

```text
confidence = .35·source_diversity_norm
           + .25·min(1, unique_sources/8)
           + .20·mean_geo_quality_score
           + .20·official_or_field_corroboration
```

Return numeric confidence and short reasons, then map it to HIGH, MEDIUM, or LOW in the presentation layer. Examples: `Corroborated by field officer` and `Location approximate for 40% of reports`.

## Test measurements

The test module, not the pipeline, compares finalized assignment IDs against `truth_incident`. It prints adjusted Rand index (ARI) and purity. Required assertions are 15–19 batch incidents, one hero cluster, hero ≥40 reports and ≥28 sources, dangerous incident priority ≥75, inflated incident below hero, and exclusion of all four out-of-scope reports.
