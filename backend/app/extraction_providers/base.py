"""Provider-neutral contract for structured LLM extraction."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from ..schemas import RuleCandidates


class ProviderError(Exception):
    """Any provider, transport, refusal, or parsing failure. Always resolves to rules fallback."""


@dataclass(frozen=True)
class ProviderRequest:
    """The only data a provider may see: synthetic report text, its source class, and the
    deterministic candidates. No database handles, keys, or other reports."""

    raw_text: str
    source: str
    candidates: RuleCandidates
    allowed_localities: tuple[str, ...]
    allowed_roads: tuple[str, ...]
    allowed_landmarks: tuple[str, ...]
    allowed_categories: tuple[str, ...]


SYSTEM_PROMPT = (
    "You extract structured fields from synthetic municipal sewerage complaints for Hyderabad. "
    "Return only the requested JSON object, with no narrative. Rules: "
    "(1) choose locality, road and landmark only from the allowed lists, otherwise null; "
    "(2) never output coordinates, people, phone numbers, causes, or claims that work was completed; "
    "(3) households and duration_hours must come from explicit statements in the text, otherwise null — never estimate numbers; "
    "(4) in_scope is true only for sewerage, drainage, manhole, or wastewater problems; garbage, water supply or pressure, "
    "streetlights, and spam are out of scope; "
    "(5) severity is 1 (nuisance) to 5 (immediate danger to life, such as an open manhole); "
    "(6) near_school_or_hospital is true only if the text says so; "
    "(7) category_confidence is your 0-1 confidence in the category."
)


def build_user_prompt(request: ProviderRequest) -> str:
    return json.dumps(
        {
            "report": request.raw_text,
            "source_type": request.source,
            "rule_candidates": request.candidates.model_dump(),
            "allowed_localities": list(request.allowed_localities),
            "allowed_roads": list(request.allowed_roads),
            "allowed_landmarks": list(request.allowed_landmarks),
            "allowed_categories": list(request.allowed_categories),
        },
        ensure_ascii=False,
    )


class StructuredExtractionProvider(Protocol):
    name: str
    model: str

    def available(self) -> bool:
        """True when credentials/endpoint are configured. No network call."""
        ...

    def extract(self, request: ProviderRequest) -> dict[str, Any]:
        """Return the model's JSON object (unvalidated). Raise ProviderError on any failure."""
        ...
