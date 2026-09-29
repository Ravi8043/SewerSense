"""Run external sources through the *existing* SewerSense pipeline.

Flow: adapters fetch -> shared normalize() -> drop exact repeats (same canonical URL/text, which
would otherwise collide on the report primary key) -> ONE process_reports() call for all sources.
Near-duplicates, clustering, scoring and incidents are left entirely to pipeline.py.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from ..extraction_providers import StructuredExtractionProvider
from ..pipeline import process_reports
from ..schemas import IncomingReport
from .apify import ApifyAdapter
from .base import IngestionError, SourceAdapter, normalize
from .tavily import TavilyAdapter

SOURCES = ("tavily", "apify")


def default_adapters() -> dict[str, SourceAdapter]:
    return {"tavily": TavilyAdapter(), "apify": ApifyAdapter()}


def configured_sources(adapters: Optional[dict[str, SourceAdapter]] = None) -> dict[str, bool]:
    adapters = adapters or default_adapters()
    return {name: adapters[name].available() for name in SOURCES}


def _empty_summary(source: str) -> dict[str, Any]:
    return {"source": source, "status": "skipped", "retrieved_count": 0, "normalized_count": 0, "inserted_count": 0,
            "duplicate_count": 0, "rejected_count": 0, "out_of_scope_count": 0, "clustered_count": 0, "message": None}


def run_ingestion(
    conn: sqlite3.Connection,
    sources: list[str],
    adapters: Optional[dict[str, SourceAdapter]] = None,
    provider: Optional[StructuredExtractionProvider] | bool = True,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    adapters = adapters or default_adapters()
    ingested_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    summaries = {source: _empty_summary(source) for source in sources}
    pending: dict[str, tuple[IncomingReport, dict[str, Any]]] = {}
    owner: dict[str, str] = {}

    for source in sources:
        summary, adapter = summaries[source], adapters[source]
        if not adapter.available():
            summary.update(status="not_configured", message=adapter.missing_config())
            continue
        try:
            fetched = adapter.fetch()
        except IngestionError as error:
            summary.update(status="failed", message=str(error))
            continue
        except Exception as error:  # an adapter bug must never take the app down
            summary.update(status="failed", message=f"unexpected error: {type(error).__name__}")
            continue
        summary.update(retrieved_count=fetched.retrieved, rejected_count=fetched.rejected,
                       status="ok" if fetched.retrieved else "empty",
                       message="; ".join(fetched.warnings[:3]) or None)
        for item in fetched.items:
            normalized = normalize(item, ingested_at)
            if normalized is None:
                summary["rejected_count"] += 1
                continue
            report, provenance = normalized
            summary["normalized_count"] += 1
            if report.id in pending:  # same article from another query or the other source
                summary["duplicate_count"] += 1
                existing = pending[report.id][1]
                existing["queries"] = sorted(set(existing["queries"]) | set(provenance["queries"]))
                existing["metadata"].setdefault("also_seen_in", [])
                if source not in existing["metadata"]["also_seen_in"] and source != existing["origin"]:
                    existing["metadata"]["also_seen_in"].append(source)
                continue
            if conn.execute("SELECT 1 FROM reports WHERE id = ?", (report.id,)).fetchone():  # ingested in an earlier run
                summary["duplicate_count"] += 1
                continue
            pending[report.id] = (report, provenance)
            owner[report.id] = source

    pipeline_result = None
    batch_id = f"live-{ingested_at.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    if pending:
        pipeline_result = process_reports(conn, [report for report, _ in pending.values()], batch_id, provider)
        conn.executemany(
            """INSERT OR REPLACE INTO report_provenance (report_id, origin, url, title, original_content, queries_json, published_at, ingested_at, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(report_id, prov["origin"], prov["url"], prov["title"], prov["original_content"], json.dumps(prov["queries"]), prov["published_at"],
              prov["ingested_at"], json.dumps(prov["metadata"], ensure_ascii=False, default=str)) for report_id, (_, prov) in pending.items()],
        )
        conn.commit()
        placeholders = ",".join("?" for _ in pending)
        for report_id, in_scope, is_duplicate, incident_id in conn.execute(
            f"SELECT id, in_scope, is_duplicate, incident_id FROM reports WHERE id IN ({placeholders})", list(pending)
        ).fetchall():
            summary = summaries[owner[report_id]]
            summary["inserted_count"] += 1
            summary["out_of_scope_count"] += int(not in_scope)
            summary["duplicate_count"] += int(bool(is_duplicate))
            summary["clustered_count"] += int(bool(incident_id) and not is_duplicate)

    ran = [summary for summary in summaries.values() if summary["status"] in ("ok", "empty")]
    status = "ok" if ran and len(ran) == len(summaries) else "partial" if ran else "unavailable"
    return {
        "dataset": "live",
        "status": status,
        "batch_id": batch_id if pending else None,
        "sources": list(summaries.values()),
        "pipeline": None if pipeline_result is None else {
            key: pipeline_result[key] for key in ("received", "out_of_scope", "duplicates", "located", "unlocated", "incidents_before", "incidents_after", "batch_incident_count", "new_incident_ids", "updated_incident_ids", "elapsed_ms")
        },
    }
