"""Lever public job board API scraper.

API: https://api.lever.co/v0/postings/{slug}?mode=json
Returns all postings with full description in one request.
Lever uses Unix milliseconds for timestamps.
"""

import logging
from datetime import datetime, timezone

import httpx

from scrapers.common import RawJob, clean_html, compute_days_old, parse_posted_at

logger = logging.getLogger(__name__)

BASE_URL = "https://api.lever.co/v0/postings/{slug}"

_PM_TITLE_KEYWORDS = [
    "product manager", "product lead", "head of product",
    "vp of product", "director of product", "group product",
]


async def fetch_jobs(company: dict, client: httpx.AsyncClient) -> list[RawJob]:
    slug = company["slugs"].get("lever")
    if not slug:
        return []

    url = BASE_URL.format(slug=slug)
    try:
        response = await client.get(url, params={"mode": "json"}, timeout=20)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning("Lever: no board found for %s (%s)", company["name"], slug)
            return []
        logger.error("Lever HTTP error for %s: %s", company["name"], e)
        return []
    except httpx.RequestError as e:
        logger.error("Lever request error for %s: %s", company["name"], e)
        return []

    jobs = response.json()
    if not isinstance(jobs, list):
        logger.error("Lever: unexpected response format for %s", company["name"])
        return []

    results: list[RawJob] = []

    for job in jobs:
        if not isinstance(job, dict):
            logger.warning("Lever: unexpected non-dict job entry for %s: %r", slug, job)
            continue
        title = job.get("text", "")
        if not any(kw in title.lower() for kw in _PM_TITLE_KEYWORDS):
            continue
        job_id = job.get("id", "")
        categories = job.get("categories", {})
        location = categories.get("location", "") or job.get("workplaceType", "")
        job_url = job.get("hostedUrl", "")

        # Lever description is split into sections
        description_parts = []
        description_html_parts = []
        for section in job.get("descriptionBody", {}).get("descriptionBodyParts", []) if "descriptionBody" in job else []:
            html = section.get("content", "")
            description_html_parts.append(html)
            description_parts.append(clean_html(html))

        # Fallback: top-level description field
        if not description_parts:
            desc_html = job.get("description", "") or job.get("descriptionPlain", "") or ""
            description_html_parts = [desc_html]
            description_parts = [clean_html(desc_html)]

        description_raw = " ".join(description_parts)
        description_html = " ".join(description_html_parts)

        # Lever timestamps are Unix ms
        posted_at = parse_posted_at(job.get("createdAt"), "lever")
        days_old = compute_days_old(posted_at)

        commitment = (categories.get("commitment") or "").lower()
        remote = _is_remote(location) or "remote" in commitment

        results.append(RawJob(
            id=f"lv_{slug}_{job_id}",
            platform="lever",
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

    logger.info("Lever: fetched %d jobs for %s", len(results), company["name"])
    return results


def _is_remote(location: str) -> bool:
    loc = location.lower()
    return any(kw in loc for kw in ["remote", "anywhere", "work from home"])
