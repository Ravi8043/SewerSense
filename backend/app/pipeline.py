"""Deterministic, explainable complaint-to-incident intelligence pipeline.

Input is a list of IncomingReport objects (no ground-truth field). Every report is persisted,
extracted, de-duplicated, clustered online against active incidents, and each touched incident is
recomputed from its member reports. Weights and thresholds live in config.py.
"""

from __future__ import annotations

import math
import re
import sqlite3
import statistics
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from .config import (
    CLUSTER_RADIUS_M,
    CLUSTER_THRESHOLD,
    CLUSTER_TOP_K_SEMANTIC,
    CLUSTER_WEIGHTS,
    COMPATIBLE_CATEGORY_SCORE,
    COMPATIBLE_GROUPS,
    CONFIDENCE_BANDS,
    CONFIDENCE_SOURCE_SATURATION,
    CONFIDENCE_WEIGHTS,
    CORRIDOR_HIGH_PERCENTILE,
    CORRIDOR_LOW_PERCENTILE,
    CORRIDOR_MIN_EIGEN_RATIO,
    CORRIDOR_MIN_LENGTH_M,
    CORRIDOR_MIN_POINTS,
    CORRIDOR_WIDTH_M,
    DUPLICATE_SIMILARITY_THRESHOLD,
    DURATION_SATURATION_HOURS,
    GEO_QUALITY_SCORES,
    GEO_ROAD_FACTOR,
    GEO_SCALE_LOCALITY_M,
    GEO_SCALE_M,
    HOUSEHOLD_FRONTAGE_M,
    HOUSEHOLD_SATURATION,
    HOUSEHOLDS_PER_SOURCE,
    LOCALITY_UNCERTAINTY_M,
    MIN_RADIUS_M,
    OFFICIAL_FIELD_DIVERSITY_BOOST,
    PRIORITY_BANDS,
    PRIORITY_WEIGHTS,
    SENSITIVE_RADIUS_M,
    SEVERITY_FLOOR_MIN_SEVERITY,
    SEVERITY_FLOOR_PRIORITY,
    SOURCE_TYPE_COUNT,
    TIME_SCALE_HOURS,
    UNLOCATED_SEMANTIC_THRESHOLD,
    VELOCITY_BUCKETS,
    VELOCITY_MIN_WINDOW_REPORTS,
    VELOCITY_RULES,
    VELOCITY_VALUES,
    VOLUME_SATURATION_SOURCES,
)
from .db import PIPELINE_REPORT_COLUMNS, PIPELINE_REPORT_SELECT, dump_json, load_json, rows_to_dicts
from .extract import details_json, extract_many
from .extraction_providers import StructuredExtractionProvider
from .gazetteer import distance_m, nearest_sensitive
from .schemas import IncomingReport

ACTIVE_STATUSES = ("open", "verified", "dispatched")
_STOPWORDS = frozenset("the a an and or of to in on at is are was it this that for from with by near our my me we i be has have not no again please pls since".split())


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def haversine_m(lat_one: float, lon_one: float, lat_two: float, lon_two: float) -> float:
    return distance_m(lat_one, lon_one, lat_two, lon_two)


# ---------------------------------------------------------------------------------------------
# TF-IDF semantic similarity (smooth IDF + L2-normalised sparse vectors, as in scikit-learn)
# ---------------------------------------------------------------------------------------------
def _terms(text: str) -> list[str]:
    # Digits are kept ("road no. 5" must not collapse to "road no"); single letters are dropped.
    return [token for token in re.findall(r"[a-z]{2,}|[0-9]+", text.lower()) if token not in _STOPWORDS]


