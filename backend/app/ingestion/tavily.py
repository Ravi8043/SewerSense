"""Tavily web/news search adapter (fetch only)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from .. import config
from .base import ExternalItem, FetchResult, IngestionError, post_json

_KEPT_FIELDS = ("score",)


class TavilyAdapter:
    name = "tavily"

    def __init__(self, queries: Optional[list[str]] = None) -> None:
        self.queries = queries if queries is not None else list(config.TAVILY_QUERIES)

    def available(self) -> bool:
        return bool(config.tavily_api_key())

    def missing_config(self) -> str:
        return "TAVILY_API_KEY is not set"

    def _search(self, query: str) -> Any:
        body: dict[str, Any] = {"query": query, "topic": config.TAVILY_TOPIC, "max_results": config.TAVILY_MAX_RESULTS, "search_depth": "basic"}
        if config.TAVILY_TIME_RANGE:
            body["time_range"] = config.TAVILY_TIME_RANGE
        return post_json(config.TAVILY_API_URL, body, config.tavily_api_key(), config.TAVILY_TIMEOUT_SECONDS)

    def fetch(self) -> FetchResult:
        if not self.available():
            raise IngestionError(self.missing_config())
        if not self.queries:
            return FetchResult(items=[], retrieved=0)
        with ThreadPoolExecutor(max_workers=min(4, len(self.queries))) as pool:
            outcomes = list(pool.map(self._safe_search, self.queries))
        items: list[ExternalItem] = []
        retrieved = rejected = 0
        warnings: list[str] = []
        failures = 0
        for query, (payload, error) in zip(self.queries, outcomes):
            if error:
                failures += 1
                warnings.append(f"query '{query}': {error}")
                continue
            results = payload.get("results") if isinstance(payload, dict) else None
            if not isinstance(results, list):
                failures += 1
                warnings.append(f"query '{query}': malformed response (no results list)")
                continue
            for result in results:
                retrieved += 1
                item = self._to_item(result, query)
                if item is None:
                    rejected += 1
                else:
                    items.append(item)
        if failures == len(self.queries):
            raise IngestionError(warnings[0] if warnings else "all Tavily queries failed")
        return FetchResult(items=items, retrieved=retrieved, rejected=rejected, warnings=warnings)

    def _safe_search(self, query: str) -> tuple[Any, Optional[str]]:
        try:
            return self._search(query), None
        except IngestionError as error:
            return None, str(error)

    @staticmethod
    def _to_item(result: Any, query: str) -> Optional[ExternalItem]:
        if not isinstance(result, dict):
            return None
        content, url = result.get("content"), result.get("url")
        if not isinstance(content, str) or not content.strip() or not isinstance(url, str):
            return None
        title = result.get("title")
        published = result.get("published_date")
        return ExternalItem(
            origin="tavily",
            source_type="news",
            content=content,
            url=url,
            title=title if isinstance(title, str) else None,
            published_at=published if isinstance(published, str) else None,
            query=query,
            metadata={key: result[key] for key in _KEPT_FIELDS if key in result},
        )
