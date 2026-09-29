"""Pydantic contracts: pipeline input, extraction output, and API payloads."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Category = Literal[
    "overflow",
    "blockage",
    "foul_smell",
    "manhole",
    "sewage_in_house",
    "damaged_pipeline",
    "drain_blockage",
    "road_flooding",
    "other",
]
Source = Literal["phone", "social", "whatsapp", "news", "official", "field"]
GeoQuality = Literal["exact", "road", "locality", "none"]
Status = Literal["open", "verified", "dispatched", "resolved"]
Band = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
VelocityLabel = Literal["RAPIDLY ESCALATING", "INCREASING", "STEADY", "DECLINING"]
Provenance = Literal["rule", "llm", "reconciled", "fallback"]


# ---------------------------------------------------------------------------------------------
# Pipeline input. Deliberately carries no ground-truth field.
# ---------------------------------------------------------------------------------------------
class IncomingReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    source: Source
    source_handle: str
    raw_text: str
    created_at: str
    # Optional device location pin (WhatsApp location share, field app, portal map pin).
    gps_lat: Optional[float] = None
    gps_lon: Optional[float] = None


# ---------------------------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------------------------
class RuleCandidates(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locality_candidates: list[str] = Field(default_factory=list)
    road_candidates: list[str] = Field(default_factory=list)
    landmark_candidates: list[str] = Field(default_factory=list)
    explicit_claims: dict[str, float | int | bool] = Field(default_factory=dict)
    category_cues: list[str] = Field(default_factory=list)
    excluded_topic_cues: list[str] = Field(default_factory=list)
    sensitive_cues: list[str] = Field(default_factory=list)


class LLMExtraction(BaseModel):
    """Exact JSON shape the structured LLM must return. Unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid")

    category: Optional[Category] = None
    category_confidence: float = Field(ge=0, le=1)
    locality: Optional[str] = None
    road: Optional[str] = None
    landmark: Optional[str] = None
    duration_hours: Optional[float] = Field(default=None, ge=0, le=24 * 30)
    households: Optional[int] = Field(default=None, ge=0, le=5000)
    road_blocked: bool
    health_risk: bool
    near_school_or_hospital: bool
    in_scope: bool
    severity: int = Field(ge=1, le=5)


class ExtractionResult(BaseModel):
    """Normalized, provider-independent extraction consumed by the pipeline."""

    model_config = ConfigDict(extra="forbid")

    category: Optional[Category]
    locality: Optional[str]
    road: Optional[str]
    landmark: Optional[str]
    lat: Optional[float]
    lon: Optional[float]
    geo_quality: GeoQuality
    duration_hours: Optional[float]
    severity: int = Field(ge=1, le=5)
    households: Optional[int]
    road_blocked: bool
    health_risk: bool
    near_sensitive: Optional[str]
    in_scope: bool
    candidate_confidence: float = Field(ge=0, le=1)
    field_provenance: dict[str, Provenance]
    reconciliation_notes: list[str]
    extraction_mode: Literal["hybrid_validated", "rules_fallback"]
    fallback_reason: Optional[str] = None
    provider: Optional[str]
    model: Optional[str]
    schema_version: str


# ---------------------------------------------------------------------------------------------
# API responses
# ---------------------------------------------------------------------------------------------
class SummaryResponse(BaseModel):
    reports_today: int
    active_incidents: int
    critical: int
    escalating: int
    resolved: int
    unlocated: int


class PriorityFactor(BaseModel):
    name: str
    value: float
    weight: float
    contribution: float
    sentence: str


class Velocity(BaseModel):
    buckets: list[int]
    recent: int
    prior: int
    ratio: float
    label: VelocityLabel


class CorridorConfidence(BaseModel):
    points: int
    spread_m: float
    eigenvalue_ratio: float
    reason: str


class Corridor(BaseModel):
    start: list[float]
    end: list[float]
    length_m: float
    width_m: float
    confidence: CorridorConfidence


class CompactIncident(BaseModel):
    id: str
    category: str
    locality: Optional[str]
    road: Optional[str]
    title: str
    centroid_lat: Optional[float]
    centroid_lon: Optional[float]
    priority: int
    band: Band
    report_count: int
    unique_sources: int
    velocity_label: VelocityLabel
    confidence_label: Literal["HIGH", "MEDIUM", "LOW"]
    status: Status
    first_reported: str
    last_reported: str


class FullIncident(CompactIncident):
    corridor: Optional[Corridor]
    radius_m: float
    source_mix: dict[str, int]
    velocity: Velocity
    priority_factors: list[PriorityFactor]
    severity_floor_applied: bool
    base_priority: int
    confidence: float
    confidence_reasons: list[str]
    est_households: int
    road_blocked: bool
    health_risk: bool
    sensitive_place: Optional[str]
    duration_hours: float
    duplicate_count: int
    created_at: str


class ClusterSummary(BaseModel):
    semantic: float
    geographic: float
    temporal: float
    category: float
    score: float
    threshold: float
    reports_scored: int
    reasons: list[str]


class EvidenceReport(BaseModel):
    id: str
    source: str
    source_handle: str
    created_at: str
    raw_text: str
    geo_quality: GeoQuality
    locality: Optional[str]
    road: Optional[str]
    landmark: Optional[str]
    is_duplicate: bool
    duplicate_of: Optional[str]
    cluster_score: Optional[float]
    cluster_details: Optional[dict[str, float]]
    extraction_mode: Optional[str]


class ExtractionSummary(BaseModel):
    hybrid_validated: int
    rules_fallback: int
    label: str
    location_confidence: float


class EvidenceResponse(BaseModel):
    incident_id: str
    priority: int
    base_priority: int
    severity_floor_applied: bool
    factors: list[PriorityFactor]
    cluster_summary: ClusterSummary
    representative_reports: list[EvidenceReport]
    total_reports: int
    duplicate_count: int
    extraction: ExtractionSummary


class SimulationStage(BaseModel):
    name: str
    count: int
    ms: int


class SimulateResponse(BaseModel):
    batch_id: str
    received: int
    out_of_scope: int
    duplicates: int
    located: int
    unlocated: int
    incidents_before: int
    incidents_after: int
    batch_incident_count: int
    new_incident_ids: list[str]
    updated_incident_ids: list[str]
    stages: list[SimulationStage]
    hero_incident_id: Optional[str]
    extraction_mode: str
    elapsed_ms: int


class BriefResponse(BaseModel):
    facts: list[str]
    assessment: list[str]
    recommended_next_step: str
    generated_by: Literal["template", "llm"]


class LLMBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facts: list[str] = Field(min_length=1, max_length=8)
    assessment: list[str] = Field(min_length=1, max_length=8)
    recommended_next_step: str


class StatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Status


class StatusResponse(BaseModel):
    id: str
    status: Status


class ResetResponse(BaseModel):
    summary: SummaryResponse
    default_incident_id: Optional[str]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    extraction_mode: str
    llm_configured: bool
