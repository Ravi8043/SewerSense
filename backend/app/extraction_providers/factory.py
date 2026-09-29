from __future__ import annotations

from ..config import EXTRACTION_MODE, LLM_PROVIDER
from .base import StructuredExtractionProvider
from .open_source import OpenSourceProvider
from .proprietary import AnthropicProvider

_PROVIDERS = {"anthropic": AnthropicProvider, "open_source": OpenSourceProvider}
_override: StructuredExtractionProvider | None = None


def get_provider() -> StructuredExtractionProvider | None:
    """The configured provider, or None when extraction runs rules-only by configuration."""
    if _override is not None:
        return _override
    if EXTRACTION_MODE != "hybrid":
        return None
    factory = _PROVIDERS.get(LLM_PROVIDER)
    return factory() if factory else None


def set_provider_override(provider: StructuredExtractionProvider | None) -> None:
    """Test hook: inject a fake provider (or None to restore configuration)."""
    global _override
    _override = provider
