"""Future open-source model adapter.

Implements the same StructuredExtractionProvider contract as the proprietary adapter. It is
intentionally inert until an approved endpoint is configured and the fixture comparison in
docs/07-hybrid-extraction-design.md has passed; no model runtime is bundled with the MVP.
"""

from __future__ import annotations

from typing import Any

from ..config import OPEN_SOURCE_LLM_ENDPOINT, OPEN_SOURCE_LLM_MODEL
from .base import ProviderError, ProviderRequest


class OpenSourceProvider:
    name = "open_source"

    def __init__(self, endpoint: str = OPEN_SOURCE_LLM_ENDPOINT, model: str = OPEN_SOURCE_LLM_MODEL) -> None:
        self.endpoint = endpoint
        self.model = model or "unconfigured"

    def available(self) -> bool:
        # Deliberately false until the adapter is implemented and evaluated.
        return False

    def extract(self, request: ProviderRequest) -> dict[str, Any]:
        raise ProviderError("open-source provider not implemented in the MVP")
