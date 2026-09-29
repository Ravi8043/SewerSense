# 07 — Hybrid Extraction Design

## Decision

SewerSense uses **rules plus a proprietary LLM**, not basic rule-only extraction. The two methods have distinct jobs:

| Layer | Job | Why it is needed |
| --- | --- | --- |
| Rule candidate extractor | Recognize deterministic cues, enumerate valid local places, parse obvious values, flag non-sewerage content | keeps location grounding local, repeatable, fast, and auditable |
| Proprietary structured LLM | Interpret varied complaint language, typos, indirect descriptions, negation, and incomplete information | handles semantic variation rules alone cannot reliably cover |
| Validator and reconciler | enforce JSON schema, stop invented facts, choose a canonical gazetteer match, record provenance | makes the combined result safe for clustering and explainable to operators |

The standard production-like demo mode is `hybrid`. `rules_fallback` exists only so the local demo still runs before a key is supplied or when a provider fails. It is not the intended quality level once credentials are available.

## Normalized output contract

Both providers must return the same Pydantic `ExtractionResult`; the pipeline never receives provider-specific fields.

```python
class ExtractionResult(BaseModel):
    category: Category | None
    locality: str | None
    road: str | None
    landmark: str | None
    duration_hours: float | None
    severity: int  # constrained to 1..5
    households: int | None
    road_blocked: bool
    health_risk: bool
    in_scope: bool
    candidate_confidence: float  # 0..1
    field_provenance: dict[str, Literal["rule", "llm", "reconciled", "fallback"]]
    reconciliation_notes: list[str]
    extraction_mode: Literal["hybrid_validated", "rules_fallback"]
    provider: str | None
    model: str | None
    schema_version: str
```

The database serializes non-sensitive provenance to `extraction_details_json`. It never stores the API key, authorization headers, hidden reasoning, or the full unvalidated provider response.

## Execution sequence

```text
Raw complaint
    │
    ├─ 1. Normalize + deterministic rule candidates
    │       locality/road/landmark matches, explicit claims, category cues,
    │       in-scope evidence, coordinate candidates
    │
    ├─ 2. Proprietary LLM structured request (when configured)
    │       raw text + source type + valid candidate choices + strict JSON schema
    │
    ├─ 3. Pydantic validation
    │       reject malformed JSON, out-of-range severity, extra/unallowed values
    │
    ├─ 4. Deterministic reconciliation
    │       canonicalize place names, resolve conflicts, derive coordinates locally
    │
    └─ 5. Cache reconciled result and pass normalized result to pipeline

No key / timeout / transport error / invalid result
    └─ rule candidate output → rules_fallback provenance → pipeline
```

The extraction cache key must include SHA-256 of normalized raw text, source type, provider name, model, extraction schema version, and gazetteer version. This prevents stale extraction results after prompt, provider, or locality-fixture changes.

## Candidate and reconciliation policy

The rule layer produces candidate lists, rather than pretending to know every field perfectly:

```json
{
  "locality_candidates": ["Kukatpally", "KPHB"],
  "road_candidates": ["Road No. 5"],
  "landmark_candidates": ["Kukatpally Government School"],
  "explicit_claims": {"households": 15, "road_blocked": true},
  "category_cues": ["overflow", "manhole"],
  "excluded_topic_cues": []
}
```

Send these candidates to the LLM so it can disambiguate language but cannot create arbitrary geography. Reconciliation applies the following order:

1. An explicit, exact local match in raw text is authoritative.
2. A valid LLM-selected candidate can resolve a fuzzy or indirect wording only when it is in the gazetteer candidate set or passes a conservative local fuzzy match.
3. Canonical coordinates always come from `gazetteer.py`, never from LLM latitude/longitude.
4. Explicit numeric values in the report (for example `15 houses`) take precedence over a model inference. The LLM may mark uncertain/approximate values but may not manufacture numbers.
5. A high-confidence LLM category can resolve ambiguous compatible cues, but an explicit safety phrase such as `open manhole` always preserves the `manhole` category/safety severity.
6. If conflict cannot be resolved, retain the deterministic value, add a reconciliation note, lower extraction confidence, and continue.

