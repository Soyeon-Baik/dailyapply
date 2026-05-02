"""Hard filter: detect visa/clearance blockers in job descriptions.

Two-tier system:
  HARD_REJECT  — marks hard_filtered=True, job is excluded from scoring
  SOFT_CONCERN — sets sponsorship_hint="unlikely" but still sends to Claude for scoring
"""

from scrapers.common import RawJob

HARD_REJECT_PHRASES = [
    "will not sponsor",
    "do not sponsor",
    "does not sponsor",
    "no sponsorship",
    "cannot sponsor",
    "unable to sponsor",
    "us citizen only",
    "u.s. citizen only",
    "united states citizen only",
    "security clearance required",
    "active clearance",
    "secret clearance",
    "top secret",
    "must hold clearance",
    "ts/sci",
]

SOFT_SPONSORSHIP_PHRASES = [
    "must be authorized to work",
    "authorized to work in the united states",
    "employment eligibility",
    "work authorization required",
    "right to work",
]


def apply_hard_filters(job: RawJob) -> RawJob:
    """Check description for hard-reject phrases. Mutates and returns the job."""
    text = (job.description_raw or "").lower()

    for phrase in HARD_REJECT_PHRASES:
        if phrase in text:
            job.hard_filtered = True
            job.hard_filter_reason = phrase
            return job

    return job


def detect_soft_sponsorship_concern(description_raw: str) -> bool:
    """Return True if the description has soft sponsorship-concern language.

    Used by the scorer to set sponsorship_hint; does NOT hard-filter the job.
    """
    text = description_raw.lower()
    return any(phrase in text for phrase in SOFT_SPONSORSHIP_PHRASES)
