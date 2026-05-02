"""PM role title filter + rule-based pre-filter for Claude API gating.

Design rationale:
  - \bpm\b is too noisy (Program Manager, Project Manager, Product Marketing Manager all match)
  - "Growth Product Manager" must pass; "Growth Marketing Manager" must not
  - Checking exclude patterns FIRST prevents false positives from loose include patterns
  - rule_based_prefilter() runs after title/location/hard filters, before Claude API calls
"""

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


# ── Rule-based pre-filter (gates Claude API calls) ────────────────────────────

_STRONG_TITLE_KEYWORDS = [
    "senior product manager", "sr. product manager",
    "staff product manager", "principal product manager",
    "lead product manager", "group product manager",
]

_INCLUDE_LOCATION_KEYWORDS = [
    "seattle", "bellevue", "redmond",
    "san francisco", "sf", "bay area", "san jose", "sunnyvale", "mountain view",
    "new york", "nyc", "remote", "united states", "us",
]

_EXCLUDE_LOCATION_KEYWORDS = [
    "india", "bangalore", "hyderabad", "chennai", "pune",
    "china", "beijing", "shanghai",
    "london", "united kingdom",
    "canada", "toronto", "vancouver",
]

_HARD_EXCLUDE_KEYWORDS = [
    "firmware", "hardware lifecycle", "supply chain", "legal operations",
    "accounting", "recruiting", "real estate agent",
    "active clearance", "security clearance", "us citizen only",
    "u.s. citizen only", "no sponsorship", "will not sponsor",
    "ts/sci",
]

_SOFT_EXCLUDE_KEYWORDS = [
    "security", "compliance", "privacy", "risk", "finance",
    "payments", "ads auction", "infrastructure", "platform operations",
]

_HIGH_SIGNAL_DOMAIN_KEYWORDS = [
    "search", "discovery", "recommendation", "personalization",
    "ranking", "relevance", "query understanding", "semantic search",
    "hybrid search", "product discovery", "shopping",
    "e-commerce", "ecommerce", "marketplace", "catalog",
]

_MEDIUM_SIGNAL_DOMAIN_KEYWORDS = [
    "ai", "ml", "machine learning", "llm", "generative ai",
    "nlp", "conversational", "chatbot", "assistant", "automation",
]


def _domain_score(text: str) -> int:
    high = sum(1 for kw in _HIGH_SIGNAL_DOMAIN_KEYWORDS if kw in text)
    medium = sum(1 for kw in _MEDIUM_SIGNAL_DOMAIN_KEYWORDS if kw in text)
    return high * 2 + medium


def rule_based_prefilter(job: "RawJob") -> tuple[bool, str]:
    """Decide whether to send a job to Claude for scoring.

    Returns:
      (True, "")        — send to Claude
      (False, reason)   — skip; reason explains why
    """
    title_lower = job.title.lower()
    loc_lower = job.location.lower()
    desc_lower = (job.description_raw or "").lower()
    combined = f"{title_lower} {loc_lower} {desc_lower}"

    # 1. Title exclude → hard skip
    for kw in ["product marketing manager", "program manager", "technical program manager",
               "project manager", "engineering manager", "software engineer",
               "machine learning engineer", "data scientist", "data engineer",
               "designer", "researcher", "analyst", "intern", "new grad",
               "associate product manager"]:
        if kw in title_lower:
            return False, f"title exclude: {kw}"

    # 2. Title not in include list → skip
    if not any(kw in title_lower for kw in [
        "product manager", "sr. product manager", "senior product manager",
        "principal product manager", "staff product manager",
        "lead product manager", "group product manager",
        "head of product", "director of product", "product lead", "vp of product",
    ]):
        return False, "title not in include list"

    # 3. Hard exclude in description or title → skip
    for kw in _HARD_EXCLUDE_KEYWORDS:
        if kw in combined:
            return False, f"hard exclude: {kw}"

    # 4. Location: exclude takes priority over "remote"
    has_exclude_loc = any(kw in loc_lower for kw in _EXCLUDE_LOCATION_KEYWORDS)
    if has_exclude_loc:
        return False, f"location exclude: {loc_lower}"

    # If not remote and no include location match → skip
    if not job.remote:
        has_include_loc = any(kw in loc_lower for kw in _INCLUDE_LOCATION_KEYWORDS)
        if not has_include_loc:
            return False, f"location not in include list: {loc_lower}"

    # 5. Domain score gating
    # Score from title + first 300 chars of description only.
    # Using the full description inflates scores: every AI company JD mentions "ai/ml/llm"
    # even for generic PM roles, making the threshold meaningless.
    title_score = _domain_score(title_lower)
    desc_excerpt = desc_lower[:300]
    score = _domain_score(f"{title_lower} {desc_excerpt}")

    has_soft_exclude = any(kw in f"{title_lower} {desc_excerpt}" for kw in _SOFT_EXCLUDE_KEYWORDS)
    is_high_priority = job.company_priority == "high"
    is_strong_title = any(kw in title_lower for kw in _STRONG_TITLE_KEYWORDS)

    # Base threshold: 3; soft_exclude raises it by 1
    # Jobs with zero title domain signal need a higher bar (title must hint at the domain)
    threshold = 4 if has_soft_exclude else 3
    if title_score == 0:
        threshold += 1  # no domain signal in title → require stronger description match

    if score >= threshold:
        return True, ""
    # One step below threshold is OK if high-priority company or strong title
    if score >= threshold - 1 and (is_high_priority or is_strong_title):
        return True, ""

    return False, f"domain score too low: {score} (title_score={title_score}, threshold={threshold})"
