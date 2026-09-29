"""Test configuration: isolated temporary data directory and no LLM credentials."""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_TEMP = tempfile.mkdtemp(prefix="sewersense-tests-")
os.environ["SEWERSENSE_DATA_DIR"] = _TEMP
os.environ["SEWERSENSE_DB_PATH"] = str(Path(_TEMP) / "test.sqlite")
os.environ.pop("ANTHROPIC_API_KEY", None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from app import db, service  # noqa: E402
from app.extraction_providers.factory import set_provider_override  # noqa: E402

FIXED_NOW = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _no_provider_override():
    set_provider_override(None)
    yield
    set_provider_override(None)


@pytest.fixture(scope="session")
def demo_db():
    """Baseline + one simulated batch, processed by the real pipeline in rules mode."""
    conn = db.connect(":memory:")
    db.initialize(conn)
    baseline = service.seed_baseline(conn, now=FIXED_NOW, provider=None)
    batch = service.simulate(conn, now=FIXED_NOW, provider=None)
    yield conn, baseline, batch
    conn.close()
