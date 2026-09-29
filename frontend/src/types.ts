// Mirrors backend/app/schemas.py. Components must not define competing API shapes.

export type Band = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
export type Status = 'open' | 'verified' | 'dispatched' | 'resolved';
export type VelocityLabel = 'RAPIDLY ESCALATING' | 'INCREASING' | 'STEADY' | 'DECLINING';
export type ConfidenceLabel = 'HIGH' | 'MEDIUM' | 'LOW';
export type GeoQuality = 'exact' | 'road' | 'locality' | 'none';
export type Source = 'phone' | 'social' | 'whatsapp' | 'news' | 'official' | 'field';

export interface Summary {
  reports_today: number;
  active_incidents: number;
  critical: number;
  escalating: number;
  resolved: number;
  unlocated: number;
}

export interface CompactIncident {
  id: string;
  category: string;
  locality: string | null;
  road: string | null;
  title: string;
  centroid_lat: number | null;
  centroid_lon: number | null;
  priority: number;
  band: Band;
  report_count: number;
  unique_sources: number;
  velocity_label: VelocityLabel;
  confidence_label: ConfidenceLabel;
  status: Status;
  first_reported: string;
  last_reported: string;
}

export interface PriorityFactor {
  name: string;
  value: number;
  weight: number;
  contribution: number;
  sentence: string;
}

export interface Velocity {
  buckets: number[];
  recent: number;
  prior: number;
  ratio: number;
  label: VelocityLabel;
}

export interface Corridor {
  start: [number, number];
  end: [number, number];
  length_m: number;
  width_m: number;
  confidence: { points: number; spread_m: number; eigenvalue_ratio: number; reason: string };
}

export interface FullIncident extends CompactIncident {
  corridor: Corridor | null;
  radius_m: number;
  source_mix: Partial<Record<Source, number>>;
  velocity: Velocity;
  priority_factors: PriorityFactor[];
  severity_floor_applied: boolean;
  base_priority: number;
  confidence: number;
  confidence_reasons: string[];
  est_households: number;
  road_blocked: boolean;
  health_risk: boolean;
  sensitive_place: string | null;
  duration_hours: number;
  duplicate_count: number;
  created_at: string;
}

export interface ClusterSummary {
  semantic: number;
  geographic: number;
  temporal: number;
  category: number;
  score: number;
  threshold: number;
  reports_scored: number;
  reasons: string[];
}

export interface EvidenceReport {
  id: string;
  source: Source;
  source_handle: string;
  created_at: string;
  raw_text: string;
  geo_quality: GeoQuality;
  locality: string | null;
  road: string | null;
  landmark: string | null;
  is_duplicate: boolean;
  duplicate_of: string | null;
  cluster_score: number | null;
  cluster_details: Record<'semantic' | 'geographic' | 'temporal' | 'category', number> | null;
  extraction_mode: string | null;
}

export interface EvidenceResponse {
  incident_id: string;
  priority: number;
  base_priority: number;
  severity_floor_applied: boolean;
  factors: PriorityFactor[];
  cluster_summary: ClusterSummary;
  representative_reports: EvidenceReport[];
  total_reports: number;
  duplicate_count: number;
  extraction: { hybrid_validated: number; rules_fallback: number; label: string; location_confidence: number };
}

/** [lat, lon, weight 0..1] */
export type HeatmapPoint = [number, number, number];

export interface SimulationStage {
  name: string;
  count: number;
  ms: number;
}

export interface SimulateResponse {
  batch_id: string;
  received: number;
  out_of_scope: number;
  duplicates: number;
  located: number;
  unlocated: number;
  incidents_before: number;
  incidents_after: number;
  batch_incident_count: number;
  new_incident_ids: string[];
  updated_incident_ids: string[];
  stages: SimulationStage[];
  hero_incident_id: string | null;
  extraction_mode: string;
  elapsed_ms: number;
}

export interface BriefResponse {
  facts: string[];
  assessment: string[];
  recommended_next_step: string;
  generated_by: 'template' | 'llm';
}

export interface StatusResponse {
  id: string;
  status: Status;
}

export interface ResetResponse {
  summary: Summary;
  default_incident_id: string | null;
}

export interface HealthResponse {
  status: 'ok';
  extraction_mode: string;
  llm_configured: boolean;
}
