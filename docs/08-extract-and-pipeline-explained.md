# 08 — How `extract.py` and `pipeline.py` work (with a real example)

This guide explains the two files that turn raw complaint text into ranked incidents:

- **`backend/app/extract.py`**: reads one complaint's text and works out what it says. What is the problem, where is it, and how bad is it?
- **`backend/app/pipeline.py`**: decides which complaints describe the *same* real-world problem, groups them into incidents, and scores each incident.

All numbers in the example flow (section 3) come from running the real code on the deterministic demo data. The run was a baseline seed plus one simulation in rules mode, with no API key.

---

## 1. The big picture

```text
IncomingReport  ──►  extract.py  ──►  ExtractionResult  ──►  pipeline.py  ──►  incidents table
(raw text,           "what does        (category, place,      "is this the      (priority, corridor,
 source, handle,      it say?"          lat/lon, severity,     same problem as   velocity, confidence,
 time, GPS pin?)                        flags, provenance)     something else?"  explanations)
```

One idea runs through both files:

> **A complaint is a signal. An incident is the real-world problem.** Forty people complaining about one overflowing manhole should produce **one** incident, not forty.

`extract.py` never decides which incident a report belongs to. `pipeline.py` never parses text. Each file does one job.

---

## 2. `extract.py`: from text to structured fields

### 2.1 Input and output

- **Input:** an `IncomingReport` (`schemas.py`) with `id`, `source` (phone/social/whatsapp/news/official/field), `source_handle`, `raw_text`, `created_at`, and an optional device pin `gps_lat`/`gps_lon`.
- **Output:** an `ExtractionResult` (`schemas.py`). It is a strict Pydantic model: `category`, `locality`, `road`, `landmark`, `lat`, `lon`, `geo_quality`, `severity` (1–5), `households`, `duration_hours`, `road_blocked`, `health_risk`, `near_sensitive`, `in_scope`, plus **provenance**: which fields came from rules or the LLM, any reconciliation notes, and the fallback reason.

### 2.2 The five steps

```text
raw text
  │ 1. normalize()              lower-case, collapse spaces, "Rd No 5" → "road no. 5"
  │ 2. rule_candidates()        gazetteer + keywords + regex  →  RuleResult
  │ 3. provider.extract()       optional LLM (only if a key is configured)
  │    validate_llm()           strict Pydantic check, unknown keys rejected
  │ 4. reconcile()              merge rules + LLM under fixed safety rules,
  │                             then look up coordinates in the gazetteer
  │ 5. apply_device_pin()       use the phone's GPS pin if it agrees with the text
  ▼
ExtractionResult
```

`extract_many()` (`extract.py:527`) runs these steps for a whole batch. The pipeline calls it.

#### Step 1: `normalize()` (`extract.py:78`)

Lower-cases the text and rewrites all road-number spellings to one canonical form, so "Rd No 5", "road number 5" and "Road no.5" all become `road no. 5`.

#### Step 2: `rule_candidates()` (`extract.py:163`), the deterministic layer

This step needs no network and always produces the same answer for the same text.

| What it finds | How |
| --- | --- |
| **Locality** | Exact whole-word match against the 18 gazetteer localities, plus aliases ("hitech city" → Madhapur) and a conservative fuzzy match ("Kukatpalli" → Kukatpally, similarity ≥ 0.88) |
| **Landmark** | Exact or fuzzy match against gazetteer landmark names. A landmark implies its locality and road. |
| **Road** | Matched only among roads in the found locality ("Road No. 5" exists in Kukatpally, but "Road No. 36" is in Jubilee Hills) |
| **Category** | Ordered keyword list `CATEGORY_CUES`, most specific first: `manhole` → `sewage_in_house` → `damaged_pipeline` → `overflow` → `drain_blockage` → `road_flooding` → `blockage` → `foul_smell`. Phrases like "road is blocked" are removed first, so a blocked *road* isn't mistaken for a blocked *sewer*. |
| **In scope?** | Needs a sewerage word (sewer, drain, manhole, nala, …) and no spam cue. "Garbage", "water pressure", "streetlight" and "click this link" are out of scope. |
| **Numbers** | Regex: `37 homes`, `5 hours`, `since yesterday` (= 24 h) |
| **Flags** | Blocked road ("vehicles cannot pass"), health risk ("mosquito", "sick", "contamination"), sensitive place ("school", "hospital", "market") |
| **Severity 1–5** | Base per category (manhole 4, open manhole 5, overflow 3, smell 2, …), +1 if a health risk or blocked road is mentioned |

