"""Rebuild the local demo database from the deterministic synthetic baseline.

Usage (from backend/):  .venv/Scripts/python seed.py [--simulate]
"""

from __future__ import annotations

import argparse
import sys

from app import config, db, service


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the SewerSense demo database.")
    parser.add_argument("--simulate", action="store_true", help="also run one 100-report simulation batch")
    args = parser.parse_args()
    conn = db.connect(config.DATABASE_PATH)
    try:
        result = service.seed_baseline(conn)
        print(f"Baseline: {result['received']} reports -> {result['incidents_after']} active incidents "
              f"({result['duplicates']} duplicates, extraction: {result['extraction_mode']}) in {result['elapsed_ms']} ms")
        if args.simulate:
            batch = service.simulate(conn)
            print(f"Simulation {batch['batch_id']}: {batch['received']} reports -> {batch['batch_incident_count']} incidents "
                  f"({len(batch['new_incident_ids'])} new), hero {batch['hero_incident_id']}, {batch['elapsed_ms']} ms")
        print(f"Database: {config.DATABASE_PATH}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
