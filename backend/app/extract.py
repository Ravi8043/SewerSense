"""Hybrid, auditable extraction.

1. Deterministic rule candidates (gazetteer, regexes, keywords, conservative fuzzy matching).
2. Optional structured LLM interpretation via a provider adapter.
3. Strict Pydantic validation of the provider output.
4. Deterministic reconciliation; coordinates always come from the local gazetteer.
5. Cache keyed by text, source, provider, model, schema and gazetteer versions.

Any provider problem (no key, timeout, invalid JSON, refusal, invented place) yields a
`rules_fallback` result — a report is never dropped because of the LLM.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from difflib import SequenceMatcher, get_close_matches
from typing import Any, Iterable, Optional

from pydantic import ValidationError

from .config import (
    CATEGORIES,
    EXTRACTION_CACHE_DIR,
    EXTRACTION_SCHEMA_VERSION,
    GPS_MAX_DISAGREEMENT_M,
    LLM_BATCH_DEADLINE_SECONDS,
    LLM_CONCURRENCY,
    LLM_MIN_CATEGORY_CONFIDENCE,
    COMPATIBLE_GROUPS,
    ensure_data_directories,
)
from .extraction_providers import ProviderError, ProviderRequest, StructuredExtractionProvider, get_provider
from .gazetteer import (
    GAZETTEER_VERSION,
    LANDMARKS,
    LOCALITIES,
    LOCALITY_ALIASES,
    ROADS,
    Landmark,
    Road,
    distance_m,
    in_hyderabad_bounds,
    landmark_for,
    road_for,
)
from .schemas import ExtractionResult, IncomingReport, LLMExtraction, RuleCandidates

# Ordered from most specific to most general; the first category with a cue wins.
CATEGORY_CUES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("manhole", ("open manhole", "manhole cover missing", "missing manhole cover", "broken manhole cover", "uncovered manhole", "manhole lid broken", "manhole left open", "manhole is open", "unsafe manhole")),
    ("sewage_in_house", ("entering houses", "entering the house", "into homes", "inside our house", "inside the house", "inside homes", "in my house", "backing up inside")),
    ("damaged_pipeline", ("pipeline burst", "pipe burst", "damaged sewer pipe", "sewer pipe broken", "leaking underground", "pipe broken", "pipeline damaged")),
    ("overflow", ("overflow", "overflowing", "gushing out")),
    ("drain_blockage", ("storm drain", "nala blocked", "nala choked", "drain not flowing", "drain blockage", "roadside drain", "culvert")),
    ("road_flooding", ("flooding the road", "flooding the street", "covered in sewage", "stagnant on the road", "under dirty sewage water", "road covered", "street under")),
    ("blockage", ("line blocked", "choked", "not clearing", "blockage", "choke", "jammed", "blocked")),
    ("foul_smell", ("smell", "stink", "stench", "odour", "odor")),
)
BASE_SEVERITY = {"manhole": 4, "sewage_in_house": 4, "overflow": 3, "road_flooding": 3, "damaged_pipeline": 3, "blockage": 2, "drain_blockage": 2, "foul_smell": 2}
SEWERAGE_TERMS = ("sewer", "sewage", "sewerage", "drain", "manhole", "ugd", "nala", "wastewater", "waste water")
EXCLUDED_TOPICS = ("garbage", "water pressure", "water supply", "streetlight", "street light", "electricity", "pothole")
SPAM_CUES = ("click this", "win a free", "claim your prize", "congratulations!")
BLOCKED_CUES = ("road is blocked", "road blocked", "road completely blocked", "cannot pass", "can't pass", "traffic stuck", "blocking the road", "road closed")
HEALTH_CUES = ("health", "mosquito", "disease", "sick", "fever", "contamination", "contaminated", "drinking water")
SENSITIVE_CUES = {"school": ("school",), "hospital": ("hospital", "clinic"), "market": ("market", "bazar", "bazaar")}
GEO_CONFIDENCE = {"exact": 0.9, "road": 0.8, "locality": 0.55, "none": 0.3}
FIELDS = ("category", "locality", "road", "landmark", "duration_hours", "households", "road_blocked", "health_risk", "near_sensitive", "in_scope", "severity")

_ROAD_NUMBER = re.compile(r"\b(?:road|rd)\.?\s*(?:no\.?|number|#)?\s*(\d{1,3})\b")


def normalize(text: str) -> str:
    value = re.sub(r"\s+", " ", text.lower()).strip()
    return _ROAD_NUMBER.sub(lambda match: f"road no. {match.group(1)}", value)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text)


def _contains(text: str, phrase: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", text) is not None


def _fuzzy_in_text(name: str, text: str, cutoff: float) -> bool:
    """Conservative fuzzy match of a place name against same-length token windows.

    Multi-word names must share at least one exact word (>=3 chars) with the window, which keeps
    matching fast and stops unrelated places matching on shape alone."""
    target_tokens = _tokens(normalize(name))
    target = " ".join(target_tokens)
    width = len(target_tokens)
    anchors = {token for token in target_tokens if len(token) >= 3}
    tokens = _tokens(text)
    for start in range(0, max(1, len(tokens) - width + 1)):
        window_tokens = tokens[start:start + width]
        if width > 1 and not anchors.intersection(window_tokens):
            continue
        matcher = SequenceMatcher(None, " ".join(window_tokens), target)
        if matcher.real_quick_ratio() >= cutoff and matcher.quick_ratio() >= cutoff and matcher.ratio() >= cutoff:
            return True
    return False


@dataclass
class _Match:
    name: str
    exact: bool


def _match_places(text: str, names: Iterable[str], cutoff: float = 0.88) -> list[_Match]:
    names = list(names)
    exact = [_Match(name, True) for name in names if _contains(text, normalize(name))]
    if exact:
        # Prefer the longest exact names ("Road No. 36" over nothing, specific over generic).
        exact.sort(key=lambda match: -len(match.name))
        return exact
    return [_Match(name, False) for name in names if len(name) >= 5 and _fuzzy_in_text(name, text, cutoff)]


@dataclass
class RuleResult:
    candidates: RuleCandidates
    category: Optional[str]
    locality: Optional[str]
    road: Optional[str]
    landmark: Optional[str]
    exact_location: dict[str, bool]
    duration_hours: Optional[float]
    households: Optional[int]
    road_blocked: bool
    health_risk: bool
    near_sensitive: Optional[str]
    in_scope: bool
    severity: int
    notes: list[str] = field(default_factory=list)


def _category(text: str) -> tuple[Optional[str], list[str]]:
    stripped = text
    for cue in BLOCKED_CUES:
        stripped = stripped.replace(cue, " ")
    cues = [category for category, phrases in CATEGORY_CUES if any(phrase in stripped for phrase in phrases)]
    return (cues[0] if cues else None), cues


def _duration(text: str) -> Optional[float]:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|days?)", text)
    if match:
        return float(match.group(1)) * (24 if match.group(2).startswith("day") else 1)
    for phrase, hours in (("since yesterday", 24.0), ("since last night", 12.0), ("since morning", 8.0), ("many hours", 12.0)):
        if phrase in text:
            return hours
    return None


def rule_candidates(raw_text: str) -> RuleResult:
    text = normalize(raw_text)
    notes: list[str] = []

    locality_matches = _match_places(text, LOCALITIES)
    for alias, canonical in LOCALITY_ALIASES.items():
        if _contains(text, alias) and canonical not in [match.name for match in locality_matches]:
            locality_matches.append(_Match(canonical, True))
    landmark_matches = _match_places(text, [landmark.name for landmark in LANDMARKS], cutoff=0.9)
    locality = locality_matches[0].name if locality_matches else None
    landmark = landmark_matches[0].name if landmark_matches else None
    landmark_item = landmark_for(landmark) if landmark else None
    if landmark_item and locality and landmark_item.locality != locality:
        # A named landmark is more specific than a locality mention.
        if landmark_item.locality in [match.name for match in locality_matches]:
            locality = landmark_item.locality
        else:
            notes.append(f"Landmark '{landmark}' is in {landmark_item.locality}, text also mentions {locality}; landmark used.")
            locality = landmark_item.locality
    elif landmark_item:
        locality = landmark_item.locality

    scoped_roads = [road.name for road in ROADS if locality is None or road.locality == locality]
    road_matches = _match_places(text, scoped_roads)
    road = road_matches[0].name if road_matches else None
    if road and locality is None:
        owners = [item.locality for item in ROADS if item.name == road]
        if len(owners) == 1:
            locality = owners[0]
        else:
            notes.append(f"Road '{road}' exists in several localities; locality unresolved.")
            road = None
    if landmark_item and road and road != landmark_item.road:
        notes.append(f"Landmark '{landmark}' is on {landmark_item.road}, text mentions {road}; landmark used.")
    if landmark_item:
        road = landmark_item.road

    category, category_cues = _category(text)
    has_sewer_term = any(term in text for term in SEWERAGE_TERMS)
    excluded = [cue for cue in EXCLUDED_TOPICS if cue in text]
    spam = [cue for cue in SPAM_CUES if cue in text]
    in_scope = has_sewer_term and not spam
    if not has_sewer_term:
        category = None
    households_match = re.search(r"(?:about|nearly|~|around)?\s*(\d{1,4})\s*(?:houses?|homes?|households?|families)", text)
    road_blocked = any(cue in text for cue in BLOCKED_CUES)
    health_risk = any(cue in text for cue in HEALTH_CUES)
    near_sensitive = next((kind for kind, cues in SENSITIVE_CUES.items() if any(_contains(text, cue) for cue in cues)), None)
    severity = BASE_SEVERITY.get(category or "", 1)
    if category == "manhole" and any(cue in text for cue in ("open", "missing", "uncovered", "left open")):
        severity = 5
    if road_blocked or health_risk:
        severity = min(5, severity + 1)

    candidates = RuleCandidates(
        locality_candidates=[match.name for match in locality_matches][:4],
        road_candidates=[match.name for match in road_matches][:4] if road_matches else ([road] if road else []),
        landmark_candidates=[match.name for match in landmark_matches][:4],
        explicit_claims={
            key: value
            for key, value in {
                "households": int(households_match.group(1)) if households_match else None,
                "duration_hours": _duration(text),
                "road_blocked": road_blocked or None,
                "health_risk": health_risk or None,
            }.items()
            if value is not None
        },
        category_cues=category_cues,
        excluded_topic_cues=excluded + spam,
        sensitive_cues=[near_sensitive] if near_sensitive else [],
    )
    exact_location = {
        "locality": any(match.exact and match.name == locality for match in locality_matches),
        "road": any(match.exact and match.name == road for match in road_matches) or bool(landmark_item),
        "landmark": any(match.exact and match.name == landmark for match in landmark_matches),
    }
    return RuleResult(
        candidates=candidates,
        category=category,
        locality=locality,
        road=road,
        landmark=landmark,
        exact_location=exact_location,
        duration_hours=_duration(text),
        households=int(households_match.group(1)) if households_match else None,
        road_blocked=road_blocked,
        health_risk=health_risk,
        near_sensitive=near_sensitive,
        in_scope=in_scope,
        severity=severity,
        notes=notes,
    )


# ---------------------------------------------------------------------------------------------
# LLM request, validation, reconciliation
# ---------------------------------------------------------------------------------------------
def _allowed_places(rules: RuleResult) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    localities = tuple(rules.candidates.locality_candidates) or tuple(LOCALITIES)
    scope = set(localities)
    roads = tuple(sorted({road.name for road in ROADS if road.locality in scope}))
    landmarks = tuple(sorted({landmark.name for landmark in LANDMARKS if landmark.locality in scope}))
    return localities, roads, landmarks


def build_request(raw_text: str, source: str, rules: RuleResult) -> ProviderRequest:
    localities, roads, landmarks = _allowed_places(rules)
    return ProviderRequest(raw_text=raw_text, source=source, candidates=rules.candidates, allowed_localities=localities, allowed_roads=roads, allowed_landmarks=landmarks, allowed_categories=(*CATEGORIES, "other"))


def validate_llm(data: Any) -> LLMExtraction:
    """Strict schema check. Raises ValidationError on unknown keys, bad types, or ranges."""
    return LLMExtraction.model_validate(data)


def _compatible(first: Optional[str], second: Optional[str]) -> bool:
    return bool(first and second) and any(first in group and second in group for group in COMPATIBLE_GROUPS)


def _resolve_coordinates(locality: Optional[str], road: Optional[str], landmark: Optional[str]) -> tuple[Optional[float], Optional[float], str, Optional[str], Optional[str]]:
    """Only permitted order: landmark → road midpoint → locality centroid → none."""
    landmark_item = landmark_for(landmark, locality) or landmark_for(landmark)
    if landmark_item:
        return landmark_item.lat, landmark_item.lon, "exact", landmark_item.locality, landmark_item.road
    road_item = road_for(locality, road)
    if road_item:
        lat, lon = road_item.midpoint
        return round(lat, 6), round(lon, 6), "road", road_item.locality, road_item.name
    if locality in LOCALITIES:
        lat, lon = LOCALITIES[locality]
        return lat, lon, "locality", locality, None
    return None, None, "none", None, None


def reconcile(raw_text: str, rules: RuleResult, llm: Optional[LLMExtraction], provider: Optional[StructuredExtractionProvider], fallback_reason: Optional[str] = None) -> ExtractionResult:
    text = normalize(raw_text)
    provenance: dict[str, str] = {name: ("rule" if llm else "fallback") for name in FIELDS}
    notes = list(rules.notes)
    values: dict[str, Any] = {
        "category": rules.category,
        "locality": rules.locality,
        "road": rules.road,
        "landmark": rules.landmark,
        "duration_hours": rules.duration_hours,
        "households": rules.households,
        "road_blocked": rules.road_blocked,
        "health_risk": rules.health_risk,
        "near_sensitive": rules.near_sensitive,
        "in_scope": rules.in_scope,
        "severity": rules.severity,
    }
    confidence_penalty = 0.0

    if llm is not None:
        # Geography: explicit exact rule matches are authoritative; the LLM may only fill gaps with
        # a valid gazetteer value that is a rule candidate or has conservative textual support.
        allowed_localities, allowed_roads, allowed_landmarks = _allowed_places(rules)
        for name, allowed, candidates in (
            ("locality", allowed_localities, rules.candidates.locality_candidates),
            ("landmark", allowed_landmarks, rules.candidates.landmark_candidates),
            ("road", allowed_roads, rules.candidates.road_candidates),
        ):
            proposal = getattr(llm, name)
            if proposal is None or proposal == values[name]:
                continue
            if proposal not in allowed:
                notes.append(f"Rejected LLM {name} '{proposal}' (not an allowed gazetteer value).")
                confidence_penalty += 0.1
                continue
            if values[name] and rules.exact_location.get(name):
                notes.append(f"Kept explicit {name} '{values[name]}' over LLM alternative '{proposal}'.")
                confidence_penalty += 0.05
                continue
            if proposal in candidates or _fuzzy_in_text(proposal, text, 0.75):
                values[name] = proposal
                provenance[name] = "llm" if not candidates else "reconciled"
            else:
                notes.append(f"Rejected LLM {name} '{proposal}' (no support in report text).")
                confidence_penalty += 0.1

        # Category: an explicit safety phrase is never overridden.
        if llm.category and llm.category != values["category"]:
            if values["category"] == "manhole" and rules.severity >= 5:
                notes.append("Explicit open-manhole safety cue kept over LLM category.")
            elif llm.category == "other":
                notes.append("LLM category 'other' ignored; rule category kept.")
            elif llm.category_confidence >= LLM_MIN_CATEGORY_CONFIDENCE and (values["category"] is None or len(rules.candidates.category_cues) > 1 or _compatible(values["category"], llm.category)):
                values["category"] = llm.category
                provenance["category"] = "reconciled" if rules.category else "llm"
            else:
                notes.append(f"Kept rule category '{values['category']}' over LLM '{llm.category}'.")
                confidence_penalty += 0.05

        # Numbers: explicit report values win; the LLM may not manufacture numbers.
        for name, claim in (("households", rules.households), ("duration_hours", rules.duration_hours)):
            proposal = getattr(llm, name)
            if proposal is None:
                continue
            if claim is not None:
                if abs(float(proposal) - float(claim)) > 1e-6:
                    notes.append(f"Report states {name}={claim}; LLM value {proposal} discarded.")
                continue
            has_support = bool(re.search(r"\d", text)) if name == "households" else any(word in text for word in ("since", "hour", "day", "yesterday", "night", "morning", "week"))
            if name == "households" and not re.search(r"\b" + str(int(proposal)) + r"\b", text):
                has_support = False
            if has_support:
                values[name] = proposal
                provenance[name] = "llm"
            else:
                notes.append(f"LLM {name} discarded: no explicit statement in report.")

        for name in ("road_blocked", "health_risk"):
            if getattr(llm, name) and not values[name]:
                values[name] = True
                provenance[name] = "llm"
        if llm.near_school_or_hospital and not values["near_sensitive"]:
            values["near_sensitive"] = "school" if "school" in text else "hospital" if "hospital" in text else None
            if values["near_sensitive"]:
                provenance["near_sensitive"] = "llm"

        if rules.candidates.excluded_topic_cues and any(cue in SPAM_CUES for cue in rules.candidates.excluded_topic_cues):
            values["in_scope"] = False
        elif llm.in_scope != values["in_scope"]:
            if llm.in_scope and llm.category not in (None, "other"):
                values["in_scope"] = True
                values["category"] = values["category"] or llm.category
                provenance["in_scope"] = "llm"
            elif not llm.in_scope and values["in_scope"]:
                notes.append("LLM marked out of scope; sewerage terms present so report kept in scope.")
                confidence_penalty += 0.05

        if llm.severity > values["severity"]:
            values["severity"] = llm.severity
            provenance["severity"] = "reconciled"

    if not values["in_scope"]:
        values["category"] = None
    lat, lon, geo_quality, locality, road = _resolve_coordinates(values["locality"], values["road"], values["landmark"])
    if geo_quality == "exact":
        values["locality"], values["road"] = locality, road
    elif geo_quality == "road":
        values["locality"] = locality
    elif geo_quality == "locality":
        values["road"] = None
    if geo_quality != "exact":
        values["landmark"] = None
    candidate_confidence = max(0.05, GEO_CONFIDENCE[geo_quality] - confidence_penalty)
    return ExtractionResult(
        category=values["category"],
        locality=values["locality"] if geo_quality != "none" else None,
        road=values["road"] if geo_quality in ("exact", "road") else None,
        landmark=values["landmark"],
        lat=lat,
        lon=lon,
        geo_quality=geo_quality,
        duration_hours=values["duration_hours"],
        severity=int(values["severity"]),
        households=values["households"],
        road_blocked=bool(values["road_blocked"]),
        health_risk=bool(values["health_risk"]),
        near_sensitive=values["near_sensitive"],
        in_scope=bool(values["in_scope"]),
        candidate_confidence=round(min(1.0, candidate_confidence), 2),
        field_provenance=provenance,
        reconciliation_notes=notes,
        extraction_mode="hybrid_validated" if llm else "rules_fallback",
        fallback_reason=None if llm else fallback_reason,
        provider=provider.name if (llm and provider) else None,
        model=provider.model if (llm and provider) else None,
        schema_version=EXTRACTION_SCHEMA_VERSION,
    )


# ---------------------------------------------------------------------------------------------
# Device location pin (source metadata) — applied after text extraction, never cached.
# ---------------------------------------------------------------------------------------------
def _point_segment_distance(lat: float, lon: float, road: Road) -> float:
    scale_x = 111_111 * math.cos(math.radians(lat))
    ax, ay = (road.start[1] - lon) * scale_x, (road.start[0] - lat) * 111_111
    bx, by = (road.end[1] - lon) * scale_x, (road.end[0] - lat) * 111_111
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, -(ax * dx + ay * dy) / (dx * dx + dy * dy or 1)))
    return math.hypot(ax + t * dx, ay + t * dy)


def apply_device_pin(result: ExtractionResult, gps_lat: Optional[float], gps_lon: Optional[float]) -> ExtractionResult:
    if gps_lat is None or gps_lon is None or not result.in_scope or not in_hyderabad_bounds(gps_lat, gps_lon):
        return result
    notes = list(result.reconciliation_notes)
    if result.geo_quality == "none":
        notes.append("Location from device pin only; no place named in text.")
        nearest = min(LOCALITIES, key=lambda name: distance_m(gps_lat, gps_lon, *LOCALITIES[name]))
        locality = nearest if distance_m(gps_lat, gps_lon, *LOCALITIES[nearest]) < 2_000 else None
        return result.model_copy(update={"lat": gps_lat, "lon": gps_lon, "geo_quality": "exact", "locality": locality, "reconciliation_notes": notes})
    if result.geo_quality in ("exact", "road") and result.road:
        road = road_for(result.locality, result.road)
        disagreement = _point_segment_distance(gps_lat, gps_lon, road) if road else distance_m(gps_lat, gps_lon, result.lat, result.lon)
        limit = GPS_MAX_DISAGREEMENT_M
    else:
        disagreement = distance_m(gps_lat, gps_lon, result.lat, result.lon)
        limit = 1_500.0
    if disagreement > limit:
        notes.append(f"Device pin {disagreement:.0f} m from named place; pin ignored.")
        return result.model_copy(update={"reconciliation_notes": notes})
    provenance = {**result.field_provenance}
    return result.model_copy(update={"lat": gps_lat, "lon": gps_lon, "geo_quality": "exact", "field_provenance": provenance, "reconciliation_notes": notes})


# ---------------------------------------------------------------------------------------------
# Cache and orchestration
# ---------------------------------------------------------------------------------------------
def cache_key(raw_text: str, source: str, provider_name: str, model: str) -> str:
    material = "|".join((normalize(raw_text), source, provider_name, model, EXTRACTION_SCHEMA_VERSION, GAZETTEER_VERSION))
    return hashlib.sha256(material.encode()).hexdigest()


def _cache_read(key: str) -> Optional[ExtractionResult]:
    path = EXTRACTION_CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        return ExtractionResult.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError):
        return None


def _cache_write(key: str, result: ExtractionResult) -> None:
    try:
        ensure_data_directories()
        (EXTRACTION_CACHE_DIR / f"{key}.json").write_text(result.model_dump_json(), encoding="utf-8")
    except OSError:
        pass  # caching is an optimisation only


def _llm_attempt(provider: StructuredExtractionProvider, request: ProviderRequest) -> tuple[Optional[LLMExtraction], Optional[str]]:
    try:
        return validate_llm(provider.extract(request)), None
    except ProviderError as error:
        return None, str(error)
    except ValidationError as error:
        return None, f"schema validation failed ({error.error_count()} errors)"
    except Exception as error:  # never let an adapter bug stop the pipeline
        return None, f"unexpected provider error: {type(error).__name__}"


@dataclass
class ExtractionStats:
    hybrid: int = 0
    fallback: int = 0
    cache_hits: int = 0
    reasons: dict[str, int] = field(default_factory=dict)
    rules_seconds: float = 0.0  # deterministic classification/candidate pass
    resolve_seconds: float = 0.0  # LLM, validation, reconciliation, geocoding

    @property
    def mode(self) -> str:
        if self.hybrid and not self.fallback:
            return "hybrid_validated"
        if self.hybrid:
            return "hybrid_partial"
        return "rules_fallback"


def extract_many(reports: list[IncomingReport], provider: Optional[StructuredExtractionProvider] | bool = True) -> tuple[dict[str, ExtractionResult], ExtractionStats]:
    """Extract all reports. LLM calls run concurrently under one wall-clock deadline so a slow
    provider cannot push /api/simulate past its latency budget; stragglers use rules fallback."""
    if provider is True:
        provider = get_provider()
    active = provider if (provider and provider.available()) else None
    stats = ExtractionStats()
    results: dict[str, ExtractionResult] = {}
    tick = time.perf_counter()
    rules_by_id = {report.id: rule_candidates(report.raw_text) for report in reports}
    stats.rules_seconds = time.perf_counter() - tick
    tick = time.perf_counter()
    pending: list[IncomingReport] = []
    for report in reports:
        if active:
            cached = _cache_read(cache_key(report.raw_text, report.source, active.name, active.model))
            if cached is not None:
                results[report.id] = cached
                stats.cache_hits += 1
                continue
            pending.append(report)
        else:
            reason = "extraction mode is rules-only" if provider is None else "no provider credentials configured"
            results[report.id] = reconcile(report.raw_text, rules_by_id[report.id], None, None, reason)

    if active and pending:
        deadline = time.monotonic() + LLM_BATCH_DEADLINE_SECONDS
        executor = ThreadPoolExecutor(max_workers=max(1, LLM_CONCURRENCY))
        futures = {executor.submit(_llm_attempt, active, build_request(report.raw_text, report.source, rules_by_id[report.id])): report for report in pending}
        done, _ = wait(futures, timeout=max(0.0, deadline - time.monotonic()))
        executor.shutdown(wait=False, cancel_futures=True)
        for future, report in futures.items():
            if future in done:
                llm, reason = future.result()
            else:
                llm, reason = None, "batch latency budget exceeded"
            result = reconcile(report.raw_text, rules_by_id[report.id], llm, active, reason)
            if llm is not None:
                _cache_write(cache_key(report.raw_text, report.source, active.name, active.model), result)
            results[report.id] = result

    for report in reports:
        result = apply_device_pin(results[report.id], report.gps_lat, report.gps_lon)
        results[report.id] = result
        if result.extraction_mode == "hybrid_validated":
            stats.hybrid += 1
        else:
            stats.fallback += 1
            key = result.fallback_reason or "unknown"
            stats.reasons[key] = stats.reasons.get(key, 0) + 1
    stats.resolve_seconds = time.perf_counter() - tick
    return results, stats


def extract(raw_text: str, source: str = "phone", gps: tuple[float, float] | None = None, provider: Optional[StructuredExtractionProvider] | bool = True) -> ExtractionResult:
    """Single-report convenience wrapper around extract_many."""
    report = IncomingReport(id="single", source=source, source_handle="single", raw_text=raw_text, created_at="1970-01-01T00:00:00+00:00", gps_lat=gps[0] if gps else None, gps_lon=gps[1] if gps else None)
    results, _ = extract_many([report], provider)
    return results["single"]


def details_json(result: ExtractionResult) -> str:
    """Non-sensitive provenance persisted with each report (never keys or raw provider output)."""
    return json.dumps(
        {
            "mode": result.extraction_mode,
            "provider": result.provider,
            "model": result.model,
            "schema_version": result.schema_version,
            "field_provenance": result.field_provenance,
            "reconciliation_notes": result.reconciliation_notes,
            "candidate_confidence": result.candidate_confidence,
            "fallback_reason": result.fallback_reason,
        },
        separators=(",", ":"),
    )


# Re-exported for tests and diagnostics.
__all__ = ["ExtractionStats", "apply_device_pin", "build_request", "cache_key", "details_json", "extract", "extract_many", "normalize", "reconcile", "rule_candidates", "validate_llm", "Landmark"]