class TfidfModel:
    def __init__(self, corpus: Iterable[str]) -> None:
        documents = [set(_terms(text)) for text in corpus]
        self.document_count = len(documents)
        frequency: Counter[str] = Counter()
        for terms in documents:
            frequency.update(terms)
        self.idf = {term: math.log((1 + self.document_count) / (1 + count)) + 1 for term, count in frequency.items()}
        self._unseen_idf = math.log(1 + self.document_count) + 1
        self._cache: dict[str, dict[str, float]] = {}

    def vector(self, text: str) -> dict[str, float]:
        cached = self._cache.get(text)
        if cached is not None:
            return cached
        counts = Counter(_terms(text))
        weights = {term: count * self.idf.get(term, self._unseen_idf) for term, count in counts.items()}
        norm = math.sqrt(sum(value * value for value in weights.values())) or 1.0
        vector = {term: value / norm for term, value in weights.items()}
        self._cache[text] = vector
        return vector

    def similarity(self, left: str, right: str) -> float:
        first, second = self.vector(left), self.vector(right)
        if len(first) > len(second):
            first, second = second, first
        return sum(value * second.get(term, 0.0) for term, value in first.items())


def text_similarity(left: str, right: str) -> float:
    """Stand-alone cosine for two texts (IDF fitted on the pair)."""
    return TfidfModel([left, right]).similarity(left, right)


# ---------------------------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------------------------
def category_score(first: Optional[str], second: Optional[str]) -> float:
    if not first or not second:
        return 0.0
    if first == second:
        return 1.0
    return COMPATIBLE_CATEGORY_SCORE if any(first in group and second in group for group in COMPATIBLE_GROUPS) else 0.0


def _mode(values: Iterable[Any], default: Any = None) -> Any:
    usable = [value for value in values if value not in (None, "")]
    return Counter(usable).most_common(1)[0][0] if usable else default


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = (len(ordered) - 1) * percentile
    lower, upper = math.floor(index), math.ceil(index)
    return ordered[lower] if lower == upper else ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def band_for(priority: int) -> str:
    return next(label for threshold, label in PRIORITY_BANDS if priority >= threshold)


def confidence_label(confidence: float) -> str:
    return next(label for threshold, label in CONFIDENCE_BANDS if confidence >= threshold)


def corridor_for(points: list[tuple[float, float]]) -> tuple[Optional[dict[str, Any]], float, dict[str, Any]]:
    """PCA on located points in local metres. Returns (corridor or None, radius_m, diagnostics)."""
    if not points:
        return None, MIN_RADIUS_M, {"points": 0, "reason": "No located reports."}
    origin_lat = statistics.mean(point[0] for point in points)
    origin_lon = statistics.mean(point[1] for point in points)
    scale_x, scale_y = 111_111 * math.cos(math.radians(origin_lat)), 111_111
    xy = [((lon - origin_lon) * scale_x, (lat - origin_lat) * scale_y) for lat, lon in points]
    max_radius = max(math.hypot(x, y) for x, y in xy)
    radius = round(max(MIN_RADIUS_M, max_radius + 15), 1)
    if len(points) < CORRIDOR_MIN_POINTS:
        return None, radius, {"points": len(points), "reason": f"Fewer than {CORRIDOR_MIN_POINTS} precisely located reports; showing a radius."}
    cov_xx = statistics.mean(x * x for x, _ in xy)
    cov_yy = statistics.mean(y * y for _, y in xy)
    cov_xy = statistics.mean(x * y for x, y in xy)
    trace, determinant = cov_xx + cov_yy, cov_xx * cov_yy - cov_xy * cov_xy
    root = math.sqrt(max(0.0, trace * trace / 4 - determinant))
    first, second = trace / 2 + root, max(0.0, trace / 2 - root)
    if abs(cov_xy) > 1e-9:
        vector = (first - cov_yy, cov_xy)
    else:
        vector = (1.0, 0.0) if cov_xx >= cov_yy else (0.0, 1.0)
    norm = math.hypot(*vector) or 1.0
    unit = (vector[0] / norm, vector[1] / norm)
    projections = [x * unit[0] + y * unit[1] for x, y in xy]
    low, high = _percentile(projections, CORRIDOR_LOW_PERCENTILE), _percentile(projections, CORRIDOR_HIGH_PERCENTILE)
    length = max(0.0, high - low)
    ratio = first / max(second, 1e-6)
    spread = math.sqrt(second)
    diagnostics = {"points": len(points), "spread_m": round(spread, 1), "eigenvalue_ratio": round(min(ratio, 999.0), 2)}
    if length < CORRIDOR_MIN_LENGTH_M or ratio < CORRIDOR_MIN_EIGEN_RATIO:
        reason = "Reports are too tightly grouped for a corridor" if length < CORRIDOR_MIN_LENGTH_M else "Reports are not spread along a line"
        return None, radius, {**diagnostics, "reason": f"{reason}; showing a radius."}

    def to_latlon(projection: float) -> list[float]:
        x, y = unit[0] * projection, unit[1] * projection
        return [round(origin_lat + y / scale_y, 6), round(origin_lon + x / scale_x, 6)]

    reason = f"{len(points)} precisely located reports spread along a line (axis ratio {min(ratio, 999):.0f}:1, cross-spread ±{spread:.0f} m)."
    corridor = {
        "start": to_latlon(low),
        "end": to_latlon(high),
        "length_m": round(length, 1),
        "width_m": CORRIDOR_WIDTH_M,
        "confidence": {**diagnostics, "reason": reason},
    }
    return corridor, radius, corridor["confidence"]


