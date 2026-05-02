"""Tests for main.py scraper helpers (V2 refactor)."""

import pytest
from main import build_slug_lookups, _slug_company_dict


# ── build_slug_lookups ────────────────────────────────────────────────────────

def test_build_slug_lookups_blocked_slug():
    companies = [
        {
            "name": "Disney",
            "status": "blocked",
            "ats": [{"type": "greenhouse", "slug": "disney"}],
        }
    ]
    blocked, priority, _ = build_slug_lookups(companies)
    assert "disney" in blocked
    assert "disney" not in priority


def test_build_slug_lookups_high_priority_via_target_status():
    companies = [
        {
            "name": "Anthropic",
            "status": "active",
            "target_status": "primary",
            "ats": [{"type": "greenhouse", "slug": "anthropic"}],
        }
    ]
    blocked, priority, _ = build_slug_lookups(companies)
    assert "anthropic" not in blocked
    assert priority["anthropic"] == "high"


def test_build_slug_lookups_medium_priority():
    companies = [
        {
            "name": "Notion",
            "status": "active",
            "priority": "medium",
            "ats": [{"type": "ashby", "slug": "notion"}],
        }
    ]
    blocked, priority, _ = build_slug_lookups(companies)
    assert priority["notion"] == "medium"


def test_build_slug_lookups_default_low_for_unknown_slug():
    blocked, priority, _ = build_slug_lookups([])
    assert priority.get("unknownco", "low") == "low"


def test_build_slug_lookups_empty_companies():
    blocked, priority, t_status = build_slug_lookups([])
    assert blocked == set()
    assert priority == {}
    assert t_status == {}


def test_build_slug_lookups_multiple_ats_entries():
    companies = [
        {
            "name": "Figma",
            "status": "active",
            "target_status": "primary",
            "ats": [
                {"type": "greenhouse", "slug": "figma"},
                {"type": "lever", "slug": "figma-lever"},
            ],
        }
    ]
    blocked, priority, _ = build_slug_lookups(companies)
    assert priority["figma"] == "high"
    assert priority["figma-lever"] == "high"


def test_build_slug_lookups_blocked_skips_slug_without_slug_key():
    companies = [
        {
            "name": "Ghost",
            "status": "blocked",
            "ats": [{"type": "greenhouse"}],  # no slug key
        }
    ]
    blocked, priority, _ = build_slug_lookups(companies)
    assert len(blocked) == 0


def test_build_slug_lookups_slug_normalized_lowercase():
    companies = [
        {
            "name": "Acme",
            "status": "blocked",
            "ats": [{"type": "greenhouse", "slug": "ACME"}],
        }
    ]
    blocked, _, _t = build_slug_lookups(companies)
    assert "acme" in blocked


# ── _slug_company_dict ────────────────────────────────────────────────────────

def test_slug_company_dict_greenhouse():
    d = _slug_company_dict("anthropic", "greenhouse", "high")
    assert d["name"] == "anthropic"
    assert d["priority"] == "high"
    assert d["slugs"]["greenhouse"] == "anthropic"
    assert d["slugs"]["lever"] is None
    assert d["slugs"]["ashby"] is None


def test_slug_company_dict_lever():
    d = _slug_company_dict("figma", "lever", "medium")
    assert d["slugs"]["lever"] == "figma"
    assert d["slugs"]["greenhouse"] is None


def test_slug_company_dict_ashby():
    d = _slug_company_dict("openai", "ashby", "low")
    assert d["slugs"]["ashby"] == "openai"
    assert d["slugs"]["greenhouse"] is None
    assert d["slugs"]["lever"] is None


def test_slug_company_dict_has_required_scraper_keys():
    d = _slug_company_dict("test", "greenhouse", "low")
    assert "name" in d
    assert "priority" in d
    assert "slugs" in d
    assert "domains" in d
    assert "note" in d