It also records **candidate lists** (`RuleCandidates`). These are the only places the LLM will be allowed to choose from.

#### Step 3: optional LLM (`extraction_providers/`)

This step runs only when `ANTHROPIC_API_KEY` is set.

- The model receives the text, the source type, the rule candidates, and the **allowed** place and category lists.
- It must return exactly the `LLMExtraction` JSON shape. `validate_llm()` rejects unknown keys (for example, a `lat` field), wrong types, and out-of-range values.
- All LLM calls in a batch run in parallel under a **3.5-second budget**. Any report still waiting at the deadline, and any timeout, bad JSON or refusal, falls back to rules. A report is never dropped.

Vendor-specific code lives only in `extraction_providers/proprietary.py`. `open_source.py` implements the same interface for a future open-source model.

#### Step 4: `reconcile()` (`extract.py:298`), where the safety rules live

When the LLM has answered, reconciliation merges the two answers under fixed rules:

| Rule | Example |
| --- | --- |
| An **exact place match in the text wins** over the LLM | Text says "Road No. 5, Kukatpally" and the LLM says "Miyapur" → Kukatpally is kept, with a note |
| The LLM may only **fill gaps** with a valid gazetteer value that the text supports | Typo "hospitl" → LLM picks "Kondapur Area Hospital" → accepted |
| **Invented places are rejected** | LLM says "Atlantis" → rejected and noted, confidence lowered |
| **Numbers from the text win**; the LLM may not make up numbers | Text says "15 houses" and the LLM says 40 → 15 is kept |
| **"Open manhole" is never overridden** | The LLM says "overflow" → category stays `manhole`, severity 5 |
| **Coordinates always come from the gazetteer**, never the LLM | — |

Then `_resolve_coordinates()` places the report, using the most specific match available:

```text
landmark found?  → landmark point        geo_quality = "exact"
road found?      → road midpoint         geo_quality = "road"
locality found?  → locality centroid     geo_quality = "locality"
nothing?         → no coordinates        geo_quality = "none"   (kept as "unlocated")
```

#### Step 5: `apply_device_pin()` (`extract.py:449`)

Some WhatsApp, field-app and portal reports carry a GPS pin. The pin is used, and the report becomes `exact`, only if it lies within **350 m** of the place named in the text. Otherwise the pin is ignored and a note is recorded. Pins give exact reports their small natural spread along a road, which the corridor detection needs later.

### 2.3 Cache

A successful LLM result is cached on disk. The cache key combines the text, source, provider, model, schema version and gazetteer version (`cache_key()`, `extract.py:475`), so changing the model or the gazetteer never reuses stale results. Rules-only results are cheap and are not cached.

---

## 3. `pipeline.py`: from reports to incidents

### 3.1 Entry point: `process_reports()` (`pipeline.py:404`)

It takes a list of `IncomingReport`s. That type has **no ground-truth field**, so the pipeline cannot cheat. The file reads and writes an explicit column list that excludes the hidden test labels.

```text
1. Receive      insert every raw report into SQLite (nothing is ever deleted)
2. Extract      extract_many() → store category, place, lat/lon, flags, provenance
3. Fit TF-IDF   one text-similarity model over all in-scope report texts
4. For each report, oldest first:
     a. out of scope?          → count it, keep it for audit, skip
     b. duplicate?             → link it to the original, count it once, skip clustering
     c. score it against every active incident within 1 km
     d. best score ≥ 0.55      → attach to that incident
        otherwise              → found a new incident (unlocated reports stay unassigned)
     e. recompute_incident()   → rebuild every derived number from its member reports
5. Commit once; return counts and real per-stage timings
```

