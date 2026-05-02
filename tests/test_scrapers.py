"""Unit tests for scrapers using respx to mock HTTP."""

import pytest
import respx
import httpx
import pytest_asyncio

from scrapers.greenhouse import fetch_jobs as gh_fetch
from scrapers.lever import fetch_jobs as lv_fetch
from scrapers.common import RawJob


# ── Greenhouse ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@respx.mock
async def test_greenhouse_parses_jobs(greenhouse_response, sample_company_greenhouse):
    slug = sample_company_greenhouse["slugs"]["greenhouse"]
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    respx.get(url).mock(return_value=httpx.Response(200, json=greenhouse_response))

    async with httpx.AsyncClient() as client:
        jobs = await gh_fetch(sample_company_greenhouse, client)

    assert len(jobs) == 2  # "Product Marketing Manager" pre-filtered by PM title check
    assert all(isinstance(j, RawJob) for j in jobs)
    assert all(j.platform == "greenhouse" for j in jobs)
    assert all(j.id.startswith("gh_testco_") for j in jobs)


@pytest.mark.asyncio
@respx.mock
async def test_greenhouse_strips_html(greenhouse_response, sample_company_greenhouse):
    slug = sample_company_greenhouse["slugs"]["greenhouse"]
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    respx.get(url).mock(return_value=httpx.Response(200, json=greenhouse_response))

    async with httpx.AsyncClient() as client:
        jobs = await gh_fetch(sample_company_greenhouse, client)

    assert "<p>" not in jobs[0].description_raw
    assert "Senior PM to lead our Search" in jobs[0].description_raw


@pytest.mark.asyncio
@respx.mock
async def test_greenhouse_returns_empty_on_404(sample_company_greenhouse):
    slug = sample_company_greenhouse["slugs"]["greenhouse"]
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    respx.get(url).mock(return_value=httpx.Response(404))

    async with httpx.AsyncClient() as client:
        jobs = await gh_fetch(sample_company_greenhouse, client)

    assert jobs == []


@pytest.mark.asyncio
@respx.mock
async def test_greenhouse_skips_null_slug(sample_company_greenhouse):
    company = {**sample_company_greenhouse, "slugs": {**sample_company_greenhouse["slugs"], "greenhouse": None}}
    async with httpx.AsyncClient() as client:
        jobs = await gh_fetch(company, client)
    assert jobs == []


@pytest.mark.asyncio
@respx.mock
async def test_greenhouse_company_priority_propagated(greenhouse_response, sample_company_greenhouse):
    slug = sample_company_greenhouse["slugs"]["greenhouse"]
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    respx.get(url).mock(return_value=httpx.Response(200, json=greenhouse_response))

    async with httpx.AsyncClient() as client:
        jobs = await gh_fetch(sample_company_greenhouse, client)

    assert all(j.company_priority == "high" for j in jobs)


# ── Lever ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@respx.mock
async def test_lever_parses_jobs(lever_response, sample_company_lever):
    slug = sample_company_lever["slugs"]["lever"]
    url = f"https://api.lever.co/v0/postings/{slug}"
    respx.get(url).mock(return_value=httpx.Response(200, json=lever_response))

    async with httpx.AsyncClient() as client:
        jobs = await lv_fetch(sample_company_lever, client)

    assert len(jobs) == 1  # "Technical Program Manager" pre-filtered by PM title check
    assert all(j.platform == "lever" for j in jobs)
    assert all(j.id.startswith("lv_testco_") for j in jobs)


@pytest.mark.asyncio
@respx.mock
async def test_lever_converts_unix_ms_timestamp(lever_response, sample_company_lever):
    slug = sample_company_lever["slugs"]["lever"]
    url = f"https://api.lever.co/v0/postings/{slug}"
    respx.get(url).mock(return_value=httpx.Response(200, json=lever_response))

    async with httpx.AsyncClient() as client:
        jobs = await lv_fetch(sample_company_lever, client)

    # First job has createdAt: 1745913600000 (Unix ms)
    job = next(j for j in jobs if "Growth" in j.title)
    assert job.posted_at is not None
    assert job.posted_at.year == 2025  # 1745913600000 ms = April 2025


@pytest.mark.asyncio
@respx.mock
async def test_lever_returns_empty_on_404(sample_company_lever):
    slug = sample_company_lever["slugs"]["lever"]
    url = f"https://api.lever.co/v0/postings/{slug}"
    respx.get(url).mock(return_value=httpx.Response(404))

    async with httpx.AsyncClient() as client:
        jobs = await lv_fetch(sample_company_lever, client)

    assert jobs == []


# ── common.py utilities ───────────────────────────────────────────────────────

def test_clean_html_strips_tags():
    from scrapers.common import clean_html
    result = clean_html("<p>Hello <b>world</b></p>")
    assert "<p>" not in result
    assert "Hello world" in result


def test_clean_html_decodes_entities():
    from scrapers.common import clean_html
    result = clean_html("Search &amp; Discovery")
    assert "&amp;" not in result
    assert "Search & Discovery" in result


def test_clean_html_empty_string():
    from scrapers.common import clean_html
    assert clean_html("") == ""


def test_parse_posted_at_lever_unix_ms():
    from scrapers.common import parse_posted_at
    dt = parse_posted_at(1745913600000, "lever")
    assert dt is not None
    assert dt.year == 2025


def test_parse_posted_at_iso_string():
    from scrapers.common import parse_posted_at
    dt = parse_posted_at("2026-04-29T10:00:00Z", "greenhouse")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 4


def test_parse_posted_at_none():
    from scrapers.common import parse_posted_at
    assert parse_posted_at(None, "greenhouse") is None


def test_compute_days_old():
    from scrapers.common import compute_days_old, parse_posted_at
    # A date 3 days ago
    from datetime import datetime, timedelta, timezone
    posted = datetime.now(timezone.utc) - timedelta(days=3)
    days = compute_days_old(posted)
    assert 2.9 < days < 3.1
