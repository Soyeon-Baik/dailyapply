"""Location filter: Seattle/Bellevue, CA, NY, Remote US."""

from typing import Literal

TARGET_EXACT_KEYWORDS = [
    "seattle",
    "bellevue",
    "redmond",
    "kirkland",
    "san francisco",
    "sf",
    "bay area",
    "silicon valley",
    "san jose",
    "palo alto",
    "mountain view",
    "menlo park",
    "new york",
    "nyc",
    "manhattan",
    "brooklyn",
    "california",
    ", ca",
    ", ny",
    "los angeles",
    ", la",
    "santa monica",
]

TARGET_REMOTE_KEYWORDS = [
    "remote",
    "anywhere",
    "work from home",
    "distributed",
    "wfh",
]


def compute_location_fit(location: str, remote: bool) -> Literal["exact", "remote", "mismatch"]:
    loc = location.lower()

    if remote or any(kw in loc for kw in TARGET_REMOTE_KEYWORDS):
        return "remote"

    if any(kw in loc for kw in TARGET_EXACT_KEYWORDS):
        return "exact"

    return "mismatch"


def passes_location_filter(location: str, remote: bool) -> bool:
    """Return True if the job is in a target location or remote."""
    return compute_location_fit(location, remote) != "mismatch"