def velocity_for(reports: list[dict[str, Any]], last_reported: datetime) -> dict[str, Any]:
    buckets: list[int] = []
    for offset in range(VELOCITY_BUCKETS, 0, -1):
        start, end = last_reported - timedelta(hours=offset), last_reported - timedelta(hours=offset - 1)
        # The final bucket includes the latest report itself.
        buckets.append(sum(1 for report in reports if start < _dt(report["created_at"]) <= end))
    half = VELOCITY_BUCKETS // 2
    prior, recent = sum(buckets[:half]), sum(buckets[half:])
    ratio = (recent + 1) / (prior + 1)
    if recent + prior < VELOCITY_MIN_WINDOW_REPORTS:
        label = "STEADY"
    elif ratio >= VELOCITY_RULES["rapid_ratio"] and recent >= VELOCITY_RULES["rapid_min_recent"]:
        label = "RAPIDLY ESCALATING"
    elif ratio >= VELOCITY_RULES["increasing_ratio"]:
        label = "INCREASING"
    elif ratio >= VELOCITY_RULES["steady_ratio"]:
        label = "STEADY"
    else:
        label = "DECLINING"
    return {"buckets": buckets, "recent": recent, "prior": prior, "ratio": round(ratio, 2), "label": label}


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def priority_for(active: list[dict[str, Any]], velocity: dict[str, Any], households: int, duration_hours: float, sensitive: Optional[dict[str, Any]], corridor_length: Optional[float]) -> tuple[int, int, bool, list[dict[str, Any]]]:
    unique_sources = len({item["source_handle"] for item in active})
    source_types = {item["source"] for item in active}
    corroborating = sorted(source_types & {"official", "field"})
    blocked = sum(1 for item in active if item["road_blocked"])
    health = sum(1 for item in active if item["health_risk"])
    values = {
        "Independent volume": min(1.0, math.log1p(unique_sources) / math.log1p(VOLUME_SATURATION_SOURCES)),
        "Source diversity": min(1.0, len(source_types) / SOURCE_TYPE_COUNT + (OFFICIAL_FIELD_DIVERSITY_BOOST if corroborating else 0.0)),
        "Duration unresolved": min(1.0, duration_hours / DURATION_SATURATION_HOURS),
        "Velocity": VELOCITY_VALUES[velocity["label"]],
        "Residential impact": min(1.0, households / HOUSEHOLD_SATURATION),
        "Road obstruction": 1.0 if blocked else 0.0,
        "Health risk": 1.0 if health else 0.0,
        "Sensitive location": 1.0 if sensitive else 0.0,
    }
    corroboration_text = f", including {' and '.join(corroborating)} reports" if corroborating else "; no official or field corroboration yet"
    extent = f" along a ~{corridor_length:.0f} m stretch" if corridor_length else ""
    sentences = {
        "Independent volume": f"{_plural(unique_sources, 'independent source')} reported this (duplicates counted once).",
        "Source diversity": f"Evidence spans {_plural(len(source_types), 'source type')}{corroboration_text}.",
        "Duration unresolved": f"Unresolved for about {round(duration_hours)} hours based on report times and stated durations.",
        "Velocity": (
            f"Report rate is {velocity['label'].lower()}: {velocity['recent']} reports in the latest 3 hours vs {velocity['prior']} in the 3 hours before."
            if velocity["recent"] + velocity["prior"] >= VELOCITY_MIN_WINDOW_REPORTS
            else "Too few recent reports to establish a trend; treated as steady."
        ),
        "Residential impact": f"About {households} households estimated affected{extent} (est.).",
        "Road obstruction": f"{_plural(blocked, 'report')} say the road is blocked." if blocked else "No report mentions a blocked road.",
        "Health risk": f"{_plural(health, 'report')} raise health or contamination concerns." if health else "No report raises a health concern.",
        "Sensitive location": sensitive["sentence"] if sensitive else "No school, hospital, or market identified within 150 m.",
    }
    factors = [
        {"name": name, "value": round(value, 3), "weight": PRIORITY_WEIGHTS[name], "contribution": round(PRIORITY_WEIGHTS[name] * value * 100, 1), "sentence": sentences[name]}
        for name, value in values.items()
    ]
    factors.sort(key=lambda factor: -factor["contribution"])
    base = min(100, round(sum(factor["contribution"] for factor in factors)))
    floor = bool(sensitive) and any(int(item["severity"]) >= SEVERITY_FLOOR_MIN_SEVERITY for item in active) and base < SEVERITY_FLOOR_PRIORITY
    return (SEVERITY_FLOOR_PRIORITY if floor else base), base, floor, factors


