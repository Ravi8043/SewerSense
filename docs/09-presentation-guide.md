# SewerSense: presentation guide

A complete script for presenting the SewerSense prototype: what to say, what to click, which numbers to quote, and how to answer the likely questions.

> Suggested length: a **10-minute** talk plus demo, with a **5-minute** short version marked ⏱. Every number below comes from the deterministic demo dataset and the automated test suite, so it will be the same on every run.

---

## 0. Before you present (checklist)

Do these 15 minutes before you present.

| # | Step | Command / action |
| --- | --- | --- |
| 1 | Stop any old servers (a backend started before a code or `.env` change does not reload) | Ctrl+C in their terminals |
| 2 | Start the backend | `backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --port 8000` |
| 3 | Start the frontend (second terminal) | `npm --prefix frontend run dev` |
| 4 | Confirm the backend sees your keys | `curl http://localhost:8000/api/health` → `"live_sources":{"tavily":true,"apify":true}` |
| 5 | Open the dashboard at full screen (1440×900 is ideal) | http://localhost:5173, then Ctrl+Shift+R |
| 6 | Click **Reset demo** so you start from the clean baseline | top bar |
| 7 | **Pre-load live data**: switch to **Live web data** → **Fetch live data**, wait for the banner, then switch back to **Demo data** | Apify can take ~2 min, so don't do this live on stage |
| 8 | Optional safety net: run the tests once | `cd backend; .venv\Scripts\python.exe -m pytest -q` → 85 passed |

If the internet fails during the talk, the demo still works: demo mode needs no network. Only the map background tiles would go blank; the incidents still show.

---

## 1. The opening (30 seconds) ⏱

> "Hyderabad's sewerage board receives complaints from phone calls, WhatsApp, social media, news, its portal and field staff. When a sewer overflows, forty people report the *same* problem in forty different ways. Operators see forty tickets, not one emergency.
>
> **SewerSense turns many fragmented complaints into a small number of explainable, geolocated incidents**, ranked by how urgent they really are, with every number traceable back to the reports behind it."

The one line to remember:

> **A complaint is a signal. An incident is the real-world problem.**

---

## 2. The problem (1 minute)

| Today | Why it hurts |
| --- | --- |
| Every complaint is a separate ticket | 40 reports of one overflow look like 40 jobs |
| Raw volume drives attention | A single person posting 10 times can outrank a real hazard |
| Locations are free text ("near the school on Road 5") | Hard to map, hard to dispatch |
| Urgency is a gut call | A 3-report open manhole next to a school can get ignored |
| No explanation | Supervisors can't audit *why* something was prioritised |

---

## 3. What SewerSense is and isn't

**It is** an *intelligence layer* that sits **above** existing complaint systems and GIS. It groups complaints into incidents, locates them, scores them, and explains every decision.

**It is not** a replacement for the complaint system, a dispatch system, or a GIS. It does not act on its own: it recommends, and humans verify.

**Data honesty:** the demo dataset is **synthetic** (a permanent `DEMO DATA` badge). Road names and geometry are illustrative. Live mode uses **real public web data** from Tavily and Apify, labelled `LIVE WEB DATA · unverified`.

---

## 4. How it works (2 minutes)

```text
   DEMO: synthetic complaints          LIVE: public web (Tavily search, Apify scrapers)
                 │                                   │
                 └──────────────┬────────────────────┘
                                ▼
                  same normalized report format
                                ▼
 1. EXTRACT     what is the problem? where? how severe?    (rules + gazetteer; LLM optional)
 2. FILTER      drop garbage / water-pressure / spam       (kept for audit, never clustered)
 3. DEDUPE      same account reposting the same text       (kept as evidence, counted once)
 4. CLUSTER     is this the same problem as an open incident?
                score = 0.30 wording + 0.35 distance + 0.15 recency + 0.20 problem type ≥ 0.55
 5. SCORE       affected stretch (corridor), trend (velocity), households, 8-factor priority, confidence
 6. EXPLAIN     every factor stored with a plain-English sentence
                                ▼
            SQLite  →  FastAPI  →  React + Leaflet command center
```