### 3.2 Duplicates

A report is a duplicate when the **same handle** has already posted **near-identical text** (TF-IDF cosine > 0.80) within 1 km. The duplicate is kept and shown as evidence, but it is excluded from independent-source counts, velocity and household estimates. Duplicate chains point at the first original.

### 3.3 Clustering score: `_cluster_score()` (`pipeline.py:375`)

```text
score = 0.30·semantic + 0.35·geographic + 0.15·temporal + 0.20·category
```

| Part | Meaning |
| --- | --- |
| **semantic** | Mean TF-IDF cosine against the incident's 5 most similar non-duplicate reports |
| **geographic** | `exp(−distance / 150 m)`, ×0.9 for road-level reports. Distance is measured to the incident's *footprint* (its centroid or nearest precisely located report), so reports at either end of a long overflow still match. Locality-only positions subtract a 350 m uncertainty and use a 400 m scale. |
| **temporal** | `exp(−hours since the incident's last report / 24)` |
| **category** | 1.0 same category, 0.6 compatible (e.g., overflow ↔ road_flooding), 0 otherwise |

The score and its four parts are **stored on the report**, so the evidence drawer shows exactly why the report was grouped.

### 3.4 `recompute_incident()` (`pipeline.py:321`): every number, rebuilt

After any change to an incident, all of its numbers are recalculated from its member reports. Nothing is updated incrementally.

| Output | How it's computed |
| --- | --- |
| **Corridor** (`corridor_for`) | PCA on precisely located points, converted to metres. The 10th–90th percentile along the main axis gives the line. Needs ≥3 points, length ≥30 m, and an axis ratio ≥3; otherwise a radius circle is used. |
| **Velocity** (`velocity_for`) | Six hourly buckets ending at the last report. `ratio = (recent3h+1)/(prior3h+1)`. ≥2.5 with ≥6 recent = RAPIDLY ESCALATING, ≥1.5 INCREASING, ≥0.67 STEADY, else DECLINING. Fewer than 3 reports in the window = STEADY. |
| **Households (est.)** | `max(median claimed, sources × 0.8)`, capped at corridor length ÷ 4 m of frontage |
| **Sensitive place** | School, hospital or market within 150 m of the centroid (gazetteer). Otherwise, a text mention. |
| **Priority** (`priority_for`) | 8 weighted factors, each stored as value × weight × 100 with a sentence (table below). **Severity floor:** severity ≥4 + sensitive place → at least 75. |
| **Confidence** (`confidence_for`) | 0.35·source diversity + 0.25·min(1, sources/8) + 0.20·location precision + 0.20·official/field corroboration, plus plain-language reasons |

| Priority factor | Weight | Value |
| --- | ---: | --- |
| Independent volume | 18 | `log(1+sources)/log(31)`, capped at 1 |
| Velocity | 15 | 1.0 / 0.65 / 0.3 / 0.1 by label |
| Residential impact | 15 | households ÷ 40 |
| Duration unresolved | 12 | hours ÷ 24 |
| Health risk | 12 | 1 if any report mentions it |
| Source diversity | 10 | source types ÷ 6 (+0.15 if official/field) |
| Sensitive location | 10 | 1 if within 150 m |
| Road obstruction | 8 | 1 if any report says blocked |

Bands: **CRITICAL ≥80**, HIGH 60–79, MEDIUM 35–59, LOW <35.

---

## 4. Example flow: the Kukatpally "Road No. 5" overflow

The simulation sends 100 reports. 47 of them describe one overflowing sewer on Road No. 5 in Kukatpally. Follow them through the two files.

### 4.1 Report #1 founds the incident

