"""Optional live-data input adapters (Tavily, Apify) feeding the existing pipeline."""

from __future__ import annotations

from .base import ExternalItem, FetchResult, IngestionError, normalize
from .service import SOURCES, configured_sources, default_adapters, run_ingestion

__all__ = ["ExternalItem", "FetchResult", "IngestionError", "SOURCES", "configured_sources", "default_adapters", "normalize", "run_ingestion"]