def confidence_for(active: list[dict[str, Any]]) -> tuple[float, list[str]]:
    unique_sources = len({item["source_handle"] for item in active})
    source_types = {item["source"] for item in active}
    geo_mean = statistics.mean(GEO_QUALITY_SCORES.get(item["geo_quality"], 0.0) for item in active) if active else 0.0
    corroborated = bool(source_types & {"official", "field"})
    value = (
        CONFIDENCE_WEIGHTS["diversity"] * min(1.0, len(source_types) / SOURCE_TYPE_COUNT)
        + CONFIDENCE_WEIGHTS["sources"] * min(1.0, unique_sources / CONFIDENCE_SOURCE_SATURATION)
        + CONFIDENCE_WEIGHTS["geo"] * geo_mean
        + CONFIDENCE_WEIGHTS["corroboration"] * (1.0 if corroborated else 0.0)
    )
    reasons: list[str] = []
    if "field" in source_types:
        reasons.append("Corroborated by field officer")
    elif "official" in source_types:
        reasons.append("Corroborated by official portal record")
    else:
        reasons.append("No official or field corroboration yet")
    approximate = sum(1 for item in active if item["geo_quality"] in ("locality", "none"))
    if approximate:
        reasons.append(f"Location approximate for {round(100 * approximate / len(active))}% of reports")
    else:
        reasons.append("All reports located to a road or landmark")
    if unique_sources == 1 and len(active) > 1:
        reasons.append("All reports come from a single handle")
    elif unique_sources < 4:
        reasons.append(f"Only {_plural(unique_sources, 'independent source')}")
    else:
        reasons.append(f"{unique_sources} independent sources across {_plural(len(source_types), 'source type')}")
    return round(value, 2), reasons