Plain-language version:

1. **Read the complaint.** A place list (gazetteer) of 18 Hyderabad localities, their roads and landmarks turns "near the school on Rd No 5, Kukatpalli" into *Kukatpally · Road No. 5 · Kukatpally Government School*, with typos handled.
2. **Throw out noise.** Garbage, water pressure, streetlights and spam are out of scope.
3. **Don't double-count.** The same account posting the same thing twice counts once.
4. **Group by meaning, place and time.** New reports join an open incident if they are about the same kind of problem, nearby, and recent.
5. **Score what matters.** Independent sources, not raw volume; whether reports are *accelerating*; health risk; blocked roads; schools, hospitals and markets nearby.
6. **Explain it.** Every priority point is traceable to a factor and to reports.

---

## 5. Live demo script (5–6 minutes) ⏱

Start in **Demo data** mode after **Reset demo**.

### Step 1: the baseline (30 s)
**Point at:** KPI strip, incident queue (left), map (centre), incident card (right).
> "This is the command center. About 300 synthetic complaints from the last three days have already become **39 incidents**. Every KPI is computed live from the database; nothing is hard-coded."

### Step 2: the raw chaos (20 s)
**Click:** *Show raw reports* (map, top right).
> "Each dot is one complaint. This clutter is what operators deal with today. SewerSense turns it into the ranked queue on the left." Click it again to hide.

### Step 3: a live batch arrives (45 s)
**Click:** *Simulate incoming complaints*.
> "A new batch of 100 complaints arrives. Watch the stages: received → classified → located → duplicates found → clustered → prioritised. The counts and timings are real server numbers."

Land on the result:
> "**100 reports → 18 incidents**: 17 new and 1 update to an existing incident. 4 were off-topic, 8 were reposts counted once, and it took about **one second** on the server."

### Step 4: the critical incident (1 min)
It auto-selects **Overflow on Road No. 5, Kukatpally**.
> "**Priority 94, CRITICAL, rapidly escalating.** 46 reports, but more importantly **38 independent sources** across all six channels. Eight reposts are counted once.
> The glowing line is the estimated affected stretch, about **127 metres**, worked out from where the reports cluster. About **32 households, estimated**. Kukatpally Government School is about 16 m away. 24 reports in the last 3 hours versus 5 before, which is why it's escalating."

Read the **Why critical?** list:
> "These sentences are generated by the scoring engine and stored with the incident, not written by the UI."

### Step 5: the evidence (1 min)
**Click:** *View evidence*.
> "This is the audit trail. Each of the 8 factors shows its points out of its maximum, and they add up to exactly 94. Below: *why these reports were grouped*, with average wording, proximity, recency and category scores. Then the actual reports. Duplicates are greyed out and labelled *counted once*."

### Step 6: few reports can still be urgent (40 s)
**Click:** the second queue item, **Hafeezpet Road, Miyapur**.
> "Only **3 reports**, yet priority **75**. It's an **open manhole next to a school**. On volume alone it would score 36. The **severity floor** lifts any severe hazard near a school, hospital or market to at least 75. Volume isn't urgency."

Optional contrast: a single social-media account posted 10 times about a smell in Madhapur. It has 10 reports but **1 independent source**, so priority **19**. "Loud isn't the same as urgent."

### Step 7: the response brief (40 s)
**Back on the hero, click:** *Generate response brief*.
> "This is what a supervisor would forward. **Reported facts** in blue come only from the reports. **AI assessment** in amber holds the estimates and interpretation, clearly labelled. The next step is marked as a *suggestion*, and the footer says **AI-generated, verify before action**. It never invents numbers; a test checks that."

