"""Workable public job board API scraper.

List API: https://apply.workable.com/api/v3/accounts/{slug}/jobs
Detail API: https://apply.workable.com/api/v3/accounts/{slug}/jobs/{shortcode}

The list endpoint returns minimal data — a second request per job fetches the full description.
Detail requests are batched with asyncio.gather, capped at 5 concurrent requests.
"""

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from scrapers.common import RawJob, clean_html, compute_days_old, parse_posted_at

logger = logging.getLogger(__name__)

LIST_URL = "https://apply.workable.com/api/v3/accounts/{slug}/jobs"
DETAIL_URL = "https://apply.workable.com/api/v3/accounts/{slug}/jobs/{shortcode}"
CONCURRENCY_LIMIT = 5


async def fetch_jobs(company: dict, client: httpx.AsyncClient) -> list[RawJob]:
    slug = company["slugs"].get("workable")
    if not slug:
        return []

    # Fetch job list
    try:
        response = await client.get(LIST_URL.format(slug=slug), timeout=20)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning("Workable: no board found for %s (%s)", company["name"], slug)
            return []
        logger.error("Workable HTTP error for %s: %s", company["name"], e)
        return []
    except httpx.RequestError as e:
        logger.error("Workable request error for %s: %s", company["name"], e)
        return []

    data = response.json()
    job_stubs = data.get("results", [])

    # Fetch details with concurrency cap
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

    async def fetch_detail(stub: dict) -> RawJob | None:
        shortcode = stub.get("shortcode", "")
        async with semaphore:
            try:
                detail_resp = await client.get(
                    DETAIL_URL.format(slug=slug, shortcode=shortcode),
                    timeout=20,
                )
                detail_resp.raise_for_status()
                detail = detail_resp.json()
            except Exception as e:
                logger.warning("Workable: failed to fetch detail for %s/%s: %s", slug, shortcode, e)
                detail = stub

        title = detail.get("title", stub.get("title", ""))
        location_city = detail.get("location", {}).get("city", "") if isinstance(detail.get("location"), dict) else ""
        location_country = detail.get("location", {}).get("country", "") if isinstance(detail.get("location"), dict) else ""
        location = ", ".join(filter(None, [location_city, location_country]))
        if not location:
            location = stub.get("location", "")

        job_url = f"https://apply.workable.com/{slug}/j/{shortcode}/"

        description_html = detail.get("description", "") or detail.get("fullDescription", "") or ""
        description_raw = clean_html(description_html)

        posted_at = parse_posted_at(detail.get("published") or detail.get("created"), "workable")
        days_old = compute_days_old(posted_at)

        is_remote = detail.get("remote", False) or _is_remote(location)

        return RawJob(
            id=f"wk_{slug}_{shortcode}",
            platform="workable",
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
        )

    tasks = [fetch_detail(stub) for stub in job_stubs]
    detail_results = await asyncio.gather(*tasks, return_exceptions=True)

    results: list[RawJob] = []
    for r in detail_results:
        if isinstance(r, RawJob):
            results.append(r)
        elif isinstance(r, Exception):
            logger.warning("Workable: detail fetch exception: %s", r)

    logger.info("Workable: fetched %d jobs for %s", len(results), company["name"])
    return results


def _is_remote(location: str) -> bool:
    loc = location.lower()
    return any(kw in loc for kw in ["remote", "anywhere", "work from home"])
