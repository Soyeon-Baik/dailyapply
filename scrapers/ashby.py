"""Ashby public job board API scraper.

API: https://api.ashbyhq.com/posting-api/job-board/{slug}
Returns all jobs with descriptions in one request.
"""

import logging
from datetime import datetime, timezone

import httpx

from scrapers.common import RawJob, clean_html, compute_days_old, parse_posted_at

logger = logging.getLogger(__name__)

BASE_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"

_PM_INCLUDE_TITLE = [
    "product manager", "sr. product manager", "sr product manager",
    "senior product manager", "staff product manager",
    "principal product manager", "lead product manager",
    "group product manager", "product lead",
]
_PM_EXCLUDE_TITLE = [
    "head of product", "vp of product", "director of product",
    "director, product", "vp, product", "vice president product",
]


async def fetch_jobs(company: dict, client: httpx.AsyncClient) -> list[RawJob]:
    slug = company["slugs"].get("ashby")
    if not slug:
        return []

    url = BASE_URL.format(slug=slug)
    try:
        response = await client.get(url, params={"includeCompensation": "false"}, timeout=20)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (404, 422):
            logger.warning("Ashby: no board found for %s (%s)", company["name"], slug)
            return []
        logger.error("Ashby HTTP error for %s: %s", company["name"], e)
        return []
    except httpx.RequestError as e:
        logger.error("Ashby request error for %s: %s", company["name"], e)
        return []

    data = response.json()
    jobs = data.get("jobPostings", [])
    results: list[RawJob] = []

    for job in jobs:
        if not isinstance(job, dict):
            logger.warning("Ashby: unexpected non-dict job entry for %s: %r", slug, job)
            continue
        title = job.get("title", "")
        title_lower = title.lower()
        if not any(kw in title_lower for kw in _PM_INCLUDE_TITLE):
            continue
        if any(kw in title_lower for kw in _PM_EXCLUDE_TITLE):
            continue
        job_id = job.get("id", "")

        # Ashby location can be a list or string
        location_data = job.get("location", "") or ""
        if isinstance(location_data, list):
            location = ", ".join(location_data)
        else:
            location = str(location_data)

        job_url = job.get("jobUrl", "") or job.get("applyUrl", "")

        # Description is in descriptionHtml or description field
        description_html = job.get("descriptionHtml", "") or job.get("description", "") or ""
        description_raw = clean_html(description_html)

        posted_at = parse_posted_at(job.get("publishedDate") or job.get("createdAt"), "ashby")
        days_old = compute_days_old(posted_at)

        is_remote = job.get("isRemote", False) or _is_remote(location)

        results.append(RawJob(
            id=f"ab_{slug}_{job_id}",
            platform="ashby",
            company=company["name"],
            company_priority=company.get("priority", "medium"),
            title=title,
            location=location,
            remote=is_remote,
            url=job_url,
            description_raw=description_raw,
            description_html=description_html,
            posted_at=posted_at,
            scraped_at=datetime.now(timezone.utc),
            days_old=days_old,
        ))

    logger.info("Ashby: fetched %d jobs for %s", len(results), company["name"])
    return results


def _is_remote(location: str) -> bool:
    loc = location.lower()
    return any(kw in loc for kw in ["remote", "anywhere", "work from home"])
