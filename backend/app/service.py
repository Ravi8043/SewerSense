"""Orchestration shared by seed.py, the API, and tests.

This module is the only place that stores generator ground truth, and it does so strictly after
the pipeline has finished with a batch, for post-hoc evaluation only.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from .db import get_meta, initialize, recreate, set_meta
from .extraction_providers import StructuredExtractionProvider
from .generator import GeneratedReport, generate_baseline, generate_batch, utc_now
from .pipeline import process_reports

# Deterministic demo status mix applied to the baseline by priority rank (rank -> status).
BASELINE_STATUS_PLAN = {1: "verified", 3: "dispatched", 6: "verified", 9: "dispatched"}
BASELINE_RESOLVED_EVERY = 5  # every 5th incident from rank 12 on is resolved


def _record_truth(conn: sqlite3.Connection, generated: list[GeneratedReport]) -> None:
    conn.executemany("UPDATE reports SET truth_incident = ? WHERE id = ?", [(item.truth_incident, item.report.id) for item in generated])


def run_batch(conn: sqlite3.Connection, generated: list[GeneratedReport], batch_id: str, provider: Optional[StructuredExtractionProvider] | bool = True) -> dict[str, Any]:
    result = process_reports(conn, [item.report for item in generated], batch_id, provider)
    _record_truth(conn, generated)
    conn.commit()
    return result


def seed_baseline(conn: sqlite3.Connection, now: Optional[datetime] = None, provider: Optional[StructuredExtractionProvider] | bool = True) -> dict[str, Any]:
    """Recreate the database and rebuild the deterministic baseline through the real pipeline."""
    now = now or utc_now()
    recreate(conn)
    result = run_batch(conn, generate_baseline(now=now), batch_id="baseline", provider=provider)
    ranked = [row[0] for row in conn.execute("SELECT id FROM incidents ORDER BY priority DESC, id").fetchall()]
    for rank, incident_id in enumerate(ranked):
        status = BASELINE_STATUS_PLAN.get(rank)
        if status is None and rank >= 12 and rank % BASELINE_RESOLVED_EVERY == 0:
            status = "resolved"
        if status:
            conn.execute("UPDATE incidents SET status = ? WHERE id = ?", (status, incident_id))
    set_meta(conn, "seeded_at", now.isoformat())
    set_meta(conn, "simulation_count", "0")
    conn.commit()
    return result


def ensure_seeded(conn: sqlite3.Connection) -> bool:
    """Seed on first start; returns True when a seed was performed."""
    initialize(conn)
    if get_meta(conn, "seeded_at") is None or conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0] == 0:
        seed_baseline(conn)
        return True
    return False


def simulate(conn: sqlite3.Connection, now: Optional[datetime] = None, provider: Optional[StructuredExtractionProvider] | bool = True) -> dict[str, Any]:
    now = (now or utc_now()).astimezone(timezone.utc).replace(microsecond=0)
    count = int(get_meta(conn, "simulation_count") or 0) + 1
    batch_id = f"batch-{now.strftime('%Y-%m-%dT%H:%M:%SZ')}-{count}"
    generated = generate_batch(n=100, now=now, hero=True, seed=42 + count - 1)
    result = run_batch(conn, generated, batch_id, provider)
    set_meta(conn, "simulation_count", str(count))
    conn.commit()
    # The hero is identified from pipeline output (the highest-priority incident this batch touched),
    # never from ground truth.
    touched = result["new_incident_ids"] + result["updated_incident_ids"]
    hero = None
    if touched:
        placeholders = ",".join("?" for _ in touched)
        row = conn.execute(f"SELECT id FROM incidents WHERE id IN ({placeholders}) ORDER BY priority DESC, report_count DESC LIMIT 1", touched).fetchone()
        hero = row[0] if row else None
    return {**result, "batch_id": batch_id, "hero_incident_id": hero}
