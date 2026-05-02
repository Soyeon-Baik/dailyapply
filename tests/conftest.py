"""Shared fixtures for all test modules."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scrapers.common import RawJob

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def greenhouse_response():
    return json.loads((FIXTURES / "greenhouse_response.json").read_text())


@pytest.fixture
def lever_response():
    return json.loads((FIXTURES / "lever_response.json").read_text())


@pytest.fixture
def sample_company_greenhouse():
    return {
        "name": "TestCo",
        "priority": "high",
        "slugs": {"greenhouse": "testco", "lever": None, "ashby": None, "workable": None},
        "domains": ["search", "ai"],
        "note": "Test company for unit tests",
    }


@pytest.fixture
def sample_company_lever():
    return {
        "name": "TestCo",
        "priority": "medium",
        "slugs": {"greenhouse": None, "lever": "testco", "ashby": None, "workable": None},
        "domains": ["growth"],
        "note": "Test company for unit tests",
    }


@pytest.fixture
def sample_raw_job():
    return RawJob(
        id="gh_testco_12345",
        platform="greenhouse",
        company="TestCo",
        company_priority="high",
        title="Senior Product Manager, Search",
        location="San Francisco, CA",
        remote=False,
        url="https://boards.greenhouse.io/testco/jobs/12345",
        description_raw="We are looking for a Senior PM. We sponsor H-1B visas. 5+ years PM experience required.",
        posted_at=datetime(2026, 4, 29, tzinfo=timezone.utc),
        scraped_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        days_old=2.0,
    )


@pytest.fixture
def sample_raw_job_hard_filtered():
    return RawJob(
        id="gh_testco_99999",
        platform="greenhouse",
        company="TestCo",
        company_priority="low",
        title="Senior Product Manager",
        location="Seattle, WA",
        remote=False,
        url="https://example.com/job/99999",
        description_raw="This role requires US citizen only and active security clearance.",
        posted_at=datetime(2026, 4, 28, tzinfo=timezone.utc),
        scraped_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        days_old=3.0,
        hard_filtered=True,
        hard_filter_reason="us citizen only",
    )