### Step 8: real web data (1 min)
**Switch the top bar to:** *Live web data* (you pre-loaded it in the checklist).
> "Everything so far was synthetic, so let's use the real internet. SewerSense searched the public web through **Tavily** and scraped results through an **Apify** actor. Those results went through **exactly the same pipeline**, with no separate logic. They're kept in a separate live dataset, so real and synthetic data never mix."

Point at the banner: found / new / duplicates / off-topic per source.
> "Notice how many were off-topic or duplicates. The same article from two queries, or from both Tavily and Apify, becomes **one** report."

**Open evidence** on a live incident:
> "Each live report links back to the original article, so an operator can check the source."

*(If the internet or keys fail: "Live data depends on external services; when they're down the core system keeps working," then switch back to demo.)*

### Step 9: architecture and close (30 s)
**Click:** *Architecture*.
> "What's built today is solid; dashed boxes are future: the real complaint system, WhatsApp and social adapters, IoT sewer sensors, GIS road snapping. They all plug into the same report format."

---

## 6. Numbers to quote

| What | Number |
| --- | --- |
| Baseline | ~300 synthetic reports → **39 incidents** (34 active, 5 resolved) |
| Simulation | **100 reports → 18 incidents** (17 new), in ~**1 s** server time |
| Grouping accuracy vs hidden ground truth | **ARI 0.97, purity 1.00** |
| Critical incident | priority **94**, 46 reports, **38 independent sources**, 8 duplicates counted once, **~127 m** corridor, **~32 households est.** |
| Small but dangerous | **3 reports → priority 75** via severity floor (base 36) |
| Loud but minor | 10 reports, **1 source → priority 19** |
| Tests | **85 automated tests**, no network or keys needed |

**ARI (Adjusted Rand Index)** measures how closely the automatic grouping matches the true grouping. 1.0 is perfect; 0.97 means nearly every report landed in the right incident. The truth labels are used **only by the tests**, never by the system itself.

---

## 7. Why the priority can be trusted (explainability)

**Priority (0–100) = sum of 8 weighted factors**, each stored with its value, weight, contribution and a sentence:

| Factor | Max points | Rewards |
| --- | ---: | --- |
| Independent volume | 18 | many *distinct* sources (log scale, duplicates excluded) |
| Velocity | 15 | reports accelerating in the last 3 h vs the 3 h before |
| Residential impact | 15 | estimated households affected |
| Duration unresolved | 12 | how long it has been going on |
| Health risk | 12 | contamination, disease or mosquito mentions |
| Source diversity | 10 | phone + WhatsApp + social + news + portal + field; bonus for official/field |
| Sensitive location | 10 | school, hospital or market within 150 m |
| Road obstruction | 8 | road reported blocked |

Plus the **severity floor**: a severe hazard near a sensitive place is never below **75**.

Bands: **CRITICAL ≥80 · HIGH 60–79 · MEDIUM 35–59 · LOW <35**.

**Confidence** is separate from priority. It reflects how sure we are, based on source diversity, number of sources, location precision, and whether an official or field officer has corroborated it.

---

## 8. Responsible design

| Principle | How it's enforced |
| --- | --- |
| Estimates are never presented as facts | "est." on households and corridors; the brief separates facts from AI assessment |
| No invented numbers | the brief template is tested to only use numbers from its data; any LLM output with a new number is rejected |
| No hallucinated places | locations only come from the local gazetteer; the model can never supply coordinates |
| Safety cues can't be overridden | "open manhole" always stays a manhole with severity 5 |
| Works offline | no API key needed; the LLM is optional and falls back to deterministic rules |
| Honest data labels | `DEMO DATA` / `LIVE WEB DATA · unverified` badges always visible |
| Privacy | synthetic handles only; live authors are hashed, never stored |
| Human in the loop | recommendations are "AI suggestions"; status changes are made by operators |

---

## 9. Tech stack and design choices

