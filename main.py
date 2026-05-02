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
from filters.role_filter import is_pm_role
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


def build_slug_lookups(companies: list[dict]) -> tuple[set[str], dict[str, str]]:
    """Derive blocked slugs and priority map from companies.json metadata.

    Returns:
      blocked_slugs  — slugs to skip entirely (status: blocked)
      slug_priority  — {slug: "high" | "medium" | "low"}
    """
    blocked_slugs: set[str] = set()
    slug_priority: dict[str, str] = {}

    for company in companies:
        is_blocked = company.get("status") == "blocked"
        priority = "high" if company.get("target_status") == "primary" else company.get("priority", "low")

        for ats_entry in company.get("ats", []):
            slug = ats_entry.get("slug")
            if not slug:
                continue
            if is_blocked:
                blocked_slugs.add(slug.lower())
            else:
                slug_priority[slug.lower()] = priority

    return blocked_slugs, slug_priority


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
    blocked_slugs, slug_priority = build_slug_lookups(companies)
    all_blocked = blocked_slugs | blocked_extra

    jobs: list[RawJob] = []
    seen_ids: set[str] = set()

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
                tasks.append(SCRAPER_MAP[platform](company_dict, client))

        logger.info("Launching %d scraper tasks across %d platforms", len(tasks), len(ats_slugs))
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
) -> tuple[list[RawJob], list[RawJob], dict[str, str]]:
    """
    Returns:
      scoreable   — jobs that pass all filters
      all_jobs    — full list with hard_filtered flags set (for logging)
      location_fits — {job.id: location_fit_value}
    """
    location_fits: dict[str, str] = {}
    scoreable: list[RawJob] = []
    all_filtered: list[RawJob] = []

    for job in jobs:
        # 1. PM title
        if not is_pm_role(job.title):
            logger.debug("Title filter removed: %s", job.title)
            continue

        # 2. Location
        loc_fit = compute_location_fit(job.location, job.remote)
        location_fits[job.id] = loc_fit
        if not passes_location_filter(job.location, job.remote):
            logger.debug("Location filter removed: %s @ %s", job.title, job.location)
            continue

        # 3. Hard filter
        job = apply_hard_filters(job)
        all_filtered.append(job)

        if not job.hard_filtered:
            scoreable.append(job)
        else:
            logger.info(
                "Hard filtered: %s @ %s (reason: %s)",
                job.title, job.company, job.hard_filter_reason,
            )

    logger.info(
        "Filter pipeline: %d scoreable, %d hard-filtered (from %d PM+location matches)",
        len(scoreable), len(all_filtered) - len(scoreable), len(all_filtered),
    )
    return scoreable, all_filtered, location_fits


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
    scoreable, all_filtered, location_fits = run_filter_pipeline(raw_jobs)

    if not scoreable:
        logger.info("No scoreable jobs found. Exiting without Claude API calls.")
        write_run_log(len(raw_jobs), len(all_filtered), len(all_filtered) - len(scoreable), 0)
        return

    # 3. Score
    logger.info("=== STEP 3: Scoring %d jobs with Claude ===", len(scoreable))
    scored = score_all(scoreable, resume, company_lookup, location_fits)

    # 4. Publish
    logger.info("=== STEP 4: Publishing ===")
    DOCS.mkdir(exist_ok=True)
    publish(scored, DOCS / "jobs.json")

    # 5. Run log
    hard_filtered_count = len(all_filtered) - len(scoreable)
    write_run_log(len(raw_jobs), len(all_filtered), hard_filtered_count, len(scored))

    logger.info("=== DONE: %d jobs scored and published ===", len(scored))


if __name__ == "__main__":
    asyncio.run(main())
