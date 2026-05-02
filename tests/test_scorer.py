"""Unit tests for scorer with a mocked Anthropic client."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from scrapers.common import RawJob
from scoring.schemas import ScoredJob, ScoreBreakdown
from scoring.scorer import score_job
from scoring.prompts import build_system_prompt, build_user_message, format_resume


SAMPLE_RESUME = {
    "name": "Test User",
    "headline": "Senior PM | AI/ML",
    "location": "Seattle, WA",
    "years_of_experience": 7,
    "visa_status": "requires_sponsorship",
    "target_archetypes": ["AI/ML", "Search"],
    "target_seniority": ["Senior PM"],
    "preferred_locations": ["Seattle", "Remote US"],
    "skills": ["SQL", "A/B Testing", "Machine Learning"],
    "experience": [
        {
            "title": "Senior Product Manager",
            "company": "TestCo",
            "dates": "2022 – Present",
            "domain": "search",
            "bullets": ["Led search platform with 10M MAU, +23% CTR"],
        }
    ],
    "education": [{"degree": "MS Analytics", "school": "TestU", "year": "2018"}],
    "key_achievements": ["10M+ MAU search platform"],
}

SAMPLE_TOOL_RESPONSE = {
    "fit_score": 78,
    "score_breakdown": {
        "requirements_match": 20,
        "domain_alignment": 22,
        "pm_archetype_fit": 15,
        "evidence_strength": 12,
        "seniority_fit": 7,
        "nice_to_have_bonus": 2,
    },
    "score_rationale": "Good fit. Strong search domain match.",
    "recommendation": "Apply",
    "recommendation_reason": "Strong domain match; should apply.",
    "sponsorship_status": "does_sponsor",
    "location_fit": "exact",
    "seniority_level": "target",
    "resume_keywords": ["LLM", "search", "personalization"],
    "suggested_summary": "Senior PM with AI/ML background.",
    "top_bullets": ["Led search platform with 10M MAU, +23% CTR"],
    "gap_handling": None,
}


def make_mock_response(tool_input: dict):
    """Build a mock Anthropic response object."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = tool_input

    response = MagicMock()
    response.content = [tool_block]
    return response


@patch("scoring.scorer.anthropic.Anthropic")
def test_score_job_returns_scored_job(mock_anthropic_cls, sample_raw_job):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = make_mock_response(SAMPLE_TOOL_RESPONSE)

    result = score_job(
        job=sample_raw_job,
        resume=SAMPLE_RESUME,
        company_note="Test company",
        run_id="2026-05-01T00:00:00",
        location_fit="exact",
    )

    assert isinstance(result, ScoredJob)
    assert result.fit_score == 78
    assert result.recommendation == "Apply"
    assert result.id == sample_raw_job.id


@patch("scoring.scorer.anthropic.Anthropic")
def test_score_job_passes_tool_choice(mock_anthropic_cls, sample_raw_job):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = make_mock_response(SAMPLE_TOOL_RESPONSE)

    score_job(sample_raw_job, SAMPLE_RESUME, "", "run1", "exact")

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["tool_choice"] == {"type": "tool", "name": "score_job"}
    assert call_kwargs["model"] == "claude-sonnet-4-6"


@patch("scoring.scorer.anthropic.Anthropic")
def test_score_job_system_has_cache_control(mock_anthropic_cls, sample_raw_job):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = make_mock_response(SAMPLE_TOOL_RESPONSE)

    score_job(sample_raw_job, SAMPLE_RESUME, "", "run1", "exact")

    call_kwargs = mock_client.messages.create.call_args.kwargs
    system = call_kwargs["system"]
    assert isinstance(system, list)
    assert system[0]["cache_control"] == {"type": "ephemeral"}


@patch("scoring.scorer.anthropic.Anthropic")
def test_score_job_uses_location_fit_argument(mock_anthropic_cls, sample_raw_job):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = make_mock_response(SAMPLE_TOOL_RESPONSE)

    result = score_job(sample_raw_job, SAMPLE_RESUME, "", "run1", location_fit="remote")
    assert result.location_fit == "remote"


@patch("scoring.scorer.anthropic.Anthropic")
def test_score_job_preserves_hard_filter_fields(mock_anthropic_cls, sample_raw_job_hard_filtered):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = make_mock_response(SAMPLE_TOOL_RESPONSE)

    result = score_job(sample_raw_job_hard_filtered, SAMPLE_RESUME, "", "run1", "exact")
    assert result.hard_filter is True
    assert result.hard_filter_reason is not None


# ── prompts.py ────────────────────────────────────────────────────────────────

def test_build_system_prompt_has_cache_control():
    blocks = build_system_prompt(SAMPLE_RESUME)
    assert len(blocks) == 1
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert blocks[0]["type"] == "text"


def test_build_system_prompt_includes_resume_content():
    blocks = build_system_prompt(SAMPLE_RESUME)
    text = blocks[0]["text"]
    assert "Test User" in text
    assert "Senior PM" in text
    assert "10M MAU" in text


def test_build_user_message_truncates_long_description(sample_raw_job):
    long_job = sample_raw_job.model_copy(update={"description_raw": "x" * 10000})
    msg = build_user_message(long_job, "note")
    assert len(msg) < 8000  # should be truncated


def test_format_resume_includes_all_sections():
    text = format_resume(SAMPLE_RESUME)
    assert "CANDIDATE:" in text
    assert "SKILLS:" in text
    assert "EXPERIENCE:" in text
    assert "KEY ACHIEVEMENTS:" in text
