"""Deterministic synthetic complaint generation.

Everything here is fabricated demo data: handles are synthetic, there are no people or phone
numbers, and places come from the illustrative gazetteer. `truth_incident` is attached to the
GeneratedReport wrapper only — the pipeline receives `.report` (an IncomingReport), which has no
ground-truth field.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from .config import BASELINE_REPORT_COUNT, SIMULATION_REPORT_COUNT
from .gazetteer import LOCALITIES, ROADS, SENSITIVE_KINDS, Road, landmarks_for_road, offset_point, point_on_road, road_for
from .schemas import IncomingReport

SOURCES = ("phone", "social", "whatsapp", "news", "official", "field")
# Probability that a report from this source carries a device location pin.
GPS_SHARE = {"phone": 0.0, "social": 0.35, "whatsapp": 0.75, "news": 0.0, "official": 0.6, "field": 1.0}

ISSUE_PHRASES: dict[str, tuple[str, ...]] = {
    "overflow": (
        "sewage overflowing",
        "drain overflowing outside my house",
        "sewer overflow",
        "manhole overflowing",
        "dirty sewage water gushing out of the manhole and overflowing",
        "underground drainage overflowing",
        "sewage water overflowing onto the lane",
    ),
    "blockage": (
        "sewer line blocked",
        "sewage line is choked",
        "sewage not clearing from the line",
        "UGD line blockage",
        "sewer choke in the main line",
        "drainage line jammed",
    ),
    "foul_smell": (
        "unbearable sewage smell",
        "foul smell from the sewer",
        "stink from the drainage",
        "bad odour from the sewer line",
        "rotten sewage smell all day",
        "terrible sewer stench",
    ),
    "manhole": (
        "open manhole",
        "manhole cover missing",
        "broken manhole cover",
        "uncovered manhole",
        "manhole lid broken and left open",
    ),
    "sewage_in_house": (
        "sewage entering houses",
        "drain water coming back into homes",
        "sewage backing up inside our house",
        "dirty drain water inside the house",
    ),
    "damaged_pipeline": (
        "sewer pipeline burst",
        "damaged sewer pipe",
        "leaking underground sewer line",
        "sewer pipe broken and leaking",
    ),
    "drain_blockage": (
        "storm drain choked",
        "nala blocked with waste",
        "roadside drain not flowing",
        "drain blockage near the culvert",
    ),
    "road_flooding": (
        "sewage flooding the road",
        "road covered in sewage water",
        "wastewater stagnant on the road",
        "street under dirty sewage water",
    ),
}

SOURCE_TEMPLATES: dict[str, tuple[str, ...]] = {
    "phone": (
        "Caller reports {issue} {loc}.{extras}",
        "Citizen called: {issue} {loc}.{extras} Requests urgent attention.",
        "Phone complaint — {issue} {loc}.{extras}",
        "Resident on call says {issue} {loc}.{extras}",
        "Call log: {issue}, {loc}.{extras}",
        "IVR complaint: {issue} {loc}.{extras} Caller wants a team sent.",
    ),
    "social": (
        "@HMWSSB {issue} {loc}!{extras} #Hyderabad",
        "Again {issue} {loc}. When will this be fixed? @HMWSSB{extras}",
        "{Issue} {loc}.{extras} #SewerIssue",
        "Tagging @HMWSSB — {issue} {loc}.{extras}",
        "Is anyone looking at this? {Issue} {loc}.{extras}",
        "{Issue} {loc} and nobody cares.{extras} #GHMC",
    ),
    "whatsapp": (
        "Neighbours pls note: {issue} {loc}.{extras}",
        "Sharing location — {issue} {loc}.{extras}",
        "Colony group: {issue} {loc}.{extras} Someone raise complaint pls",
        "{Issue} {loc}, sending photos.{extras}",
        "Forwarded: {issue} {loc}.{extras}",
        "Guys {issue} {loc} again.{extras}",
    ),
    "news": (
        "Residents complain of {issue} {loc}.{extras}",
        "Locals report {issue} {loc}; civic officials yet to respond.{extras}",
        "Commuters face trouble due to {issue} {loc}.{extras}",
        "{Issue} {loc} leaves residents fuming.{extras}",
        "Civic watch: {issue} {loc}.{extras}",
        "Area residents allege {issue} {loc}.{extras}",
    ),
    "official": (
        "Grievance: {issue}. Location: {loc}.{extras}",
        "Portal complaint — sewerage; {issue}; {loc}.{extras}",
        "Sewerage grievance registered: {issue} {loc}.{extras}",
        "Complaint logged: {issue} {loc}.{extras}",
        "Online grievance: {issue}, {loc}.{extras}",
        "Citizen portal: {issue} reported {loc}.{extras}",
    ),
    "field": (
        "Field note: {issue} {loc}.{extras}",
        "Site inspection: {issue} {loc}.{extras}",
        "Officer observation — {issue} {loc}.{extras}",
        "Inspection report: {issue} {loc}.{extras} Team informed.",
        "Lineman update: {issue} {loc}.{extras}",
        "Field visit confirms {issue} {loc}.{extras}",
    ),
}

HOUSEHOLD_PHRASES = ("About {n} houses affected.", "Nearly {n} families affected.", "~{n} households hit.", "{n} homes affected.")
BLOCKED_PHRASES = ("Road is blocked.", "Vehicles cannot pass.", "Traffic stuck because of it.", "Road completely blocked.")
HEALTH_PHRASES = ("Mosquitoes everywhere, health risk.", "Kids falling sick.", "Worried about disease spreading.", "Fear of contamination in drinking water.")
SCHOOL_PHRASES = ("Right next to the school gate.", "Children walk past this to school.", "School kids pass here every day.")
HOSPITAL_PHRASES = ("Just outside the hospital entrance.", "Patients have to walk through this near the hospital.")

# Informal / misspelt variants residents use. The extractor must recover canonical names.
LOCALITY_VARIANTS = {"Kukatpally": ("Kukatpalli", "kukatpally"), "Dilsukhnagar": ("Dilshuknagar",), "Secunderabad": ("Secundrabad",)}
ROAD_VARIANTS = {"Road No. 5": ("Road 5", "Rd No 5", "road number 5", "Road no.5")}

OUT_OF_SCOPE = (
    ("phone", "Garbage pickup has not happened for three days near Ameerpet Vegetable Market."),
    ("social", "@HMWSSB water pressure is very low in KPHB today, tanks not filling."),
    ("whatsapp", "Congratulations! Win a free phone now, click this link to claim your prize."),
    ("official", "Streetlight not working near LB Nagar Metro Station for a week."),
)


@dataclass(frozen=True)
class GeneratedReport:
    report: IncomingReport
    truth_incident: str  # test-only ground truth; never passed to the pipeline


@dataclass
class IncidentSpec:
    key: str
    locality: str
    road: str
    category: str
    unique_reports: int
    age_hours: float  # first report, hours before `now`
    span_hours: float  # first-to-last report spread
    pattern: str = "steady"  # steady | accelerating | declining | hero
    households: int = 0
    blocked: bool = False
    health: bool = False
    sensitive_phrase: Optional[str] = None  # "school" | "hospital"
    duplicates: int = 0
    one_handle_source: Optional[str] = None
    source_cycle: tuple[str, ...] = SOURCES
    location_weights: dict[str, float] = field(default_factory=lambda: {"landmark": 0.3, "road": 0.5, "locality": 0.2})
    extra_rate: float = 0.5
    vague_reports: int = 0  # reports with no usable location text
    gps_spread: tuple[float, float] = (0.1, 0.9)


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _stable_id(*parts: str) -> str:
    return "RPT-" + hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]


def _slug(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def _jitter(point: tuple[float, float], rng: random.Random, low_m: float = 5.0, high_m: float = 25.0) -> tuple[float, float]:
    distance, bearing = rng.uniform(low_m, high_m), rng.uniform(0, 2 * math.pi)
    lat, lon = offset_point(point[0], point[1], math.cos(bearing) * distance, math.sin(bearing) * distance)
    return round(lat, 6), round(lon, 6)


def _offsets(spec: IncidentSpec, rng: random.Random) -> list[float]:
    """Hours relative to `now` (negative = past), sorted ascending."""
    count = spec.unique_reports
    if spec.pattern == "hero":
        hero = [-18] * 2 + [-14] * 2 + [-10] * 3 + [-7] * 2 + [-5] * 2 + [-4] * 3 + [-3] * 6 + [-2] * 9 + [-1] * 10
        if count != len(hero):
            raise ValueError("Hero timing expects 39 unique reports")
        return sorted(value + rng.uniform(-0.35, 0.35) for value in hero)
    values = []
    for index in range(count):
        u = (index + 0.5) / count
        if spec.pattern == "accelerating":
            u = math.sqrt(u)
        elif spec.pattern == "declining":
            u = u * u
        values.append(-spec.age_hours + spec.span_hours * u + rng.uniform(-0.2, 0.2))
    return sorted(values)


def _location_text(kind: str, locality: str, road: Road, landmark: str, rng: random.Random) -> str:
    locality_text = rng.choice((locality, *LOCALITY_VARIANTS.get(locality, ()))) if rng.random() < 0.3 else locality
    road_text = rng.choice(ROAD_VARIANTS.get(road.name, (road.name,))) if rng.random() < 0.35 else road.name
    if kind == "landmark":
        return rng.choice((
            f"near {landmark}, {road_text}",
            f"opposite {landmark}",
            f"beside {landmark} on {road_text}, {locality_text}",
            f"close to {landmark}, {locality_text}",
        ))
    if kind == "road":
        return rng.choice((
            f"on {road_text}, {locality_text}",
            f"at {road_text} in {locality_text}",
            f"{road_text}, {locality_text}",
            f"along {road_text} ({locality_text})",
        ))
    if kind == "locality":
        return rng.choice((f"in {locality_text}", f"in {locality_text} area", f"somewhere in {locality_text}"))
    return rng.choice(("near my house", "in our lane", "near the school", "at our colony"))


def _extras(spec: IncidentSpec, rng: random.Random, claimed_hours: float) -> str:
    parts: list[str] = []
    if spec.households and rng.random() < spec.extra_rate:
        claimed = max(1, round(spec.households * rng.uniform(0.85, 1.12)))
        parts.append(rng.choice(HOUSEHOLD_PHRASES).format(n=claimed))
    if spec.blocked and rng.random() < spec.extra_rate:
        parts.append(rng.choice(BLOCKED_PHRASES))
    if spec.health and rng.random() < spec.extra_rate:
        parts.append(rng.choice(HEALTH_PHRASES))
    if spec.sensitive_phrase == "school" and rng.random() < spec.extra_rate + 0.2:
        parts.append(rng.choice(SCHOOL_PHRASES))
    if spec.sensitive_phrase == "hospital" and rng.random() < spec.extra_rate + 0.2:
        parts.append(rng.choice(HOSPITAL_PHRASES))
    if rng.random() < 0.4:
        if claimed_hours >= 20:
            parts.append(rng.choice(("Since yesterday.", f"Going on for {round(claimed_hours)} hours.")))
        elif claimed_hours >= 2:
            parts.append(rng.choice((f"Since {round(claimed_hours)} hours.", f"For the last {round(claimed_hours)} hours.")))
    rng.shuffle(parts)
    return (" " + " ".join(parts)) if parts else ""


def _compose(source: str, issue: str, loc: str, extras: str, rng: random.Random) -> str:
    template = rng.choice(SOURCE_TEMPLATES[source])
    return template.format(issue=issue, Issue=issue[0].upper() + issue[1:], loc=loc, extras=extras).replace("..", ".").strip()


def _incident_reports(spec: IncidentSpec, now: datetime, rng: random.Random, handle_counters: dict[str, int]) -> list[GeneratedReport]:
    road = road_for(spec.locality, spec.road)
    if road is None:
        raise ValueError(f"Unknown road in spec: {spec.locality}/{spec.road}")
    landmarks = landmarks_for_road(spec.locality, spec.road)
    offsets = _offsets(spec, rng)
    first_offset = offsets[0]
    kinds = list(spec.location_weights)
    weights = [spec.location_weights[kind] for kind in kinds]
    vague_indexes = set(rng.sample(range(len(offsets)), spec.vague_reports)) if spec.vague_reports else set()
    def next_handle(source: str) -> str:
        prefix = f"{source}_{_slug(spec.locality)}"
        handle_counters[prefix] = handle_counters.get(prefix, handle_counters.get("__base__", 0)) + 1
        return f"{prefix}_{handle_counters[prefix]:03d}"

    fixed_handle = next_handle(spec.one_handle_source) if spec.one_handle_source else None
    result: list[GeneratedReport] = []
    for index, offset in enumerate(offsets):
        source = spec.one_handle_source or spec.source_cycle[index % len(spec.source_cycle)]
        handle = fixed_handle or next_handle(source)
        kind = "vague" if index in vague_indexes else rng.choices(kinds, weights)[0]
        landmark = rng.choice(landmarks).name
        issue = rng.choice(ISSUE_PHRASES[spec.category])
        extras = _extras(spec, rng, claimed_hours=offset - first_offset + 1)
        text = _compose(source, issue, _location_text(kind, spec.locality, road, landmark, rng), extras, rng)
        created = now + timedelta(hours=offset)
        gps = None
        if kind != "vague" and rng.random() < GPS_SHARE[source]:
            low, high = spec.gps_spread
            gps = _jitter(point_on_road(road, rng.uniform(low, high)), rng)
        report = IncomingReport(
            id=_stable_id(spec.key, handle, _iso(created), text),
            source=source,
            source_handle=handle,
            raw_text=text,
            created_at=_iso(created),
            gps_lat=gps[0] if gps else None,
            gps_lon=gps[1] if gps else None,
        )
        result.append(GeneratedReport(report, spec.key))
    # Near-exact reposts by the same handle: evidence, not independent corroboration.
    candidates = sorted(result[len(result) // 2:], key=lambda item: item.report.created_at)
    for index in range(spec.duplicates):
        original = candidates[(index * 3) % len(candidates)].report
        created = datetime.fromisoformat(original.created_at) + timedelta(minutes=10 + 3 * index)
        text = original.raw_text if index % 2 == 0 else original.raw_text + " Please act!"
        report = original.model_copy(update={"id": _stable_id(spec.key, original.source_handle, _iso(created), text, "dup"), "raw_text": text, "created_at": _iso(created)})
        result.append(GeneratedReport(report, spec.key))
    return result


def _out_of_scope(now: datetime, seed: int = 42) -> list[GeneratedReport]:
    reports = []
    for index, (source, text) in enumerate(OUT_OF_SCOPE):
        created = now - timedelta(hours=index * 2 + 1.5)
        handle = f"{source}_misc_{900 + index:03d}"
        # Seed 42 keeps its original ids; later batches must not collide with it within the same second.
        report_id = _stable_id("OUT", handle, _iso(created), text) if seed == 42 else _stable_id("OUT", handle, _iso(created), text, str(seed))
        reports.append(GeneratedReport(IncomingReport(id=report_id, source=source, source_handle=handle, raw_text=text, created_at=_iso(created)), f"OUT-{index}"))
    return reports


BATCH_SPECS: tuple[IncidentSpec, ...] = (
    IncidentSpec("TRUTH-HERO", "Kukatpally", "Road No. 5", "overflow", 39, 18, 17, pattern="hero", households=36, blocked=True, health=True,
                 sensitive_phrase="school", duplicates=8, source_cycle=("social", "whatsapp", "phone", "whatsapp", "social", "field", "official", "news", "whatsapp", "social"),
                 location_weights={"landmark": 0.35, "road": 0.6, "locality": 0.05}, extra_rate=0.55, vague_reports=1, gps_spread=(0.18, 0.86)),
    IncidentSpec("TRUTH-DANGER", "Miyapur", "Hafeezpet Road", "manhole", 3, 5, 3, households=0, sensitive_phrase="school",
                 source_cycle=("phone", "whatsapp", "field"), location_weights={"landmark": 0.6, "road": 0.4}, extra_rate=0.9),
    IncidentSpec("TRUTH-INFLATED", "Madhapur", "Kavuri Hills Road", "foul_smell", 10, 20, 16, households=3, one_handle_source="social",
                 location_weights={"road": 0.6, "landmark": 0.4}, extra_rate=0.3),
    IncidentSpec("TRUTH-03", "Gachibowli", "Old Mumbai Highway Service Road", "blockage", 4, 10, 8, households=12, source_cycle=("phone", "social", "official", "whatsapp")),
    IncidentSpec("TRUTH-04", "Kondapur", "Raghavendra Colony Road", "road_flooding", 3, 6, 5, pattern="accelerating", households=9, blocked=True),
    IncidentSpec("TRUTH-05", "Ameerpet", "Srinivasa Nagar Road", "sewage_in_house", 3, 12, 10, households=7, health=True, source_cycle=("phone", "whatsapp", "official")),
    IncidentSpec("TRUTH-06", "Begumpet", "Airport Road Service Lane", "damaged_pipeline", 3, 30, 20, pattern="declining", households=8),
    IncidentSpec("TRUTH-07", "Secunderabad", "Station Road", "drain_blockage", 3, 20, 14, households=11, source_cycle=("news", "social", "field")),
    IncidentSpec("TRUTH-08", "Tarnaka", "Lalapet Road", "overflow", 3, 4, 3, pattern="accelerating", households=10, blocked=True, health=True),
    IncidentSpec("TRUTH-09", "Uppal", "Ramanthapur Road", "foul_smell", 2, 40, 10, pattern="declining", households=3),
    IncidentSpec("TRUTH-10", "LB Nagar", "Sagar Ring Road Service Lane", "blockage", 2, 6, 4, households=6),
    IncidentSpec("TRUTH-11", "Dilsukhnagar", "Dilsukhnagar Main Road", "manhole", 2, 16, 6, health=True, source_cycle=("social", "official")),
    IncidentSpec("TRUTH-12", "Mehdipatnam", "Asif Nagar Road", "road_flooding", 2, 9, 5, households=8, blocked=True),
    IncidentSpec("TRUTH-13", "Attapur", "Rambagh Road", "sewage_in_house", 2, 25, 12, households=5, health=True),
    IncidentSpec("TRUTH-14", "Charminar", "Shalibanda Road", "damaged_pipeline", 2, 3, 2, households=2, source_cycle=("whatsapp", "field")),
    IncidentSpec("TRUTH-15", "Jubilee Hills", "Film Nagar Road", "drain_blockage", 2, 14, 10, households=7),
    IncidentSpec("TRUTH-16", "Malkajgiri", "Anandbagh Road", "overflow", 3, 7, 6, pattern="accelerating", households=9, health=True, sensitive_phrase="hospital",
                 source_cycle=("phone", "official", "whatsapp")),
)


def generate_batch(n: int = SIMULATION_REPORT_COUNT, now: datetime | None = None, hero: bool = True, seed: int = 42) -> list[GeneratedReport]:
    """The 100-report demo batch: 96 in-scope reports from 17 hidden incidents plus 4 out-of-scope.

    Identical arguments give identical output. Later simulations pass a different `seed` so their
    wording and handles differ (new people reporting), while the composition stays the same."""
    if n != SIMULATION_REPORT_COUNT:
        raise ValueError("The demo batch intentionally contains exactly 100 reports.")
    now, rng = (now or utc_now()), random.Random(seed)
    counters: dict[str, int] = {"__base__": (seed - 42) * 100}
    reports: list[GeneratedReport] = []
    for spec in BATCH_SPECS:
        if spec.key == "TRUTH-HERO" and not hero:
            continue
        reports.extend(_incident_reports(spec, now, rng, counters))
    if hero and len(reports) != 96:
        raise AssertionError(f"Batch composition drifted: {len(reports)} in-scope reports")
    reports.extend(_out_of_scope(now, seed))
    return sorted(reports, key=lambda item: item.report.created_at)


def _baseline_specs(rng: random.Random) -> list[IncidentSpec]:
    used = {(spec.locality, spec.road) for spec in BATCH_SPECS}
    roads = [road for road in ROADS if (road.locality, road.name) not in used]
    rng.shuffle(roads)
    categories = list(ISSUE_PHRASES)
    # Sizes are random but sum exactly to the baseline count.
    sizes = [rng.randint(4, 12) for _ in roads]
    index = 0
    while sum(sizes) != BASELINE_REPORT_COUNT:
        step = 1 if sum(sizes) < BASELINE_REPORT_COUNT else -1
        if 3 <= sizes[index % len(sizes)] + step <= 15:
            sizes[index % len(sizes)] += step
        index += 1
    # Keep the baseline plausible: most incidents beside schools/hospitals/markets are nuisance-level,
    # with only a couple severe enough to trigger the severity floor.
    mild = ("foul_smell", "blockage", "drain_blockage")
    severe_sensitive_budget = 2
    specs: list[IncidentSpec] = []
    for index, (road, size) in enumerate(zip(roads, sizes)):
        duplicates = 1 if size >= 8 and rng.random() < 0.4 else 0
        age = rng.uniform(4, 70)
        category = categories[index % len(categories)]
        blocked, health = rng.random() < 0.2, rng.random() < 0.3
        sensitive_road = any(landmark.kind in SENSITIVE_KINDS for landmark in landmarks_for_road(road.locality, road.name))
        if sensitive_road and (category not in mild or blocked or health):
            if severe_sensitive_budget > 0:
                severe_sensitive_budget -= 1
            else:
                category, blocked, health = mild[index % len(mild)], False, False
        specs.append(IncidentSpec(
            key=f"BASE-{index + 1:02d}", locality=road.locality, road=road.name, category=category,
            unique_reports=size - duplicates, age_hours=age, span_hours=min(age - 0.5, rng.uniform(2, 16)),
            pattern=rng.choice(("steady", "steady", "accelerating", "declining")), households=rng.randint(2, 30),
            blocked=blocked, health=health, duplicates=duplicates,
            source_cycle=tuple(rng.sample(SOURCES, len(SOURCES))), extra_rate=0.45,
        ))
    return specs


def generate_baseline(n: int = BASELINE_REPORT_COUNT, now: datetime | None = None) -> list[GeneratedReport]:
    """~300 reports over three days on roads the demo batch does not use."""
    if n != BASELINE_REPORT_COUNT:
        raise ValueError("The baseline intentionally contains exactly 300 reports.")
    now, rng = (now or utc_now()), random.Random(314159)
    counters: dict[str, int] = {}
    reports: list[GeneratedReport] = []
    for spec in _baseline_specs(rng):
        reports.extend(_incident_reports(spec, now, rng, counters))
    reports.sort(key=lambda item: item.report.created_at)
    if len(reports) != n:
        raise AssertionError(f"Baseline composition drifted: {len(reports)} reports")
    return reports


def locality_names() -> list[str]:
    return list(LOCALITIES)