```text
source:  social · social_kukatpally_001 · 28 Sep 17:40 UTC · no GPS pin
text:    "Again sewage overflowing beside Kukatpally Government School on Road No. 5,
          Kukatpally. When will this be fixed? @HMWSSB"
```

**extract.py**

| Step | Result |
| --- | --- |
| normalize | `…beside kukatpally government school on road no. 5, kukatpally…` |
| category | cue "overflowing" → `overflow` |
| in scope | "sewage" present, no spam → `True` |
| landmark | exact match "Kukatpally Government School" → implies Kukatpally / Road No. 5 |
| flags | "school" → `near_sensitive = school`; no health or blocked cue |
| severity | overflow base 3 |
| LLM | none configured → `rules_fallback` (reason recorded) |
| coordinates | landmark point **17.494705, 78.399742**, `geo_quality = exact` |

**pipeline.py**: not a duplicate; there is no active incident nearby with the same problem, so it **founds HYD-144**. It is stored with `cluster_details = {"founding": 1}`, and the evidence drawer labels it "First report".

### 4.2 A report with a GPS pin joins 26 minutes later

```text
source:  whatsapp · whatsapp_kukatpally_001 · 18:05 UTC · GPS pin 17.494596, 78.399151
text:    "Neighbours pls note: underground drainage overflowing beside Sai Baba Temple on
          Rd No 5, Kukatpally. School kids pass here every day."
```

- **extract.py:** "Rd No 5" is normalized to `road no. 5`. The landmark "Sai Baba Temple" resolves to Road No. 5. The GPS pin lies within 350 m of that road, so the pin is used: `exact` at 17.494596, 78.399151.
- **pipeline.py:** scored against HYD-144:

```text
semantic 0.254 · geographic 0.653 · temporal 0.982 · category 1.0
score = 0.30(0.254) + 0.35(0.653) + 0.15(0.982) + 0.20(1.0) = 0.652  ≥ 0.55 → attach
```

### 4.3 The hardest case: the far end of the road, 4 hours later

```text
source:  phone · phone_kukatpally_001 · 21:48 UTC
text:    "Citizen called: underground drainage overflowing opposite Road No. 5 Bus Stop.
          37 homes affected. Right next to the school gate. For the last 5 hours. …"
```

- **extract.py:** the landmark "Road No. 5 Bus Stop" is at the east end of the road. The rules pull out explicit claims `households = 37` and `duration_hours = 5`. The locality comes from the landmark; the text itself never says "Kukatpally".
- **pipeline.py:**

```text
semantic 0.172 · geographic 0.657 · temporal 0.857 · category 1.0
score = 0.052 + 0.230 + 0.129 + 0.200 = 0.610 → attach
```

Measuring distance to the incident's **footprint** (its nearest precise member) is what keeps this score above 0.55. When distance was measured to the centroid, this report scored 0.52 and started a second, parallel incident on the same road.

### 4.4 A repost becomes a duplicate

```text
09:12 UTC  social_kukatpally_006: "Tagging @HMWSSB — drain overflowing outside my house on Road no.5, …"
09:22 UTC  social_kukatpally_006: same text again
```

Same handle, cosine > 0.80, same place. The second post is marked `is_duplicate`, linked to the 09:12 original, and shown muted as "Duplicate · counted once". Eight hero reposts are handled this way.

### 4.5 A report that stays unlocated

```text
"Portal complaint — sewerage; dirty sewage water gushing out of the manhole and overflowing;
 near the school. Right next to the school gate."
```

No place is named and there is no GPS pin, so `geo_quality = none`. It could attach only if its text matched an incident at > 0.50 similarity *and* the category matched; it didn't. It stays **unlocated** and appears in the "Unlocated reports" KPI rather than being guessed onto the map.

### 4.6 Out-of-scope reports are filtered out

`"Streetlight not working near LB Nagar Metro Station…"` and `"Congratulations! Win a free phone now, click this link…"` get `in_scope = False` (no sewerage term, or a spam cue). They are stored for audit and never clustered. There are 4 in the batch.

