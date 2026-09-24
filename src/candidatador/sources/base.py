"""Contract every job source implements. See docs/nova-fonte.md."""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from typing import Any, ClassVar

import httpx
from pydantic import BaseModel, Field

KEYWORD_WORKERS = 4
USER_AGENT = "candidatador/0.1 (+https://github.com/davidogral/candidatador)"


class SearchQuery(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    location: str | None = None
    remote_only: bool = False
    posted_within_days: int | None = None
    limit: int = 50
    # Search-time filters (see matching/filters.py). None = use the profile's default.
    seniority: list[str] | None = None
    include_unknown_seniority: bool | None = None
    countries: list[str] | None = None
    include_unknown_country: bool | None = None
    contract_types: list[str] | None = None
    exclude_talent_pool: bool | None = None
    title_must_match: bool | None = None


class JobPosting(BaseModel):
    """Normalized job returned by every source."""

    source: str
    external_id: str
    title: str
    company: str = ""
    location: str = ""
    remote: bool | None = None
    url: str
    apply_url: str = ""
    description: str = ""
    employment_type: str = ""
    salary: str = ""
    posted_at: datetime | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @property
    def id(self) -> str:
        return f"{self.source}:{self.external_id}"

    @property
    def fingerprint(self) -> str:
        """Same title + company => same job, even when found on different sites."""
        key = f"{normalize(self.title)}|{normalize(self.company)}"
        return hashlib.sha1(key.encode()).hexdigest()


class SourceError(RuntimeError):
    pass


class JobSource(ABC):
    #: unique identifier used in config.yaml and on the CLI
    name: ClassVar[str]
    #: human-friendly name
    display_name: ClassVar[str]
    #: regions where this source is most relevant, e.g. ("BR",), ("global",)
    regions: ClassVar[tuple[str, ...]] = ("global",)
    #: short note on terms of use, shown to the user when the source is enabled
    terms_note: ClassVar[str | None] = None

    def __init__(self, settings: dict[str, Any] | None = None, client: httpx.Client | None = None):
        self.settings = settings or {}
        self.client = client or httpx.Client(
            timeout=30, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        )

    @abstractmethod
    def search(self, query: SearchQuery) -> Iterable[JobPosting]:
        """Yield postings matching the query. Must not raise for 'no results'."""

    def max_results(self, query: SearchQuery) -> int:
        return int(self.settings.get("max_results") or query.limit)

    def per_keyword(
        self, query: SearchQuery, fetch: Callable[[str], list[JobPosting]]
    ) -> list[JobPosting]:
        """Run `fetch` for every keyword in parallel and merge the results without repeats."""
        terms = query.keywords or [""]
        with ThreadPoolExecutor(max_workers=min(KEYWORD_WORKERS, len(terms))) as pool:
            batches = list(pool.map(fetch, terms))
        seen: set[str] = set()
        merged = []
        for batch in batches:
            for posting in batch:
                if posting.external_id not in seen:
                    seen.add(posting.external_id)
                    merged.append(posting)
        return merged


# --------------------------------------------------------------------------- helpers

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    if "&lt;" in value:  # some APIs (Greenhouse) return HTML-escaped HTML
        value = html.unescape(value)
    text = re.sub(r"<(br|/p|/li|/h\d)\s*/?>", "\n", value, flags=re.I)
    text = html.unescape(_TAG_RE.sub(" ", text)).replace("\xa0", " ")
    lines = (_WS_RE.sub(" ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def matches_keywords(text: str, keywords: list[str]) -> bool:
    """True if any keyword appears in the text (accent/case-insensitive)."""
    if not keywords:
        return True
    haystack = f" {normalize(text)} "
    return any(f" {normalize(k)} " in haystack for k in keywords if k.strip())


def parse_datetime(value: Any) -> datetime | None:
    """Parse ISO strings, epoch millis, dates or datetimes into an aware UTC datetime."""
    if value in (None, ""):
        return None
    try:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, date):
            parsed = datetime(value.year, value.month, value.day)
        elif isinstance(value, int | float):  # epoch millis (Lever)
            parsed = datetime.fromtimestamp(value / 1000, tz=UTC)
        else:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, OSError, OverflowError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
