"""Anthropic structured-output adapter (the current proprietary provider)."""

from __future__ import annotations

from typing import Any

from ..config import LLM_MAX_OUTPUT_TOKENS, LLM_MAX_RETRIES, LLM_MODEL, LLM_TIMEOUT_SECONDS, llm_api_key
from ..schemas import LLMExtraction
from .base import SYSTEM_PROMPT, ProviderError, ProviderRequest, build_user_prompt

try:  # The SDK is optional: without it the demo runs in rules fallback mode.
    import anthropic
except ImportError:  # pragma: no cover - depends on the local environment
    anthropic = None  # type: ignore[assignment]


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str = LLM_MODEL) -> None:
        self.model = model
        self._client: Any = None

    def available(self) -> bool:
        return anthropic is not None and bool(llm_api_key())

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=llm_api_key(), timeout=LLM_TIMEOUT_SECONDS, max_retries=LLM_MAX_RETRIES)
        return self._client

    def extract(self, request: ProviderRequest) -> dict[str, Any]:
        if not self.available():
            raise ProviderError("provider not configured")
        try:
            response = self._get_client().messages.parse(
                model=self.model,
                max_tokens=LLM_MAX_OUTPUT_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": build_user_prompt(request)}],
                output_format=LLMExtraction,
                output_config={"effort": "low"},
            )
        except anthropic.APIStatusError as error:
            raise ProviderError(f"api status {error.status_code}") from None
        except anthropic.APIConnectionError:
            raise ProviderError("connection or timeout error") from None
        except Exception as error:  # SDK-side schema validation or unexpected client errors
            raise ProviderError(f"client error: {type(error).__name__}") from None
        if response.stop_reason == "refusal":
            raise ProviderError("model refusal")
        if response.stop_reason == "max_tokens":
            raise ProviderError("truncated output")
        parsed = response.parsed_output
        if parsed is None:
            raise ProviderError("no structured output")
        # Return plain data; the orchestrator re-validates with extra="forbid".
        return parsed.model_dump()
