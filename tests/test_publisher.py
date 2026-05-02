"""Unit tests for the publish() function in main.py."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from main import publish
from scoring.schemas import ScoredJob, ScoreBreakdown


def make_scored_job(job_id="job_1", fit_score=75, days_old=2.0, posted_at_offset_days=-2):
    posted = (datetime.now(timezone.utc) + timedelta(days=posted_at_offset_days)).isoformat()
    return ScoredJob(
        id=job_id,
        platform="greenhouse",
        company="TestCo",
        company_priority="high",
        title="Senior PM",
        location="Seattle, WA",
        remote=False,
        url="https://example.com",
        posted_at=posted,
        days_old=days_old,
        scraped_at=datetime.now(timezone.utc).isoformat(),
        fit_score=fit_score,
        score_breakdown=ScoreBreakdown(
            requirements_match=20, domain_alignment=20, pm_archetype_fit=15,
            evidence_strength=10, seniority_fit=7, nice_to_have_bonus=3,
        ),
        score_rationale="Good fit.",
        recommendation="Apply",
        recommendation_reason="Strong match.",
        sponsorship_status="does_sponsor",
        location_fit="exact",
        seniority_level="target",
        hard_filter=False,
        resume_keywords=["AI", "search"],
        suggested_summary="Senior PM with AI background.",
        top_bullets=["Led search platform with 10M MAU"],
        run_id="2026-05-01T00:00:00",
    )


def test_publish_creates_output_file(tmp_path):
    jobs = [make_scored_job("job_1")]
    output = tmp_path / "jobs.json"
    publish(jobs, output)
    assert output.exists()
    result = json.loads(output.read_text())
    assert len(result) == 1
    assert result[0]["id"] == "job_1"


def test_publish_merges_with_existing(tmp_path):
    output = tmp_path / "jobs.json"
    first_batch = [make_scored_job("job_1", fit_score=80)]
    publish(first_batch, output)

    second_batch = [make_scored_job("job_2", fit_score=60)]
    publish(second_batch, output)

    result = json.loads(output.read_text())
    ids = [j["id"] for j in result]
    assert "job_1" in ids
    assert "job_2" in ids
    assert len(result) == 2


def test_publish_overwrites_same_job(tmp_path):
    output = tmp_path / "jobs.json"
    publish([make_scored_job("job_1", fit_score=50)], output)
    publish([make_scored_job("job_1", fit_score=90)], output)

    result = json.loads(output.read_text())
    assert len(result) == 1
    assert result[0]["fit_score"] == 90


def test_publish_drops_old_jobs(tmp_path):
    output = tmp_path / "jobs.json"
    old_job = make_scored_job("old_job", posted_at_offset_days=-10)
    publish([old_job], output, retention_days=7)

    result = json.loads(output.read_text())
    assert len(result) == 0


def test_publish_keeps_recent_jobs(tmp_path):
    output = tmp_path / "jobs.json"
    recent = make_scored_job("recent_job", posted_at_offset_days=-3)
    publish([recent], output, retention_days=7)

    result = json.loads(output.read_text())
    assert len(result) == 1


def test_publish_sorts_by_fit_score_desc(tmp_path):
    output = tmp_path / "jobs.json"
    jobs = [
        make_scored_job("job_low", fit_score=30),
        make_scored_job("job_high", fit_score=90),
        make_scored_job("job_mid", fit_score=60),
    ]
    publish(jobs, output)

    result = json.loads(output.read_text())
    scores = [j["fit_score"] for j in result]
    assert scores == sorted(scores, reverse=True)


def test_publish_output_is_valid_json(tmp_path):
    output = tmp_path / "jobs.json"
    jobs = [make_scored_job(f"job_{i}") for i in range(5)]
    publish(jobs, output)
    json.loads(output.read_text())  # should not raise


def test_publish_handles_missing_posted_at(tmp_path):
    output = tmp_path / "jobs.json"
    job = make_scored_job("job_no_date")
    job_dict = job.model_dump()
    job_dict["posted_at"] = None

    # Write directly as if it's pre-existing JSON
    output.write_text(json.dumps([job_dict]))

    # Publish a new job; old one should be kept (no posted_at = never expires)
    new_job = make_scored_job("new_job")
    publish([new_job], output, retention_days=7)
    result = json.loads(output.read_text())
    ids = [j["id"] for j in result]
    assert "job_no_date" in ids
    assert "new_job" in ids
