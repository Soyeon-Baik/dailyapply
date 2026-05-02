"""Claude API scorer using tool_use for structured output.

Scores jobs in parallel (semaphore 5) using AsyncAnthropic.
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone

import anthropic

from scrapers.common import RawJob
from scoring.schemas import ScoreBreakdown, ScoredJob
from scoring.prompts import build_system_prompt, build_user_message

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1500

SCORE_TOOL = {
    "name": "score_job",
    "description": "Score a PM job posting against the candidate resume and return a structured assessment.",
    "input_schema": {
        "type": "object",
        "required": [
            "fit_score",
            "score_breakdown",
            "score_rationale",
            "recommendation",
            "recommendation_reason",
            "sponsorship_status",
            "location_fit",
            "seniority_level",
            "resume_keywords",
            "suggested_summary",
            "top_bullets",
        ],
        "properties": {
            "fit_score": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "Overall fit score (sum of score_breakdown fields)",
            },
            "score_breakdown": {
                "type": "object",
                "required": [
                    "requirements_match",
                    "domain_alignment",
                    "pm_archetype_fit",
                    "evidence_strength",
                    "seniority_fit",
                    "nice_to_have_bonus",
                ],
                "properties": {
                    "requirements_match": {"type": "integer", "minimum": 0, "maximum": 25},
                    "domain_alignment": {"type": "integer", "minimum": 0, "maximum": 25},
                    "pm_archetype_fit": {"type": "integer", "minimum": 0, "maximum": 20},
                    "evidence_strength": {"type": "integer", "minimum": 0, "maximum": 15},
                    "seniority_fit": {"type": "integer", "minimum": 0, "maximum": 10},
                    "nice_to_have_bonus": {"type": "integer", "minimum": 0, "maximum": 5},
                },
            },
            "score_rationale": {
                "type": "string",
                "description": "2-3 sentences explaining the score",
            },
            "recommendation": {
                "type": "string",
                "enum": ["Apply", "Maybe", "Skip"],
            },
            "recommendation_reason": {
                "type": "string",
                "description": "One-line reason for the recommendation",
            },
            "sponsorship_status": {
                "type": "string",
                "enum": ["does_sponsor", "unknown", "does_not_sponsor"],
            },
            "location_fit": {
                "type": "string",
                "enum": ["exact", "remote", "mismatch"],
            },
            "seniority_level": {
                "type": "string",
                "enum": ["too_junior", "target", "stretch", "too_senior", "unclear"],
                "description": "How the role level compares to candidate's target seniority",
            },
            "resume_keywords": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
                "maxItems": 8,
                "description": "Keywords to add or emphasize in resume for this role",
            },
            "suggested_summary": {
                "type": "string",
                "description": "2-sentence tailored resume summary for this role",
            },
            "top_bullets": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 3,
                "description": "Top 3 existing resume bullets to lead with for this role",
            },
            "gap_handling": {
                "type": "string",
                "description": "How to honestly address the main skill gap (optional)",
            },
        },
    },
}


def parse_json_response(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"```json|```", "", content).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        if start != -1 and end != -1:
            return json.loads(content[start:end + 1])
        raise


async def score_job(
    job: RawJob,
    resume: dict,
    company_note: str,
    run_id: str,
    location_fit: str,
) -> ScoredJob:
    """Score a single job with Claude. Returns a ScoredJob."""
    client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    system = build_system_prompt(resume)
    user_message = build_user_message(job, company_note)

    response = await client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        tools=[SCORE_TOOL],
        tool_choice={"type": "tool", "name": "score_job"},
        messages=[{"role": "user", "content": user_message}],
    )

    tool_block = response.content[0]
    if tool_block.type != "tool_use":
        raise ValueError(f"Expected tool_use block, got: {tool_block.type}")

    tool_input = tool_block.input
    breakdown = ScoreBreakdown(**tool_input["score_breakdown"])

    company_slug = re.sub(r"[^a-z0-9]", "-", job.company.lower())
    source_id = job.id.split("_")[-1] if "_" in job.id else job.id
    job_id = f"{job.platform}:{company_slug}:{source_id}"

    return ScoredJob(
        id=job_id,
        platform=job.platform,
        company=job.company,
        company_priority=job.company_priority,
        title=job.title,
        location=job.location,
        remote=job.remote,
        url=job.url,
        posted_at=job.posted_at.isoformat() if job.posted_at else None,
        days_old=job.days_old,
        scraped_at=job.scraped_at.isoformat(),
        fit_score=tool_input["fit_score"],
        score_breakdown=breakdown,
        score_rationale=tool_input["score_rationale"],
        recommendation=tool_input["recommendation"],
        recommendation_reason=tool_input["recommendation_reason"],
        sponsorship_status=tool_input["sponsorship_status"],
        location_fit=location_fit,
        seniority_level=tool_input["seniority_level"],
        hard_filter=job.hard_filtered,
        hard_filter_reason=job.hard_filter_reason,
        resume_keywords=tool_input["resume_keywords"],
        suggested_summary=tool_input["suggested_summary"],
        top_bullets=tool_input["top_bullets"],
        gap_handling=tool_input.get("gap_handling"),
        run_id=run_id,
        scoring_status="scored",
    )


async def score_all(
    jobs: list[RawJob],
    resume: dict,
    companies_lookup: dict,
    location_fits: dict,
) -> list[ScoredJob]:
    """Score all jobs in parallel with semaphore=5."""
    sem = asyncio.Semaphore(5)
    run_id = datetime.now(timezone.utc).isoformat()

    async def _bounded(job: RawJob) -> ScoredJob:
        async with sem:
            company_note = companies_lookup.get(job.company, {}).get("note", "")
            loc_fit = location_fits.get(job.id, "mismatch")
            return await score_job(job, resume, company_note, run_id, loc_fit)

    results = await asyncio.gather(*[_bounded(j) for j in jobs], return_exceptions=True)

    scored: list[ScoredJob] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            logger.error("score_job failed for %s @ %s: %s", jobs[i].title, jobs[i].company, r)
        else:
            logger.info(
                "[%d/%d] Scored %s @ %s → %d (%s)",
                len(scored) + 1, len(jobs), r.title, r.company,
                r.fit_score, r.recommendation,
            )
            scored.append(r)

    return scored
