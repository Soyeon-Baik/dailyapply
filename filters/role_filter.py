"""PM role title filter + domain-score gating for Claude API calls."""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapers.common import RawJob

# ── Title filter (is_pm_role) ─────────────────────────────────────────────────

INCLUDE_TITLE_PATTERNS = [
    r"\bproduct manager\b",
    r"\bsenior product manager\b",
    r"\bstaff product manager\b",
    r"\bprincipal product manager\b",
    r"\bgroup product manager\b",
    r"\blead product manager\b",
    r"\bdirector of product\b",
    r"\bhead of product\b",
    r"\bproduct lead\b",
    r"\bvp of product\b",
    r"\bvice president.*product\b",
]

EXCLUDE_TITLE_PATTERNS = [
    r"\bproduct marketing\b",
    r"\bprogram manager\b",
    r"\bproject manager\b",
    r"\btechnical program manager\b",
    r"\btpm\b",
    r"\bgrowth marketing\b",
    r"\bmarketing manager\b",
    r"\bsales\b",
    r"\boperations manager\b",
    r"\bfinance\b",
    r"\baccounting\b",
    r"\brecruiter\b",
    r"\bdata scientist\b",
    r"\bdata analyst\b",
    r"\bsoftware engineer\b",
    r"\bsoftware developer\b",
]

_include_re = [re.compile(p, re.IGNORECASE) for p in INCLUDE_TITLE_PATTERNS]
_exclude_re = [re.compile(p, re.IGNORECASE) for p in EXCLUDE_TITLE_PATTERNS]


def is_pm_role(title: str) -> bool:
    """Return True if the job title is a PM role we want to see."""
    for pattern in _exclude_re:
        if pattern.search(title):
            return False
    for pattern in _include_re:
        if pattern.search(title):
            return True
    return False


# ── should_score() constants ──────────────────────────────────────────────────

HARD_EXCLUDE = [
    "firmware", "hardware lifecycle", "supply chain",
    "legal operations", "accounting", "recruiting",
    "security clearance", "active clearance",
    "us citizen only", "no sponsorship",
]

EXCLUDE_TITLE = [
    "product marketing manager", "program manager",
    "technical program manager", "project manager",
    "engineering manager", "software engineer",
    "machine learning engineer", "data scientist",
    "data engineer", "designer", "researcher",
    "analyst", "intern", "new grad", "associate product manager",
]

US_STATE_ABBR = ["WA", "CA", "NY", "NJ", "TX", "MA", "IL", "CO", "OR", "FL", "GA", "VA", "DC"]
US_STATE_FULL = [
    "washington", "california", "new york", "new jersey", "texas",
    "massachusetts", "illinois", "colorado", "oregon", "florida", "georgia", "virginia",
]

LOCATION_EXCLUDE = [
    "remote - canada", "remote - uk", "remote - india",
    "india", "bangalore", "hyderabad", "mumbai", "pune",
    "canada", "toronto", "vancouver",
    "uk", "london", "united kingdom",
    "china", "beijing", "shanghai",
    "singapore", "australia", "germany",
]

HIGH_SIGNAL = [
    "search", "discovery", "recommendation", "personalization",
    "ranking", "relevance", "ecommerce", "marketplace",
    "catalog", "shopping", "product discovery",
    "semantic search", "query understanding", "search relevance", "browse",
]

MEDIUM_SIGNAL = [
    "ai", "ml", "llm", "generative", "nlp",
    "conversational", "automation", "chatbot", "assistant", "agent", "ai agent",
]

SOFT_EXCLUDE = [
    "security", "compliance", "privacy", "risk", "finance", "ads auction", "infrastructure",
]


def has_us_location(location: str) -> bool:
    for abbr in US_STATE_ABBR:
        if re.search(rf"\b{re.escape(abbr)}\b", location, re.IGNORECASE):
            return True
    if any(state in location for state in US_STATE_FULL):
        return True
    if any(term in location for term in ["united states", "usa", "u.s."]):
        return True
    return False


def should_score(job: "RawJob", company_priority: str = "low", target_status: str = "watchlist") -> tuple[bool, str]:
    """Decide whether to send a job to Claude for scoring.

    Returns (True, reason) or (False, reason).
    """
    title = job.title.lower()
    location = (job.location or "").lower()
    hard_text = (title + " " + (job.description_raw or "")[:3000]).lower()
    domain_text = (title + " " + (job.description_raw or "")[:500]).lower()

    if any(kw in hard_text for kw in HARD_EXCLUDE):
        return False, "hard_exclude"
    if any(kw in title for kw in EXCLUDE_TITLE):
        return False, "exclude_title"

    has_exclude = any(kw in location for kw in LOCATION_EXCLUDE)
    if has_exclude:
        return False, "location_exclude"

    is_remote = "remote" in location
    has_us = (
        has_us_location(location)
        or any(t in location for t in ["remote us", "remote - united states"])
        or (is_remote and not has_exclude)
    )
    if not has_us:
        return False, "location_not_us"

    high = sum(1 for kw in HIGH_SIGNAL if kw in domain_text)
    medium = sum(1 for kw in MEDIUM_SIGNAL if kw in domain_text)
    domain_score = high * 2 + medium

    soft = any(kw in domain_text for kw in SOFT_EXCLUDE)
    threshold = 4 if soft else 3
    is_senior = any(t in title for t in ["senior", "staff", "principal"])
    is_primary = target_status == "primary"

    if is_primary and company_priority == "high" and domain_score >= 2:
        return True, "primary_target"
    if company_priority == "high" and domain_score >= 3:
        return True, "target_company"
    if is_senior and domain_score >= 2:
        return True, "senior_domain_match"
    if domain_score >= threshold:
        return True, "domain_match"
    return False, "low_domain_score"
