"""Real-API smoke test for live ingestion. NOT part of pytest; it uses your .env keys and spends
provider credits. It ingests into a throwaway SQLite file, so neither the demo nor your live
dataset is touched.

Usage (from the project root):  backend/.venv/Scripts/python.exe backend/scripts/smoke_live_ingest.py [tavily] [apify]
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config, db  # noqa: E402  (config loads the project .env)
from app.ingestion import configured_sources, run_ingestion  # noqa: E402
from app.ingestion.tavily import TavilyAdapter  # noqa: E402
from app.ingestion.apify import ApifyAdapter  # noqa: E402


def main() -> int:
    wanted = [name for name in sys.argv[1:] if name in ("tavily", "apify")] or ["tavily", "apify"]
    available = configured_sources()
    print("Configured:", available)
    runnable = [name for name in wanted if available[name]]
    if not runnable:
        print("NOT RUN: no requested source has credentials. Fill in .env (see .env.example).")
        return 2
    # Keep the smoke test small: two Tavily queries, a handful of results.
    config.TAVILY_MAX_RESULTS = 3
    adapters = {"tavily": TavilyAdapter(queries=config.TAVILY_QUERIES[:2]), "apify": ApifyAdapter()}
    with tempfile.TemporaryDirectory() as folder:
        conn = db.connect(Path(folder) / "smoke.sqlite")
        db.initialize(conn)
        result = run_ingestion(conn, runnable, adapters=adapters)
        print(json.dumps({key: result[key] for key in ("status", "sources", "pipeline")}, indent=2))
        reports = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        in_scope = conn.execute("SELECT COUNT(*) FROM reports WHERE in_scope = 1").fetchone()[0]
        incidents = conn.execute("SELECT id, title, priority, report_count FROM incidents ORDER BY priority DESC LIMIT 5").fetchall()
        print(f"\nSQLite: {reports} reports stored, {in_scope} in scope, {len(incidents)} incidents shown below")
        for row in incidents:
            print(f"  {row[0]}  priority {row[2]:>3}  {row[3]} reports  {row[1]}")
        sample = conn.execute("SELECT p.origin, p.url, r.raw_text FROM reports r JOIN report_provenance p ON p.report_id = r.id LIMIT 3").fetchall()
        for origin, url, text in sample:
            print(f"\n[{origin}] {url}\n  {text[:160]}")
        conn.close()
    ok = all(source["status"] in ("ok", "empty") for source in result["sources"] if source["source"] in runnable)
    print("\nSMOKE TEST", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
