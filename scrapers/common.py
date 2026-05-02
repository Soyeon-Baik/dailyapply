"""Shared models and utilities for all scrapers."""

import re
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class RawJob(BaseModel):
    id: str
    platform: str  # greenhouse | lever | ashby | workable
    company: str
    company_priority: str  # high | medium | low
    title: str
    location: str
    remote: bool = False
    url: str
    description_raw: str
    description_html: Optional[str] = None
    posted_at: Optional[datetime] = None
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    days_old: Optional[float] = None
    hard_filtered: bool = False
    hard_filter_reason: Optional[str] = None


_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def clean_html(html: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    if not html:
        return ""
    text = _TAG_RE.sub(" ", html)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&nbsp;", " ").replace("&#39;", "'").replace("&quot;", '"')
    return _WHITESPACE_RE.sub(" ", text).strip()


def parse_posted_at(raw, platform: str) -> Optional[datetime]:
    """Parse platform-specific date formats into UTC datetime."""
    if raw is None:
        return None
    try:
        if platform == "lever":
            # Lever uses Unix milliseconds
            return datetime.fromtimestamp(int(raw) / 1000, tz=timezone.utc)
        if isinstance(raw, (int, float)):
            # Treat as Unix seconds
            return datetime.fromtimestamp(raw, tz=timezone.utc)
        if isinstance(raw, str):
            raw = raw.rstrip("Z")
            for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
    except Exception:
        pass
    return None


def compute_days_old(posted_at: Optional[datetime]) -> Optional[float]:
    if posted_at is None:
        return None
    now = datetime.now(timezone.utc)
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=timezone.utc)
    delta = now - posted_at
    return round(delta.total_seconds() / 86400, 1)
