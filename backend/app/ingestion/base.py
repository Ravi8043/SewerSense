"""Shared ingestion contract: every external source becomes an IncomingReport.

Adapters only *fetch*. Normalization lives here once, so Tavily and Apify produce exactly the
same report representation and the rest of SewerSense cannot tell them apart.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional, Protocol

from ..config import INGEST_MAX_TEXT_CHARS
from ..schemas import IncomingReport

PIPELINE_SOURCES = {"phone", "social", "whatsapp", "news", "official", "field"}
_TRACKING_PARAMS = re.compile(r"^(utm_|fbclid|gclid|ref$|ref_)")


class IngestionError(Exception):
    """A source could not be fetched. Messages never contain credentials."""


@dataclass
class ExternalItem:
    """One raw result from an external source, before normalization."""

    origin: str  # "tavily" | "apify"
    source_type: str  # pipeline source class, e.g. "news" or "social"
    content: str
    url: Optional[str] = None
    title: Optional[str] = None
    published_at: Optional[str] = None  # exactly as supplied by the source, never invented
    query: Optional[str] = None
    author: Optional[str] = None  # only used (hashed) to derive a pseudonymous handle
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FetchResult:
    items: list[ExternalItem]
    retrieved: int  # raw records returned by the source
    rejected: int = 0  # records the adapter could not parse
    warnings: list[str] = field(default_factory=list)


class SourceAdapter(Protocol):
    name: str

    def available(self) -> bool: ...

    def missing_config(self) -> str: ...

    def fetch(self) -> FetchResult: ...


# ---------------------------------------------------------------------------------------------
# HTTP (standard library only)
# ---------------------------------------------------------------------------------------------
def post_json(url: str, body: Any, token: str, timeout: float, params: Optional[dict[str, Any]] = None) -> Any:
    if params:
        url = f"{url}?{urllib.parse.urlencode({key: value for key, value in params.items() if value not in (None, '')})}"
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        raise IngestionError(f"HTTP {error.code} from {urllib.parse.urlparse(url).netloc}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        reason = getattr(error, "reason", error)
        raise IngestionError(f"network error contacting {urllib.parse.urlparse(url).netloc}: {type(reason).__name__}") from None
    try:
        return json.loads(payload)
    except ValueError:
        raise IngestionError("response was not valid JSON") from None


# ---------------------------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------------------------
def canonical_url(url: Optional[str]) -> Optional[str]:
    if not url or not isinstance(url, str):
        return None
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    query = urllib.parse.urlencode([(key, value) for key, value in urllib.parse.parse_qsl(parsed.query) if not _TRACKING_PARAMS.match(key)])
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/") or "/", query, ""))


def _parse_time(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    text = str(value).strip()
    for parser in (lambda raw: datetime.fromisoformat(raw.replace("Z", "+00:00")), parsedate_to_datetime):
        try:
            parsed = parser(text)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError, IndexError):
            continue
    return None


def _slug(value: str, limit: int = 24) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())[:limit] or "web"


def normalize(item: ExternalItem, ingested_at: datetime) -> Optional[tuple[IncomingReport, dict[str, Any]]]:
    """ExternalItem -> (IncomingReport, provenance row). Returns None for unusable items."""
    content = re.sub(r"\s+", " ", item.content or "").strip()
    title = re.sub(r"\s+", " ", item.title or "").strip() or None
    if title and not content.lower().startswith(title.lower()[:40]):
        text = f"{title}. {content}" if content else title
    else:
        text = content
    if len(text) < 20:
        return None
    text = text[:INGEST_MAX_TEXT_CHARS]
    url = canonical_url(item.url)
    source = item.source_type if item.source_type in PIPELINE_SOURCES else "news"

    domain = urllib.parse.urlsplit(url).netloc.removeprefix("www.") if url else item.origin
    handle = f"{source}_{_slug(domain.split('.')[0] if '.' in domain else domain)}"
    if item.author:
        # Pseudonymous: the same author maps to the same handle without storing the name.
        handle += "_" + hashlib.sha1(str(item.author).encode()).hexdigest()[:6]

    published = _parse_time(item.published_at)
    created = published if published and published <= ingested_at else ingested_at
    identity = url or hashlib.sha1(text.lower().encode()).hexdigest()
    report = IncomingReport(
        id="EXT-" + hashlib.sha1(identity.encode()).hexdigest()[:16],
        source=source,
        source_handle=handle,
        raw_text=text,
        created_at=created.astimezone(timezone.utc).replace(microsecond=0).isoformat(),
    )
    provenance = {
        "origin": item.origin,
        "url": url,
        "title": title,
        "original_content": item.content,
        "queries": [item.query] if item.query else [],
        "published_at": item.published_at if item.published_at not in ("", None) else None,
        "ingested_at": ingested_at.replace(microsecond=0).isoformat(),
        "metadata": item.metadata,
    }
    return report, provenance
