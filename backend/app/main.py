"""FastAPI routes. Numerical logic lives in pipeline.py; this module only orchestrates and shapes."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import config, db, service
from .brief import BriefNotFound, generate_brief
from .db import load_json, rows_to_dicts
from .extraction_providers import get_provider
from .pipeline import hydrate_incident
from .schemas import (
    BriefResponse,
    CompactIncident,
    EvidenceResponse,
    FullIncident,
    HealthResponse,
    ResetResponse,
    SimulateResponse,
    StatusResponse,
    StatusUpdate,
    SummaryResponse,
)

# SQLite allows one writer; simulate/reset/status share this lock so requests never interleave.
_write_lock = threading.Lock()


def database_path() -> str:
    return str(config.DATABASE_PATH)


@asynccontextmanager
async def lifespan(_: FastAPI):
    conn = db.connect(database_path())
    try:
        with _write_lock:
            service.ensure_seeded(conn)
    finally:
        conn.close()
    yield


app = FastAPI(title="SewerSense API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


def get_conn() -> Iterator[sqlite3.Connection]:
    conn = db.connect(database_path())
    try:
        yield conn
    finally:
        conn.close()


def _incident_row(conn: sqlite3.Connection, incident_id: str) -> dict:
    row = conn.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return dict(row)


def _summary(conn: sqlite3.Connection) -> SummaryResponse:
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    active = "status IN ('open','verified','dispatched')"
    one = lambda sql, *params: conn.execute(sql, params).fetchone()[0]  # noqa: E731
    return SummaryResponse(
        reports_today=one("SELECT COUNT(*) FROM reports WHERE created_at >= ?", since),
        active_incidents=one(f"SELECT COUNT(*) FROM incidents WHERE {active}"),
        critical=one(f"SELECT COUNT(*) FROM incidents WHERE {active} AND priority >= 80"),
        escalating=one(f"SELECT COUNT(*) FROM incidents WHERE {active} AND velocity_label IN ('RAPIDLY ESCALATING','INCREASING')"),
        resolved=one("SELECT COUNT(*) FROM incidents WHERE status = 'resolved'"),
        unlocated=one("SELECT COUNT(*) FROM reports WHERE in_scope = 1 AND is_duplicate = 0 AND incident_id IS NULL"),
    )


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    provider = get_provider()
    return HealthResponse(status="ok", extraction_mode="hybrid" if provider and provider.available() else "rules_fallback", llm_configured=bool(provider and provider.available()))


@app.get("/api/summary", response_model=SummaryResponse)
def summary(conn: sqlite3.Connection = Depends(get_conn)) -> SummaryResponse:
    return _summary(conn)


@app.get("/api/incidents", response_model=list[CompactIncident])
def list_incidents(
    status: Optional[Literal["open", "verified", "dispatched", "resolved", "active"]] = Query(default=None),
    min_priority: Optional[int] = Query(default=None, ge=0, le=100),
    conn: sqlite3.Connection = Depends(get_conn),
) -> list[dict]:
    clauses, params = [], []
    if status == "active":
        clauses.append("status IN ('open','verified','dispatched')")
    elif status:
        clauses.append("status = ?")
        params.append(status)
    if min_priority is not None:
        clauses.append("priority >= ?")
        params.append(min_priority)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(f"SELECT * FROM incidents {where} ORDER BY priority DESC, last_reported DESC", params).fetchall()
    return [hydrate_incident(dict(row)) for row in rows]


@app.get("/api/incidents/{incident_id}", response_model=FullIncident)
def get_incident(incident_id: str, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return hydrate_incident(_incident_row(conn, incident_id))


@app.get("/api/incidents/{incident_id}/evidence", response_model=EvidenceResponse)
def get_evidence(incident_id: str, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    incident = hydrate_incident(_incident_row(conn, incident_id))
    reports = rows_to_dicts(conn.execute(
        """SELECT id, source, source_handle, created_at, raw_text, geo_quality, locality, road, landmark, is_duplicate, duplicate_of,
                  cluster_score, cluster_details_json, extraction_details_json
           FROM reports WHERE incident_id = ? ORDER BY created_at""",
        (incident_id,),
    ).fetchall())
    for report in reports:
        report["cluster_details"] = load_json(report.pop("cluster_details_json"), None)
        report["extraction"] = load_json(report.pop("extraction_details_json"), {})
        report["is_duplicate"] = bool(report["is_duplicate"])

    scored = [item for item in reports if not item["is_duplicate"] and item["cluster_score"] is not None and item["cluster_details"] and "semantic" in item["cluster_details"]]
    averages = {name: round(sum(item["cluster_details"][name] for item in scored) / len(scored), 3) if scored else 0.0 for name in ("semantic", "geographic", "temporal", "category")}
    score = round(sum(item["cluster_score"] for item in scored) / len(scored), 3) if scored else 0.0
    if scored:
        describe = lambda value: "strongly" if value >= 0.75 else "moderately" if value >= 0.4 else "weakly"  # noqa: E731
        reasons = [
            f"{len(scored)} reports were attached to this incident after it was first reported; each scored at least {config.CLUSTER_THRESHOLD:.2f} (average {score:.2f}).",
            f"Content: {describe(averages['semantic'])} similar wording to the incident's closest reports (TF-IDF {averages['semantic']:.2f}).",
            f"Proximity: {describe(averages['geographic'])} close to the incident footprint ({averages['geographic']:.2f}).",
            f"Recency: arrived {describe(averages['temporal'])} close in time to the previous report ({averages['temporal']:.2f}).",
            f"Category: {'same' if averages['category'] >= 0.95 else 'same or compatible'} problem type ({averages['category']:.2f}).",
        ]
    else:
        reasons = ["Single founding report so far; no grouping decisions to explain yet."]
    duplicates = [item for item in reports if item["is_duplicate"]]
    active = [item for item in reports if not item["is_duplicate"]]
    founding = [item for item in active if item["cluster_score"] is None]
    top_scored = sorted(scored, key=lambda item: -item["cluster_score"])
    representative: list[dict] = []
    for item in founding[:1] + top_scored[:3] + sorted(active, key=lambda item: item["created_at"], reverse=True)[:3] + duplicates[:2]:
        if item["id"] not in {chosen["id"] for chosen in representative}:
            representative.append(item)
    hybrid = sum(1 for item in active if item["extraction"].get("mode") == "hybrid_validated")
    location_confidence = round(sum(item["extraction"].get("candidate_confidence", 0.0) for item in active) / len(active), 2) if active else 0.0
    return {
        "incident_id": incident_id,
        "priority": incident["priority"],
        "base_priority": incident["base_priority"],
        "severity_floor_applied": incident["severity_floor_applied"],
        "factors": incident["priority_factors"],
        "cluster_summary": {**averages, "score": score, "threshold": config.CLUSTER_THRESHOLD, "reports_scored": len(scored), "reasons": reasons},
        "representative_reports": [
            {**{key: item[key] for key in ("id", "source", "source_handle", "created_at", "raw_text", "geo_quality", "locality", "road", "landmark", "is_duplicate", "duplicate_of", "cluster_score")},
             "cluster_details": item["cluster_details"] if item["cluster_details"] and "semantic" in item["cluster_details"] else None,
             "extraction_mode": item["extraction"].get("mode")}
            for item in representative
        ],
        "total_reports": len(reports),
        "duplicate_count": len(duplicates),
        "extraction": {
            "hybrid_validated": hybrid,
            "rules_fallback": len(active) - hybrid,
            "label": "Hybrid extraction validated" if hybrid == len(active) and active else "Partly hybrid-validated" if hybrid else "Rules fallback",
            "location_confidence": location_confidence,
        },
    }


@app.get("/api/heatmap", response_model=list[list[float]])
def heatmap(conn: sqlite3.Connection = Depends(get_conn)) -> list[list[float]]:
    rows = conn.execute(
        """SELECT r.lat, r.lon, i.priority FROM reports r JOIN incidents i ON i.id = r.incident_id
           WHERE r.lat IS NOT NULL AND r.is_duplicate = 0 AND i.status != 'resolved'"""
    ).fetchall()
    return [[round(lat, 6), round(lon, 6), round(max(0.05, priority / 100), 2)] for lat, lon, priority in rows]


@app.post("/api/simulate", response_model=SimulateResponse)
def simulate(conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    if not _write_lock.acquire(timeout=30):
        raise HTTPException(status_code=409, detail="Another simulation or reset is in progress")
    try:
        return service.simulate(conn)
    finally:
        _write_lock.release()


@app.post("/api/incidents/{incident_id}/brief", response_model=BriefResponse)
def brief(incident_id: str, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    try:
        return generate_brief(conn, incident_id)
    except BriefNotFound:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found") from None


@app.post("/api/incidents/{incident_id}/status", response_model=StatusResponse)
def update_status(incident_id: str, update: StatusUpdate, conn: sqlite3.Connection = Depends(get_conn)) -> StatusResponse:
    with _write_lock:
        _incident_row(conn, incident_id)
        conn.execute("UPDATE incidents SET status = ? WHERE id = ?", (update.status, incident_id))
        conn.commit()
    return StatusResponse(id=incident_id, status=update.status)


@app.post("/api/reset", response_model=ResetResponse)
def reset(conn: sqlite3.Connection = Depends(get_conn)) -> ResetResponse:
    if not _write_lock.acquire(timeout=30):
        raise HTTPException(status_code=409, detail="Another simulation or reset is in progress")
    try:
        service.seed_baseline(conn)
    finally:
        _write_lock.release()
    top = conn.execute("SELECT id FROM incidents WHERE status != 'resolved' ORDER BY priority DESC, last_reported DESC LIMIT 1").fetchone()
    return ResetResponse(summary=_summary(conn), default_incident_id=top[0] if top else None)
