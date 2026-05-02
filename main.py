"""DailyApply pipeline orchestrator.

Execution order:
  1. Load config (companies, blocked list, resume)
  2. Scrape all platforms concurrently
  3. Filter pipeline (blocked → PM title → location → hard filter)
  4. Score with Claude API
  5. Publish to docs/jobs.json (merge with existing, 7-day retention)
  6. Write run log
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

from filters.hard_filters import apply_hard_filters
from filters.location_filter import compute_location_fit, passes_location_filter
from filters.role_filter import is_pm_role, should_score
from scrapers.common import RawJob
from scrapers import greenhouse, lever, ashby, workable
from scoring.scorer import score_all
from scoring.schemas import ScoredJob

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

ROOT = Path(__file__).parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"

SCRAPER_MAP = {
    "greenhouse": greenhouse.fetch_jobs,
    "lever": lever.fetch_jobs,
    "ashby": ashby.fetch_jobs,
    "workable": workable.fetch_jobs,
}


# ── Config loading ────────────────────────────────────────────────────────────

def load_json(path: Path) -> dict | list:
    with open(path) as f:
        return json.load(f)


def build_company_lookup(companies: list[dict]) -> dict[str, dict]:
    return {c["name"]: c for c in companies}


def build_slug_lookups(companies: list[dict]) -> tuple[set[str], dict[str, str], dict[str, str]]:
    """Derive blocked slugs, priority map, and target_status map from companies.json.

    Returns:
      blocked_slugs      — slugs to skip entirely (status: blocked)
      slug_priority      — {slug: "high" | "medium" | "low"}
      slug_target_status — {slug: "primary" | "watchlist" | ...}
    """
    blocked_slugs: set[str] = set()
    slug_priority: dict[str, str] = {}
    slug_target_status: dict[str, str] = {}

    for company in companies:
        is_blocked = company.get("status") == "blocked"
        priority = "high" if company.get("target_status") == "primary" else company.get("priority", "low")
        t_status = company.get("target_status", "watchlist")

        for ats_entry in company.get("ats", []):
            slug = ats_entry.get("slug")
            if not slug:
                continue
            if is_blocked:
                blocked_slugs.add(slug.lower())
            else:
                slug_priority[slug.lower()] = priority
                slug_target_status[slug.lower()] = t_status

    return blocked_slugs, slug_priority, slug_target_status


def _slug_company_dict(slug: str, platform: str, priority: str) -> dict:
    """Build a minimal scraper-compatible dict for a slug from ats_slugs.json."""
    return {
        "name": slug,
        "priority": priority,
        "slugs": {
            "greenhouse": slug if platform == "greenhouse" else None,
            "lever":      slug if platform == "lever"      else None,
            "ashby":      slug if platform == "ashby"      else None,
            "workable":   None,
        },
        "domains": [],
        "note": "",
    }


# ── Scraping ──────────────────────────────────────────────────────────────────

async def scrape_all(
    companies: list[dict],
    blocked_extra: set[str],
    ats_slugs: dict[str, list[str]],
) -> list[RawJob]:
    blocked_slugs, slug_priority, _slug_target_status = build_slug_lookups(companies)
    all_blocked = blocked_slugs | blocked_extra

    jobs: list[RawJob] = []
    seen_ids: set[str] = set()
    sem = asyncio.Semaphore(20)

    async def _bounded(coro):
        async with sem:
            return await coro

    async with httpx.AsyncClient(
        headers={"User-Agent": "DailyApply/1.0 (job aggregator; contact via GitHub)"},
        timeout=30,
    ) as client:
        tasks = []
        for platform, slugs in ats_slugs.items():
            if platform not in SCRAPER_MAP:
                continue
            for slug in slugs:
                if slug.lower() in all_blocked:
                    logger.debug("Skipping blocked slug: %s (%s)", slug, platform)
                    continue
                priority = slug_priority.get(slug.lower(), "low")
                company_dict = _slug_company_dict(slug, platform, priority)
                tasks.append(_bounded(SCRAPER_MAP[platform](company_dict, client)))

        logger.info("Launching %d scraper tasks (semaphore=20) across %d platforms", len(tasks), len(ats_slugs))
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            logger.error("Scraper raised exception: %s", result)
            continue
        for job in result:
            if job.id not in seen_ids:
                seen_ids.add(job.id)
                jobs.append(job)

    logger.info("Scraped %d unique jobs across all platforms", len(jobs))
    return jobs


# ── Filter pipeline ───────────────────────────────────────────────────────────

def run_filter_pipeline(
    jobs: list[RawJob],
    slug_priority: dict[str, str],
    slug_target_status: dict[str, str],
) -> tuple[list[RawJob], dict[str, str]]:
    """
    Returns:
      scoreable     — jobs that pass all filters and should be sent to Claude
      location_fits — {job.id: location_fit_value}
    """
    skipped: dict[str, int] = {
        "hard_exclude": 0, "exclude_title": 0,
        "location_exclude": 0, "location_not_us": 0, "low_domain_score": 0,
    }
    scoreable: list[RawJob] = []
    location_fits: dict[str, str] = {}

    for job in jobs:
        location_fits[job.id] = compute_location_fit(job.location, job.remote)
        priority = slug_priority.get(job.company.lower(), job.company_priority)
        t_status = slug_target_status.get(job.company.lower(), "watchlist")
        ok, reason = should_score(job, company_priority=priority, target_status=t_status)
        if ok:
            scoreable.append(job)
        else:
            skipped[reason] = skipped.get(reason, 0) + 1

    logger.info(
        "Filter pipeline: %d scoreable from %d raw — skipped: %s",
        len(scoreable), len(jobs), skipped,
    )
    return scoreable, location_fits


# ── Publishing ────────────────────────────────────────────────────────────────

def publish(scored_jobs: list[ScoredJob], output_path: Path, retention_days: int = 7):
    """Merge new scored jobs with existing docs/jobs.json, keep 7-day window."""
    existing: dict[str, dict] = {}

    if output_path.exists():
        try:
            for job in json.loads(output_path.read_text()):
                existing[job["id"]] = job
        except Exception as e:
            logger.warning("Could not read existing jobs.json: %s", e)

    for job in scored_jobs:
        existing[job.id] = job.model_dump()

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    kept = []
    for job in existing.values():
        posted = job.get("posted_at")
        if posted is None:
            kept.append(job)
            continue
        try:
            dt = datetime.fromisoformat(posted)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt > cutoff:
                kept.append(job)
        except ValueError:
            kept.append(job)

    kept.sort(key=lambda j: j.get("fit_score", 0), reverse=True)
    output_path.write_text(json.dumps(kept, indent=2, ensure_ascii=False))
    logger.info("Published %d jobs to %s", len(kept), output_path)


def write_run_log(
    raw_count: int,
    filtered_count: int,
    hard_filtered_count: int,
    scored_count: int,
):
    log_path = DATA / "run_log.json"
    try:
        entries = json.loads(log_path.read_text()) if log_path.exists() else []
    except Exception:
        entries = []

    entries.append({
        "run_at": datetime.now(timezone.utc).isoformat(),
        "raw_jobs": raw_count,
        "pm_location_matches": filtered_count,
        "hard_filtered": hard_filtered_count,
        "scored": scored_count,
    })
    entries = entries[-30:]  # keep last 30 runs
    log_path.write_text(json.dumps(entries, indent=2))


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.error("ANTHROPIC_API_KEY not set. Run: cp .env.example .env && fill it in.")
        sys.exit(1)

    companies: list[dict] = load_json(DATA / "companies.json")
    blocked_path = DATA / "blocked_companies.json"
    blocked_raw: list[str] = load_json(blocked_path) if blocked_path.exists() else []
    blocked_extra: set[str] = {c.lower() for c in blocked_raw}
    resume: dict = load_json(DATA / "resume.json")
    company_lookup = build_company_lookup(companies)
    ats_slugs: dict = load_json(DATA / "ats_slugs.json")

    # 1. Scrape
    logger.info("=== STEP 1: Scraping ===")
    raw_jobs = await scrape_all(companies, blocked_extra, ats_slugs)

    # 2. Filter
    logger.info("=== STEP 2: Filtering ===")
    _blocked, slug_priority, slug_target_status = build_slug_lookups(companies)
    scoreable, location_fits = run_filter_pipeline(raw_jobs, slug_priority, slug_target_status)

    if not scoreable:
        logger.info("No scoreable jobs found. Exiting without Claude API calls.")
        write_run_log(len(raw_jobs), 0, 0, 0)
        return

    # 3. Score
    logger.info("=== STEP 3: Scoring %d jobs with Claude ===", len(scoreable))
    scored = await score_all(scoreable, resume, company_lookup, location_fits)

    # 4. Publish
    logger.info("=== STEP 4: Publishing ===")
    DOCS.mkdir(exist_ok=True)
    publish(scored, DOCS / "jobs.json")

    # 5. Run log
    write_run_log(len(raw_jobs), len(scoreable), 0, len(scored))

    logger.info("=== DONE: %d jobs scored and published ===", len(scored))


if __name__ == "__main__":
    asyncio.run(main())
