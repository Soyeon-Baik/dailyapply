"""PM role title filter.

Conservative include list + strong exclude list.
Seniority is NOT filtered here — Claude scores it as seniority_fit.

Design rationale:
  - \bpm\b is too noisy (Program Manager, Project Manager, Product Marketing Manager all match)
  - "Growth Product Manager" must pass; "Growth Marketing Manager" must not
  - Checking exclude patterns FIRST prevents false positives from loose include patterns
"""

import re

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
    # Exclude takes priority: bail early on obvious non-PM roles
    for pattern in _exclude_re:
        if pattern.search(title):
            return False

    for pattern in _include_re:
        if pattern.search(title):
            return True

    return False