### 4.7 The final HYD-144 after all 47 reports

| Field | Value | Where it comes from |
| --- | --- | --- |
| Reports | **46** (8 duplicates) | 47 hero reports minus the one unlocated |
| Independent sources | **38** | distinct handles among non-duplicates |
| Source mix | whatsapp 12, social 11, field 4, news 4, phone 4, official 3 | non-duplicates |
| Corridor | **126.8 m**, 37 points, axis ratio 16:1, cross-spread ±11 m | PCA on exact/road points |
| Households (est.) | **32** | median claim ≈36 and 38 × 0.8 = 30.4 → max ≈36, capped at 126.8 ÷ 4 ≈ 31.7 → 32 |
| Duration | **19.1 h** | first→last report span plus stated durations |
| Velocity | buckets `[0,2,3,6,9,9]`; recent 24, prior 5; ratio (24+1)/(5+1) = **4.17** → **RAPIDLY ESCALATING** | non-duplicates only |
| Sensitive place | Kukatpally Government School, **~16 m** | gazetteer within 150 m |
| Confidence | **0.99 (HIGH)**: "Corroborated by field officer", "Location approximate for 3% of reports", "38 independent sources across 6 source types" | `confidence_for` |

**Priority breakdown (each line is stored and shown in the evidence drawer):**

| Factor | Value × Weight | Points | Stored sentence |
| --- | --- | ---: | --- |
| Independent volume | 1.0 × 18 | 18.0 | 38 independent sources reported this (duplicates counted once). |
| Velocity | 1.0 × 15 | 15.0 | 24 reports in the latest 3 hours vs 5 in the 3 hours before. |
| Residential impact | 0.8 × 15 | 12.0 | About 32 households estimated affected along a ~127 m stretch (est.). |
| Health risk | 1.0 × 12 | 12.0 | 19 reports raise health or contamination concerns. |
| Source diversity | 1.0 × 10 | 10.0 | Evidence spans 6 source types, including field and official reports. |
| Sensitive location | 1.0 × 10 | 10.0 | Kukatpally Government School (school) is ~16 m from the incident. |
| Duration unresolved | 0.795 × 12 | 9.5 | Unresolved for about 19 hours. |
| Road obstruction | 1.0 × 8 | 8.0 | 17 reports say the road is blocked. |
| **Total** | | **94.5 → 94** | **CRITICAL** (Python rounds 94.5 to the even 94) |

### 4.8 Contrast: few reports can still be urgent

HYD-153, the open manhole on Hafeezpet Road in Miyapur, has only **3 reports**. Its factors add up to just **36**. But it contains an open manhole (severity 5) within 150 m of Miyapur Zilla Parishad School, so the **severity floor** lifts it to **75**, rank #2 in the queue.

### 4.9 What `/api/simulate` returns for the whole batch

```text
received 100 · out_of_scope 4 · duplicates 8 · located 95 · unlocated 1
incidents 34 → 51 active (17 new, 1 existing incident updated) · 18 incidents touched
stages (server ms): received 1 · classifying 233 · extracting 4 · duplicates 3 · clustering 44 · priority 40
```

These counts and timings drive the "100 REPORTS → 18 INCIDENTS" simulation overlay in the UI. Nothing there is hard-coded.

---

## 5. Where to change things

| You want to… | Edit |
| --- | --- |
| Tune grouping, priority or velocity thresholds | `backend/app/config.py` only, then re-run `pytest` (it prints ARI and purity) |
| Teach the rules a new phrase | `CATEGORY_CUES`, `BLOCKED_CUES`, `HEALTH_CUES`, … at the top of `extract.py` |
| Add a place | `gazetteer.py`, then bump `GAZETTEER_VERSION` so cached LLM results are invalidated |
| Swap the LLM vendor | Add an adapter in `extraction_providers/`; `extract.py` and `pipeline.py` stay unchanged |