| Layer | Choice | Why |
| --- | --- | --- |
| Backend | **Python + FastAPI** | fast to build, typed contracts, auto API docs at `/docs` |
| Storage | **SQLite** (plain `sqlite3`) | zero setup for a demo; schema shaped for a later move to PostGIS |
| Text similarity | hand-written **TF-IDF** | same maths as scikit-learn, no heavy dependencies |
| Corridor | **PCA** on report positions | finds the line the complaints fall along; 10th–90th percentile = affected stretch |
| Frontend | **React + TypeScript + Vite + Tailwind** | fast, typed, clean dark command-center UI |
| Map | **Leaflet** + custom heat layer | lightweight; Esri dark basemap (CARTO now needs a key) |
| Live data | **Tavily** (web/news search) + **Apify** (configurable scraper Actor) | two independent real-world sources through one adapter interface |
| LLM (optional) | provider adapter; rules mode by default | runs with zero keys; an open-source model (e.g. via Groq) can be added behind the same adapter |

Key architectural decisions worth mentioning:

- **One pipeline for everything.** Demo, Tavily and Apify all become the same report format. There are no source-specific scoring rules.
- **Incidents are derived, not edited.** After every new report, all of an incident's numbers are recomputed from its reports, so they can't drift.
- **Truth isolation.** The pipeline's input type has no ground-truth field; only the tests see it.
- **Demo and live datasets are separate files** with the same schema, so real data never contaminates the reproducible demo.

---

## 10. Live data integration (Tavily + Apify)

```text
Tavily  (Hyderabad sewerage search queries; default 8, news, last month; set in .env) ─┐
                                                                  ├─► normalize → one report format → existing pipeline
Apify   (configurable Actor, default Google Search scraper)      ─┘
```

- **Provenance saved** for every live report: URL, title, original snippet, the search queries that found it, published date (only if supplied), ingestion time.
- **Duplicates:** the same URL from several queries or from both sources becomes one report; re-fetching never re-inserts; near-identical reposts use the existing duplicate rule.
- **Failure-tolerant:** a missing key shows *not configured*; a failing source shows *failed* with a reason, and the other source still runs; with both down, demo mode is untouched.
- **Configurable:** queries, result counts, time range, the Apify Actor and its input are all in `.env`; nothing is hard-coded.

What to say about live results: real articles are messier than the demo. Many don't name a specific road, and some aren't about sewerage. The system labels those *off-topic* or *unlocated* instead of guessing, and that honesty is a feature.

---

## 11. Quality and testing

- **85 automated tests** covering the place list, the synthetic data generator, extraction (including mocked LLM responses), every acceptance criterion, brief safety, all API endpoints, and Tavily/Apify ingestion with mocked responses running through the real pipeline.
- The tests need **no internet and no keys**.
- A separate **real-API smoke test** (`backend/scripts/smoke_live_ingest.py`) checks the live services against a throwaway database.
- Frontend: TypeScript type-check and production build both pass.

---

## 12. Limitations (say these before someone asks)

1. **Illustrative geography.** Road names and lines are demo fixtures, not HMWSSB GIS. Corridors are statistical estimates, not pipe segments.
2. **Estimates are estimates.** Households and affected stretches are marked "est." and need field verification.
3. **Live web data is sparse and vague.** News rarely names a road, so many live reports are locality-level or unlocated.
4. **Online grouping is order-dependent.** Rarely, a vague report joins a neighbouring incident (1 of 96 in the demo batch).
5. **Prototype scale.** SQLite on one machine; not built for many simultaneous users.
6. **LLM path not exercised live.** The LLM adapter is tested with recorded responses; the demo runs in deterministic rules mode.
7. **English only.** No Telugu or Hindi language processing yet.

---

## 13. Roadmap

| Next | Why |
| --- | --- |
| Connect the real HMWSSB complaint feed | same report format, no pipeline changes |
| Open-source LLM (e.g. Qwen via Groq) for messy text and Telugu | better extraction from informal complaints |
| Real GIS: HMWSSB sewer network, road snapping | corridors become actual pipe segments |
| PostGIS + embeddings | city scale; better semantic matching |
| IoT manhole level sensors | detect overflows before anyone complains |
| Feedback loop from field verification | tune weights with real outcomes |

