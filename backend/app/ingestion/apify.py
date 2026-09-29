"""Apify Actor adapter (fetch only). The Actor, its input, and result flattening are configuration."""

from __future__ import annotations

import json
from typing import Any, Optional

from .. import config
from .base import ExternalItem, FetchResult, IngestionError, post_json

# Common field names across Apify Actors, checked in order. Unknown shapes are rejected, not guessed.
TEXT_FIELDS = ("text", "full_text", "fullText", "content", "description", "caption", "snippet", "body", "markdown")
URL_FIELDS = ("url", "link", "postUrl", "permalink")
TITLE_FIELDS = ("title", "headline")
TIME_FIELDS = ("publishedAt", "published_at", "date", "createdAt", "created_at", "timestamp", "time")
AUTHOR_FIELDS = ("author", "username", "userName", "ownerUsername", "authorName")


def _first(item: dict[str, Any], names: tuple[str, ...]) -> Optional[Any]:
    for name in names:
        value = item.get(name)
        if value not in (None, "", [], {}):
            return value
    return None


class ApifyAdapter:
    name = "apify"

    def available(self) -> bool:
        return bool(config.apify_api_token() and config.apify_actor_id())

    def missing_config(self) -> str:
        missing = [name for name, value in (("APIFY_API_TOKEN", config.apify_api_token()), ("APIFY_ACTOR_ID", config.apify_actor_id())) if not value]
        return f"{' and '.join(missing)} not set"

    def fetch(self) -> FetchResult:
        if not self.available():
            raise IngestionError(self.missing_config())
        try:
            actor_input = json.loads(config.APIFY_ACTOR_INPUT or "{}")
        except ValueError:
            raise IngestionError("APIFY_ACTOR_INPUT is not valid JSON") from None
        actor = config.apify_actor_id().replace("/", "~")
        payload = post_json(
            f"{config.APIFY_API_BASE}/acts/{actor}/run-sync-get-dataset-items",
            actor_input,
            config.apify_api_token(),
            config.APIFY_TIMEOUT_SECONDS,
            params={"format": "json", "clean": "true", "maxItems": config.APIFY_MAX_ITEMS, "unwind": config.APIFY_UNWIND},
        )
        if not isinstance(payload, list):
            raise IngestionError("Actor returned an unexpected payload (expected a list of dataset items)")
        items: list[ExternalItem] = []
        rejected = 0
        for record in payload:
            item = self._to_item(record, actor)
            if item is None:
                rejected += 1
            else:
                items.append(item)
        return FetchResult(items=items, retrieved=len(payload), rejected=rejected)

    @staticmethod
    def _to_item(record: Any, actor: str) -> Optional[ExternalItem]:
        if not isinstance(record, dict):
            return None
        text = _first(record, TEXT_FIELDS)
        if not isinstance(text, str) or not text.strip():
            return None
        url = _first(record, URL_FIELDS)
        title = _first(record, TITLE_FIELDS)
        published = _first(record, TIME_FIELDS)
        author = _first(record, AUTHOR_FIELDS)
        if isinstance(author, dict):
            author = author.get("userName") or author.get("username") or author.get("name")
        query = record.get("searchQuery")
        if isinstance(query, dict):
            query = query.get("term")
        used = set(TEXT_FIELDS + URL_FIELDS + TITLE_FIELDS + TIME_FIELDS + AUTHOR_FIELDS)
        extra = {key: value for key, value in record.items() if key not in used and isinstance(value, (str, int, float, bool)) and len(str(value)) <= 200}
        return ExternalItem(
            origin="apify",
            source_type=config.APIFY_SOURCE_TYPE,
            content=text,
            url=url if isinstance(url, str) else None,
            title=title if isinstance(title, str) else None,
            published_at=str(published) if published is not None else None,
            query=query if isinstance(query, str) else None,
            author=str(author) if author else None,
            metadata={"actor": actor, **dict(list(extra.items())[:15])},
        )