def _title(category: str, road: Optional[str], locality: Optional[str]) -> str:
    label = category.replace("_", " ").capitalize()
    location = ", ".join(value for value in (road, locality) if value)
    return f"{label} — {location}" if location else label


# ---------------------------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------------------------
def _reports_for(conn: sqlite3.Connection, where: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    return rows_to_dicts(conn.execute(f"SELECT {PIPELINE_REPORT_SELECT} FROM reports WHERE {where}", params).fetchall())


def _next_incident_id(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT MAX(CAST(SUBSTR(id, 5) AS INTEGER)) FROM incidents").fetchone()
    return f"HYD-{(row[0] or 100) + 1:03d}"


def recompute_incident(conn: sqlite3.Connection, incident_id: str) -> None:
    reports = sorted(_reports_for(conn, "incident_id = ?", (incident_id,)), key=lambda item: item["created_at"])
    if not reports:
        return
    active = [item for item in reports if not item["is_duplicate"]] or reports
    located = [item for item in active if item["lat"] is not None]
    precise = [(item["lat"], item["lon"]) for item in located if item["geo_quality"] in ("exact", "road")]
    all_points = [(item["lat"], item["lon"]) for item in located]
    corridor, radius, _ = corridor_for(precise if len(precise) >= CORRIDOR_MIN_POINTS else all_points)
    centroid_points = precise or all_points
    centroid_lat = round(statistics.mean(point[0] for point in centroid_points), 6) if centroid_points else None
    centroid_lon = round(statistics.mean(point[1] for point in centroid_points), 6) if centroid_points else None

    first, last = _dt(active[0]["created_at"]), _dt(active[-1]["created_at"])
    stated = [float(item["duration_hours"]) + (last - _dt(item["created_at"])).total_seconds() / 3600 for item in active if item["duration_hours"]]
    duration = max([(last - first).total_seconds() / 3600, *stated]) if stated else (last - first).total_seconds() / 3600
    unique_sources = len({item["source_handle"] for item in active})
    claimed = [int(item["households"]) for item in active if item["households"]]
    uncapped = max(statistics.median(claimed) if claimed else 0, unique_sources * HOUSEHOLDS_PER_SOURCE)
    households = max(1, round(min(uncapped, corridor["length_m"] / HOUSEHOLD_FRONTAGE_M) if corridor else uncapped))
    velocity = velocity_for(active, last)

    sensitive = None
    if centroid_lat is not None:
        nearby = nearest_sensitive(centroid_lat, centroid_lon, SENSITIVE_RADIUS_M)
        if nearby:
            landmark, distance = nearby
            sensitive = {"place": landmark.name, "sentence": f"{landmark.name} ({landmark.kind}) is ~{distance:.0f} m from the incident (gazetteer)."}
    if sensitive is None:
        mentions = [item["near_sensitive"] for item in active if item["near_sensitive"] and item["geo_quality"] != "none"]
        if mentions:
            kind = _mode(mentions)
            sensitive = {"place": f"Reported nearby {kind}", "sentence": f"{_plural(len(mentions), 'report')} mention a nearby {kind} (not confirmed in gazetteer)."}

    priority, base, floor, factors = priority_for(active, velocity, households, duration, sensitive, corridor["length_m"] if corridor else None)
    confidence, reasons = confidence_for(active)
    category = _mode((item["category"] for item in active), "other")
    locality = _mode(item["locality"] for item in active)
    road = _mode(item["road"] for item in active if item["locality"] == locality)
    conn.execute(
        """UPDATE incidents SET category=?, locality=?, road=?, title=?, centroid_lat=?, centroid_lon=?, corridor_json=?, radius_m=?,
               first_reported=?, last_reported=?, report_count=?, unique_sources=?, duplicate_count=?, source_mix_json=?, est_households=?,
               road_blocked=?, health_risk=?, sensitive_place=?, duration_hours=?, velocity_json=?, velocity_label=?, priority=?, base_priority=?,
               severity_floor_applied=?, priority_factors_json=?, confidence=?, confidence_reasons_json=? WHERE id=?""",
        (
            category, locality, road, _title(category, road, locality), centroid_lat, centroid_lon, dump_json(corridor) if corridor else None, radius,
            reports[0]["created_at"], reports[-1]["created_at"], len(reports), unique_sources, len(reports) - len(active) if len(active) < len(reports) else 0,
            dump_json(dict(sorted(Counter(item["source"] for item in active).items()))), households,
            int(any(item["road_blocked"] for item in active)), int(any(item["health_risk"] for item in active)), sensitive["place"] if sensitive else None,
            round(duration, 1), dump_json(velocity), velocity["label"], priority, base, int(floor), dump_json(factors), confidence, dump_json(reasons), incident_id,
        ),
    )


def _cluster_score(model: TfidfModel, report: dict[str, Any], incident: dict[str, Any], members: list[dict[str, Any]]) -> tuple[float, dict[str, float]]:
    similarities = sorted((model.similarity(report["raw_text"], item["raw_text"]) for item in members if not item["is_duplicate"]), reverse=True)[:CLUSTER_TOP_K_SEMANTIC]
    semantic = sum(similarities) / len(similarities) if similarities else 0.0
    if report["lat"] is None or incident["centroid_lat"] is None:
        geographic = 0.0
    else:
        # Distance to the incident footprint: its centroid or nearest precisely located member,
        # so reports at either end of a linear corridor are not penalised.
        precise = [(item["lat"], item["lon"]) for item in members if not item["is_duplicate"] and item["geo_quality"] in ("exact", "road") and item["lat"] is not None]
        footprint = [(incident["centroid_lat"], incident["centroid_lon"]), *precise]
        distance = min(haversine_m(report["lat"], report["lon"], lat, lon) for lat, lon in footprint)
        scale = GEO_SCALE_M
        # Either side known only to locality level: allow for that positional uncertainty.
        if report["geo_quality"] == "locality" or not precise:
            distance, scale = max(0.0, distance - LOCALITY_UNCERTAINTY_M), GEO_SCALE_LOCALITY_M
        geographic = math.exp(-distance / scale) * (GEO_ROAD_FACTOR if report["geo_quality"] == "road" else 1.0)
    hours = max(0.0, (_dt(report["created_at"]) - _dt(incident["last_reported"])).total_seconds() / 3600)
    details = {
        "semantic": round(semantic, 3),
        "geographic": round(geographic, 3),
        "temporal": round(math.exp(-hours / TIME_SCALE_HOURS), 3),
        "category": round(category_score(report["category"], incident["category"]), 3),
    }
    return round(sum(CLUSTER_WEIGHTS[name] * details[name] for name in details), 3), details


# ---------------------------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------------------------
def process_reports(conn: sqlite3.Connection, incoming: list[IncomingReport], batch_id: Optional[str] = None, provider: Optional[StructuredExtractionProvider] | bool = True) -> dict[str, Any]:
    """Run reports through extraction, duplicate detection, clustering and recomputation.
    Commits once at the end. Returns metrics and real per-stage server timings."""
    timings = {"received": 0.0, "classifying": 0.0, "extracting": 0.0, "duplicates": 0.0, "clustering": 0.0, "priority": 0.0}
    started = time.perf_counter()
    active_filter = "status IN ('open','verified','dispatched')"
    before = conn.execute(f"SELECT COUNT(*) FROM incidents WHERE {active_filter}").fetchone()[0]
    ordered = sorted(incoming, key=lambda item: (item.created_at, item.id))

    # 1. Receive: persist raw signals.
    tick = time.perf_counter()
    columns = PIPELINE_REPORT_COLUMNS
    for report in ordered:
        row = {column: None for column in columns}
        row.update({"id": report.id, "source": report.source, "source_handle": report.source_handle, "raw_text": report.raw_text, "created_at": report.created_at,
                    "gps_lat": report.gps_lat, "gps_lon": report.gps_lon, "geo_quality": "none", "severity": 1, "road_blocked": 0, "health_risk": 0,
                    "in_scope": 1, "is_duplicate": 0, "batch_id": batch_id})
        conn.execute(f"INSERT INTO reports ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", [row[column] for column in columns])
    timings["received"] += time.perf_counter() - tick

    # 2-3. Classify and extract (hybrid or rules fallback).
    extractions, stats = extract_many(ordered, provider)
    timings["classifying"] += stats.rules_seconds
    timings["extracting"] += stats.resolve_seconds
    tick = time.perf_counter()
    for report in ordered:
        result = extractions[report.id]
        conn.execute(
            """UPDATE reports SET category=?, road=?, landmark=?, locality=?, lat=?, lon=?, geo_quality=?, duration_hours=?, severity=?, households=?,
                   road_blocked=?, health_risk=?, near_sensitive=?, in_scope=?, extraction_details_json=? WHERE id=?""",
            (result.category or "other", result.road, result.landmark, result.locality, result.lat, result.lon, result.geo_quality, result.duration_hours,
             result.severity, result.households, int(result.road_blocked), int(result.health_risk), result.near_sensitive, int(result.in_scope), details_json(result), report.id),
        )
    timings["extracting"] += time.perf_counter() - tick

    corpus = [row[0] for row in conn.execute("SELECT raw_text FROM reports WHERE in_scope = 1").fetchall()]
    model = TfidfModel(corpus)
    out_of_scope = duplicates = located = unlocated = 0
    new_ids: list[str] = []
    touched: set[str] = set()

    for report in ordered:
        row = _reports_for(conn, "id = ?", (report.id,))[0]
        if not row["in_scope"]:
            out_of_scope += 1
            continue
        if row["lat"] is not None:
            located += 1

        # 4. Duplicates: same handle, near-identical text, same incident candidate.
        tick = time.perf_counter()
        prior = _reports_for(conn, "source_handle = ? AND id != ? AND in_scope = 1 AND created_at <= ?", (row["source_handle"], row["id"], row["created_at"]))
        original = None
        for candidate in sorted(prior, key=lambda item: item["created_at"]):
            if row["lat"] is not None and candidate["lat"] is not None and haversine_m(row["lat"], row["lon"], candidate["lat"], candidate["lon"]) > CLUSTER_RADIUS_M:
                continue
            if model.similarity(row["raw_text"], candidate["raw_text"]) > DUPLICATE_SIMILARITY_THRESHOLD:
                original = candidate
                break
        timings["duplicates"] += time.perf_counter() - tick
        if original is not None:
            root_id = original["duplicate_of"] or original["id"]
            conn.execute("UPDATE reports SET is_duplicate=1, duplicate_of=?, incident_id=? WHERE id=?", (root_id, original["incident_id"], row["id"]))
            if original["incident_id"]:
                touched.add(original["incident_id"])
                tick = time.perf_counter()
                recompute_incident(conn, original["incident_id"])
                timings["priority"] += time.perf_counter() - tick
            duplicates += 1
            continue

        # 5. Online clustering against active incidents.
        tick = time.perf_counter()
        best: tuple[Optional[dict[str, Any]], float, Optional[dict[str, float]]] = (None, 0.0, None)
        for incident in rows_to_dicts(conn.execute(f"SELECT id, category, centroid_lat, centroid_lon, last_reported FROM incidents WHERE {active_filter}").fetchall()):
            if row["lat"] is not None:
                if incident["centroid_lat"] is None or haversine_m(row["lat"], row["lon"], incident["centroid_lat"], incident["centroid_lon"]) > CLUSTER_RADIUS_M:
                    continue
            members = _reports_for(conn, "incident_id = ?", (incident["id"],))
            score, details = _cluster_score(model, row, incident, members)
            if row["geo_quality"] == "none" and not (details["semantic"] > UNLOCATED_SEMANTIC_THRESHOLD and details["category"] == 1.0):
                continue
            if score > best[1]:
                best = (incident, score, details)
        incident, score, details = best
        if incident is not None and (score >= CLUSTER_THRESHOLD or row["geo_quality"] == "none"):
            incident_id = incident["id"]
            conn.execute("UPDATE reports SET incident_id=?, cluster_score=?, cluster_details_json=? WHERE id=?", (incident_id, score, dump_json(details), row["id"]))
        elif row["geo_quality"] == "none":
            unlocated += 1
            timings["clustering"] += time.perf_counter() - tick
            continue
        else:
            incident_id = _next_incident_id(conn)
            conn.execute(
                """INSERT INTO incidents (id, category, locality, road, title, first_reported, last_reported, report_count, unique_sources, source_mix_json,
                       est_households, road_blocked, health_risk, velocity_json, priority, priority_factors_json, confidence, confidence_reasons_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, '{}', 0, 0, 0, '{}', 0, '[]', 0, '[]', ?)""",
                (incident_id, row["category"], row["locality"], row["road"], _title(row["category"], row["road"], row["locality"]), row["created_at"], row["created_at"], row["created_at"]),
            )
            conn.execute("UPDATE reports SET incident_id=?, cluster_score=NULL, cluster_details_json=? WHERE id=?", (incident_id, dump_json({"founding": 1.0}), row["id"]))
            new_ids.append(incident_id)
        touched.add(incident_id)
        timings["clustering"] += time.perf_counter() - tick

        # 6. Recompute the affected aggregate from its members.
        tick = time.perf_counter()
        recompute_incident(conn, incident_id)
        timings["priority"] += time.perf_counter() - tick

    conn.commit()
    after = conn.execute(f"SELECT COUNT(*) FROM incidents WHERE {active_filter}").fetchone()[0]
    in_scope = len(ordered) - out_of_scope
    stage_ms = {name: max(1, round(value * 1000)) for name, value in timings.items()}
    new_set = set(new_ids)
    return {
        "received": len(ordered),
        "out_of_scope": out_of_scope,
        "duplicates": duplicates,
        "located": located,
        "unlocated": unlocated,
        "incidents_before": before,
        "incidents_after": after,
        "batch_incident_count": len(touched),
        "new_incident_ids": new_ids,
        "updated_incident_ids": sorted(touched - new_set),
        "stages": [
            {"name": "Reports received", "count": len(ordered), "ms": stage_ms["received"]},
            {"name": "Classifying", "count": in_scope, "ms": stage_ms["classifying"]},
            {"name": "Extracting locations", "count": located, "ms": stage_ms["extracting"]},
            {"name": "Finding duplicates", "count": duplicates, "ms": stage_ms["duplicates"]},
            {"name": "Clustering incidents", "count": len(touched), "ms": stage_ms["clustering"]},
            {"name": "Calculating priority", "count": len(touched), "ms": stage_ms["priority"]},
        ],
        "extraction_mode": stats.mode,
        "extraction_fallback_reasons": stats.reasons,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
    }


def hydrate_incident(record: dict[str, Any]) -> dict[str, Any]:
    item = dict(record)
    for column, default in (("corridor_json", None), ("source_mix_json", {}), ("velocity_json", {}), ("priority_factors_json", []), ("confidence_reasons_json", [])):
        item[column.removesuffix("_json")] = load_json(item.pop(column), default)
    item["road_blocked"], item["health_risk"] = bool(item["road_blocked"]), bool(item["health_risk"])
    item["severity_floor_applied"] = bool(item.get("severity_floor_applied"))
    item["band"] = band_for(item["priority"])
    item["confidence_label"] = confidence_label(item["confidence"])
    item["velocity_label"] = item.get("velocity_label") or item["velocity"].get("label", "STEADY")
    return item
