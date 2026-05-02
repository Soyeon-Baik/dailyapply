"""Greenhouse public job board API scraper.

API: https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
Returns all jobs with descriptions in one request.
"""

import logging
from datetime import datetime, timezone

import httpx

from scrapers.common import RawJob, clean_html, compute_days_old, parse_posted_at

logger = logging.getLogger(__name__)

BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"

# Broad pre-filter: skip jobs that clearly aren't PM roles before building RawJob objects.
# is_pm_role() in filters/ does the precise check later; this just cuts noise at scale.
_PM_TITLE_KEYWORDS = [
    "product manager", "product lead", "head of product",
    "vp of product", "director of product", "group product",
]


async def fetch_jobs(company: dict, client: httpx.AsyncClient) -> list[RawJob]:
    slug = company["slugs"].get("greenhouse")
    if not slug:
        return []

    url = BASE_URL.format(slug=slug)
    try:
        response = await client.get(url, params={"content": "true"}, timeout=20)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning("Greenhouse: no board found for %s (%s)", company["name"], slug)
            return []
        logger.error("Greenhouse HTTP error for %s: %s", company["name"], e)
        return []
    except httpx.RequestError as e:
        logger.error("Greenhouse request error for %s: %s", company["name"], e)
        return []

    data = response.json()
    jobs = data.get("jobs", [])
    results: list[RawJob] = []

    for job in jobs:
        title = job.get("title", "")
        if not any(kw in title.lower() for kw in _PM_TITLE_KEYWORDS):
            continue
        job_id = str(job.get("id", ""))
        location_data = job.get("location", {})
        location = location_data.get("name", "") if isinstance(location_data, dict) else str(location_data)
        job_url = job.get("absolute_url", "")

        content = job.get("content", "") or ""
        description_html = content
        description_raw = clean_html(content)

        posted_at = parse_posted_at(job.get("updated_at"), "greenhouse")
        days_old = compute_days_old(posted_at)

        remote = _is_remote(location)

        results.append(RawJob(
            id=f"gh_{slug}_{job_id}",
            platform="greenhouse",
            company=company["name"],
            company_priority=company.get("priority", "medium"),
            title=title,
            location=location,
            remote=remote,
            url=job_url,
            description_raw=description_raw,
            description_html=description_html,
            posted_at=posted_at,
            scraped_at=datetime.now(timezone.utc),
            days_old=days_old,
        ))

    logger.info("Greenhouse: fetched %d jobs for %s", len(results), company["name"])
    return results


def _is_remote(location: str) -> bool:
    loc = location.lower()
    return any(kw in loc for kw in ["remote", "anywhere", "work from home"])
