"""Structured-extraction provider adapters. Vendor code lives only in this package."""

from __future__ import annotations

from .base import ProviderError, ProviderRequest, StructuredExtractionProvider
from .factory import get_provider

__all__ = ["ProviderError", "ProviderRequest", "StructuredExtractionProvider", "get_provider"]