---

## 14. Likely questions and answers

**Q: How do you know two complaints are the same incident?**
A: A weighted score of four things: similar wording (30%), physical distance to the incident (35%), time since its last report (15%), and compatible problem type (20%). At 0.55 or above it joins; otherwise it starts a new incident. The score and its parts are stored and shown in the evidence drawer.

**Q: Isn't this just counting complaints?**
A: No. Raw count isn't even a factor. We count *independent sources* on a log scale, so ten posts from one account count once. Our demo has a 10-report, 1-source incident ranked far below a 3-report open manhole.

**Q: Is it using AI? Can it hallucinate?**
A: The core runs on deterministic, auditable rules, and the demo uses no LLM at all. An LLM can optionally help read messy text, but it's boxed in: it can only choose places from our list, can't supply coordinates, can't invent numbers, and can't downgrade a safety hazard. If it fails, the rules take over.

**Q: How accurate is it?**
A: On the synthetic benchmark the grouping scores ARI 0.97 against hidden ground truth, which is used only by the tests. Real-world accuracy needs real labelled complaints; that's the next step.

**Q: What if the internet or Tavily/Apify goes down?**
A: Each source fails independently and reports why. The rest of the system, including the full demo, keeps working offline.

**Q: Why is real data kept separate from demo data?**
A: So the demo stays reproducible and real articles never merge into fake incidents. It's the same code and schema, just a different database file.

**Q: How does it know the affected stretch of road?**
A: It takes the precise report locations, finds the main direction they spread along (PCA), and uses the middle 80% as the corridor. If they don't form a line, it shows a radius instead.

**Q: What is "velocity"?**
A: Reports in the latest 3 hours compared with the 3 hours before. At 2.5× or more, with at least 6 recent reports, it's rapidly escalating. Duplicates don't count.

**Q: Could this replace the complaint system?**
A: No, and it shouldn't. It's an intelligence layer on top; tickets and dispatch stay where they are.

**Q: How would it scale to the whole city?**
A: Swap SQLite for PostgreSQL/PostGIS, use a spatial index for nearby-incident lookups, and optionally embeddings for similarity. The API and UI don't change.

**Q: What about privacy?**
A: Demo handles are synthetic. For live data, author names are hashed into pseudonyms and never stored; only public content and its URL are kept.

---

## 15. If something goes wrong on stage

| Symptom | Fix |
| --- | --- |
| "Fetch live data" is greyed out | The backend was started before the keys were added: restart it (checklist step 1–4) |
| Live mode shows no incidents | You haven't fetched yet, or all results were off-topic. Say so; that's the filter working |
| Map background is blank | No internet for the map tiles; incidents and markers still work |
| Numbers look different from this guide | Someone ran extra simulations: click **Reset demo** |
| Simulation button does nothing | You're in Live mode; simulation only runs on demo data |
| Error banner "API unavailable" | The backend isn't running: start it and click **Retry** |

---

## 16. Glossary

| Term | Meaning |
| --- | --- |
| **Report / signal** | one complaint from one source |
| **Incident** | the real-world problem one or more reports describe |
| **Gazetteer** | the local list of localities, roads and landmarks with coordinates |
| **Independent sources** | distinct reporting accounts, with duplicates removed |
| **Corridor** | the estimated stretch of road affected |
| **Velocity** | whether the report rate is rising or falling |
| **Severity floor** | a rule that keeps severe hazards near schools, hospitals and markets at priority ≥75 |
| **Provenance** | where a live report came from: URL, query, source, time |
| **TF-IDF** | a standard way to measure how similar two texts are |
| **ARI** | a 0–1 score of how well automatic grouping matches the truth |

---

*Related docs: `README.md` (setup), `docs/08-extract-and-pipeline-explained.md` (technical deep-dive with a traced example), `docs/00–07` (original specification).*
