"""SQLite storage. Coordinates and JSON blobs are shaped for a later PostGIS migration."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .config import DATABASE_PATH, ensure_data_directories

REPORT_COLUMNS = (
    "id", "source", "source_handle", "raw_text", "created_at", "gps_lat", "gps_lon",
    "category", "road", "landmark", "locality", "lat", "lon", "geo_quality",
    "duration_hours", "severity", "households", "road_blocked", "health_risk", "near_sensitive", "in_scope",
    "is_duplicate", "duplicate_of", "incident_id", "batch_id", "truth_incident",
    "cluster_score", "cluster_details_json", "extraction_details_json",
)
# The pipeline reads and writes only these columns; hidden ground truth is excluded.
PIPELINE_REPORT_COLUMNS = tuple(column for column in REPORT_COLUMNS if column != "truth_incident")
PIPELINE_REPORT_SELECT = ", ".join(PIPELINE_REPORT_COLUMNS)

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_handle TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    gps_lat REAL,
    gps_lon REAL,
    category TEXT,
    road TEXT,
    landmark TEXT,
    locality TEXT,
    lat REAL,
    lon REAL,
    geo_quality TEXT NOT NULL DEFAULT 'none',
    duration_hours REAL,
    severity INTEGER NOT NULL DEFAULT 1,
    households INTEGER,
    road_blocked INTEGER NOT NULL DEFAULT 0,
    health_risk INTEGER NOT NULL DEFAULT 0,
    near_sensitive TEXT,
    in_scope INTEGER NOT NULL DEFAULT 1,
    is_duplicate INTEGER NOT NULL DEFAULT 0,
    duplicate_of TEXT,
    incident_id TEXT,
    batch_id TEXT,
    truth_incident TEXT,
    cluster_score REAL,
    cluster_details_json TEXT,
    extraction_details_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_reports_incident ON reports(incident_id);
CREATE INDEX IF NOT EXISTS idx_reports_created ON reports(created_at);
CREATE INDEX IF NOT EXISTS idx_reports_batch ON reports(batch_id);
CREATE INDEX IF NOT EXISTS idx_reports_handle ON reports(source_handle);

CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    locality TEXT,
    road TEXT,
    title TEXT NOT NULL,
    centroid_lat REAL,
    centroid_lon REAL,
    corridor_json TEXT,
    radius_m REAL NOT NULL DEFAULT 0,
    first_reported TEXT NOT NULL,
    last_reported TEXT NOT NULL,
    report_count INTEGER NOT NULL,
    unique_sources INTEGER NOT NULL,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    source_mix_json TEXT NOT NULL,
    est_households INTEGER NOT NULL,
    road_blocked INTEGER NOT NULL,
    health_risk INTEGER NOT NULL,
    sensitive_place TEXT,
    duration_hours REAL NOT NULL DEFAULT 0,
    velocity_json TEXT NOT NULL,
    velocity_label TEXT NOT NULL DEFAULT 'STEADY',
    priority INTEGER NOT NULL,
    base_priority INTEGER NOT NULL DEFAULT 0,
    severity_floor_applied INTEGER NOT NULL DEFAULT 0,
    priority_factors_json TEXT NOT NULL,
    confidence REAL NOT NULL,
    confidence_reasons_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_incidents_priority ON incidents(priority DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);

-- Provenance for reports ingested from external sources (Tavily, Apify). Demo reports have no row.
CREATE TABLE IF NOT EXISTS report_provenance (
    report_id TEXT PRIMARY KEY,
    origin TEXT NOT NULL,
    url TEXT,
    title TEXT,
    original_content TEXT,
    queries_json TEXT,
    published_at TEXT,
    ingested_at TEXT NOT NULL,
    metadata_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_provenance_origin ON report_provenance(origin);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect(path: Path | str = DATABASE_PATH) -> sqlite3.Connection:
    if str(path) != ":memory:":
        ensure_data_directories()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def recreate(conn: sqlite3.Connection) -> None:
    """Explicit, idempotent rebuild of the demo schema."""
    conn.executescript("DROP TABLE IF EXISTS reports; DROP TABLE IF EXISTS incidents; DROP TABLE IF EXISTS meta; DROP TABLE IF EXISTS report_provenance;")
    initialize(conn)


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def load_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


def dump_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