The only permitted coordinate-resolution order is reconciled landmark → road midpoint → locality centroid → `none`. A semantic LLM interpretation cannot turn unlocated text into a precise point without a valid gazetteer reference.

## Proprietary provider adapter now

Use an adapter boundary so vendor code is absent from `extract.py`:

```text
app/
  extract.py
  extraction_providers/
    base.py            # StructuredExtractionProvider protocol
    proprietary.py     # current API client and JSON-mode request
    open_source.py     # interface-compatible placeholder/future implementation
```

`StructuredExtractionProvider.extract(request) -> ProviderExtraction` accepts only a safe request object and returns parsed JSON text/data. It does not write to SQLite or make clustering decisions.

The initial proprietary adapter should support the build spec's Anthropic configuration:

```text
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=<provided later; never commit it>
LLM_MODEL=claude-sonnet-5
EXTRACTION_MODE=hybrid
```

Keep names generic in the orchestrator. A second proprietary provider can be introduced by another adapter, not by `if vendor == ...` branches throughout extraction code. Configure timeout, maximum retry count, and response token budget centrally. One failed request should resolve to rules fallback, not retry indefinitely or delay `/api/simulate` beyond its five-second target.

## LLM request constraints

The structured extractor prompt includes only synthetic report text, source class, rule candidates, permitted categories, and a JSON schema. Its instructions must require:

- Return JSON only; no narrative or hidden analysis.
- Select locations only from candidates or return null.
- Do not provide coordinates.
- Preserve direct report claims and distinguish them from uncertainty.
- Mark out-of-scope only according to the allowed sewerage scope.
- Never infer people, phone numbers, causes, or operational completion.

Pydantic uses `extra="forbid"` for model responses. JSON parse failure, schema mismatch, token-limit truncation, non-200 response, or model refusal is handled as rules fallback and captured in a non-sensitive diagnostic reason.

## Future open-source model path

When the proprietary provider is replaced or supplemented, implement `open_source.py` to the exact `StructuredExtractionProvider` protocol. It may call an approved locally hosted or OpenAI-compatible endpoint, but it must use the same prompt schema, Pydantic validation, candidate restrictions, cache-key versioning, reconciliation, and output shape. No change to `pipeline.py`, API response schemas, database aggregate calculations, or frontend components is allowed.

Before enabling an open-source model, run the same fixed extraction fixture suite against both adapters and compare: valid schema rate, category accuracy, canonical location accuracy, fallback rate, conflict rate, and p95 latency. Do not switch default provider if location hallucinations or simulation latency violate the tests.

## Test plan

No real API call or key is needed in unit tests. Test with provider fakes that return controlled JSON.

| Case | Expected outcome |
| --- | --- |
| Clear exact road/landmark text | Rule match is retained; LLM confirms or adds semantic fields |
| Informal/typo-heavy wording | LLM can select one valid candidate; reconciliation canonicalizes it |
| Landmark-only report | Correct locality/road derives from gazetteer; geo quality is `exact` |
| Explicit number conflicts with LLM estimate | Raw-text number wins and conflict is recorded |
| LLM invents locality or coordinate | Validation/reconciliation rejects invention; use valid rule candidate or null |
| Malformed JSON / timeout / missing key | Rules fallback, report still reaches pipeline |
| Non-sewerage complaint | Correctly marked out of scope without clustering |
| Open manhole beside a school | Manhole/safety cues survive reconciliation and enable downstream floor |
| Same raw text after schema/model change | Cache is not incorrectly reused |

## Operator visibility

The dashboard need not expose model details in the primary card. The evidence drawer can show a modest extraction badge — `Hybrid extraction validated` or `Rules fallback` — plus canonical location confidence. This supports auditability without making an LLM the apparent authority over the underlying reports.
