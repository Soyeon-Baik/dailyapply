"""Unit tests for all filter modules."""

import pytest

from filters.hard_filters import apply_hard_filters, detect_soft_sponsorship_concern
from filters.location_filter import compute_location_fit, passes_location_filter
from filters.role_filter import is_pm_role, should_score
from scrapers.common import RawJob
from datetime import datetime, timezone


def make_job(description="", title="Senior Product Manager", location="Seattle, WA", remote=False):
    return RawJob(
        id="test_1",
        platform="greenhouse",
        company="TestCo",
        company_priority="medium",
        title=title,
        location=location,
        remote=remote,
        url="https://example.com",
        description_raw=description,
        scraped_at=datetime.now(timezone.utc),
    )


# ── hard_filters ──────────────────────────────────────────────────────────────

class TestHardFilters:
    def test_no_sponsorship_triggers_hard_filter(self):
        job = make_job("We will not sponsor work visas for this position.")
        result = apply_hard_filters(job)
        assert result.hard_filtered is True
        assert result.hard_filter_reason == "will not sponsor"

    def test_does_not_sponsor_phrase(self):
        job = make_job("Our company does not sponsor H-1B applications.")
        result = apply_hard_filters(job)
        assert result.hard_filtered is True

    def test_no_sponsorship_phrase(self):
        job = make_job("No sponsorship available for this role.")
        result = apply_hard_filters(job)
        assert result.hard_filtered is True

    def test_us_citizen_only(self):
        job = make_job("Candidates must be US citizen only to apply.")
        result = apply_hard_filters(job)
        assert result.hard_filtered is True
        assert result.hard_filter_reason == "us citizen only"

    def test_security_clearance_required(self):
        job = make_job("This role requires an active security clearance required.")
        result = apply_hard_filters(job)
        assert result.hard_filtered is True

    def test_ts_sci(self):
        job = make_job("Must hold TS/SCI clearance.")
        result = apply_hard_filters(job)
        assert result.hard_filtered is True

    def test_clean_description_passes(self):
        job = make_job("Great AI/ML PM role. We sponsor H-1B visas for qualified candidates.")
        result = apply_hard_filters(job)
        assert result.hard_filtered is False
        assert result.hard_filter_reason is None

    def test_empty_description_passes(self):
        job = make_job("")
        result = apply_hard_filters(job)
        assert result.hard_filtered is False

    def test_soft_concern_does_not_hard_filter(self):
        job = make_job("Must be authorized to work in the United States.")
        result = apply_hard_filters(job)
        assert result.hard_filtered is False  # soft phrase, not hard reject

    def test_detect_soft_sponsorship_concern_true(self):
        assert detect_soft_sponsorship_concern("Must be authorized to work in the United States.") is True

    def test_detect_soft_sponsorship_concern_false(self):
        assert detect_soft_sponsorship_concern("We are an equal opportunity employer.") is False

    def test_case_insensitive(self):
        job = make_job("US CITIZEN ONLY required for this position.")
        result = apply_hard_filters(job)
        assert result.hard_filtered is True


# ── role_filter ───────────────────────────────────────────────────────────────

class TestRoleFilter:
    def test_senior_product_manager(self):
        assert is_pm_role("Senior Product Manager") is True

    def test_product_manager(self):
        assert is_pm_role("Product Manager") is True

    def test_staff_product_manager(self):
        assert is_pm_role("Staff Product Manager, AI") is True

    def test_principal_product_manager(self):
        assert is_pm_role("Principal Product Manager") is True

    def test_group_product_manager(self):
        assert is_pm_role("Group Product Manager") is True

    def test_lead_product_manager(self):
        assert is_pm_role("Lead Product Manager") is True

    def test_director_of_product(self):
        assert is_pm_role("Director of Product") is True

    def test_head_of_product(self):
        assert is_pm_role("Head of Product") is True

    def test_product_lead(self):
        assert is_pm_role("Product Lead, Growth") is True

    def test_growth_product_manager_passes(self):
        assert is_pm_role("Growth Product Manager") is True

    def test_product_marketing_manager_rejected(self):
        assert is_pm_role("Product Marketing Manager") is False

    def test_program_manager_rejected(self):
        assert is_pm_role("Senior Program Manager") is False

    def test_technical_program_manager_rejected(self):
        assert is_pm_role("Technical Program Manager") is False

    def test_tpm_rejected(self):
        assert is_pm_role("TPM, Infrastructure") is False

    def test_project_manager_rejected(self):
        assert is_pm_role("Project Manager, Operations") is False

    def test_marketing_manager_rejected(self):
        assert is_pm_role("Senior Marketing Manager") is False

    def test_software_engineer_rejected(self):
        assert is_pm_role("Software Engineer") is False

    def test_growth_marketing_rejected(self):
        assert is_pm_role("Growth Marketing Manager") is False

    def test_data_scientist_rejected(self):
        assert is_pm_role("Senior Data Scientist") is False

    def test_sales_rejected(self):
        assert is_pm_role("Sales Manager, Enterprise") is False


# ── location_filter ───────────────────────────────────────────────────────────

class TestLocationFilter:
    def test_seattle_exact(self):
        assert compute_location_fit("Seattle, WA", False) == "exact"

    def test_bellevue_exact(self):
        assert compute_location_fit("Bellevue, WA", False) == "exact"

    def test_san_francisco_exact(self):
        assert compute_location_fit("San Francisco, CA", False) == "exact"

    def test_new_york_exact(self):
        assert compute_location_fit("New York, NY", False) == "exact"

    def test_nyc_exact(self):
        assert compute_location_fit("NYC", False) == "exact"

    def test_california_exact(self):
        assert compute_location_fit("Palo Alto, California", False) == "exact"

    def test_remote_string(self):
        assert compute_location_fit("Remote US", False) == "remote"

    def test_remote_flag(self):
        assert compute_location_fit("Anywhere", True) == "remote"

    def test_remote_flag_overrides_location(self):
        assert compute_location_fit("Austin, TX", True) == "remote"

    def test_austin_mismatch(self):
        assert compute_location_fit("Austin, TX", False) == "mismatch"

    def test_chicago_mismatch(self):
        assert compute_location_fit("Chicago, IL", False) == "mismatch"

    def test_passes_location_filter_exact(self):
        assert passes_location_filter("Seattle, WA", False) is True

    def test_passes_location_filter_remote(self):
        assert passes_location_filter("Remote", False) is True

    def test_passes_location_filter_mismatch(self):
        assert passes_location_filter("Dallas, TX", False) is False


# ── should_score ──────────────────────────────────────────────────────────────

def make_prefilter_job(
    title="Senior Product Manager",
    location="Seattle, WA",
    remote=False,
    description="search discovery recommendation ranking relevance ecommerce marketplace",
    company_priority="medium",
):
    return RawJob(
        id="pf_1",
        platform="greenhouse",
        company="TestCo",
        company_priority=company_priority,
        title=title,
        location=location,
        remote=remote,
        url="https://example.com",
        description_raw=description,
        scraped_at=datetime.now(timezone.utc),
    )


class TestShouldScore:
    # ── Title exclude ────────────────────────────────────────────────────────

    def test_product_marketing_manager_skipped(self):
        job = make_prefilter_job(title="Product Marketing Manager")
        ok, reason = should_score(job)
        assert ok is False
        assert reason == "exclude_title"

    def test_technical_program_manager_skipped(self):
        job = make_prefilter_job(title="Technical Program Manager")
        ok, reason = should_score(job)
        assert ok is False
        assert reason == "exclude_title"

    def test_intern_skipped(self):
        job = make_prefilter_job(title="Product Manager Intern")
        ok, reason = should_score(job)
        assert ok is False

    def test_associate_pm_skipped(self):
        job = make_prefilter_job(title="Associate Product Manager")
        ok, reason = should_score(job)
        assert ok is False

    # ── Location exclude ─────────────────────────────────────────────────────

    def test_india_location_skipped(self):
        job = make_prefilter_job(location="Bangalore, India")
        ok, reason = should_score(job)
        assert ok is False
        assert reason == "location_exclude"

    def test_remote_canada_skipped(self):
        job = make_prefilter_job(location="Remote - Canada", remote=True)
        ok, reason = should_score(job)
        assert ok is False
        assert reason == "location_exclude"

    def test_london_skipped(self):
        job = make_prefilter_job(location="London, UK")
        ok, reason = should_score(job)
        assert ok is False

    def test_non_us_non_remote_skipped(self):
        # Mexico City has no US state abbr, not in exclude list, not remote → location_not_us
        job = make_prefilter_job(location="Mexico City, Mexico", remote=False)
        ok, reason = should_score(job)
        assert ok is False
        assert reason == "location_not_us"

    def test_non_target_city_but_remote_flag_passes(self):
        # remote=True with no exclude → is_remote=True, has_us=True → passes
        job = make_prefilter_job(location="Remote", remote=True)
        ok, _ = should_score(job)
        assert ok is True

    # ── Hard exclude ─────────────────────────────────────────────────────────

    def test_no_sponsorship_in_desc_skipped(self):
        job = make_prefilter_job(description="no sponsorship available search discovery ranking")
        ok, reason = should_score(job)
        assert ok is False
        assert reason == "hard_exclude"

    def test_security_clearance_in_desc_skipped(self):
        job = make_prefilter_job(description="active clearance required search ecommerce")
        ok, reason = should_score(job)
        assert ok is False

    # ── Domain score gating ──────────────────────────────────────────────────

    def test_high_signal_domain_scores(self):
        # "search" + "discovery" + "ranking" = 3 high-signal × 2 = score 6 ≥ threshold 3
        job = make_prefilter_job(description="search discovery ranking")
        ok, _ = should_score(job)
        assert ok is True

    def test_low_domain_score_skipped(self):
        # No domain keywords → score=0; Senior title → senior_domain_match needs score>=2
        job = make_prefilter_job(
            title="Product Manager",
            description="manage stakeholders coordinate releases",
        )
        ok, reason = should_score(job)
        assert ok is False
        assert reason == "low_domain_score"

    def test_medium_signal_ai_ml_counts(self):
        # "ai" + "ml" + "llm" = 3 medium-signal → score=3 ≥ threshold 3
        job = make_prefilter_job(description="ai ml llm based product")
        ok, _ = should_score(job)
        assert ok is True

    def test_soft_exclude_raises_threshold(self):
        # "security" triggers soft_exclude → threshold=4
        # "search"(2) + "discovery"(2) = score=4 ≥ threshold 4 → passes
        job = make_prefilter_job(
            description="search discovery security compliance",
        )
        ok, _ = should_score(job)
        assert ok is True

    def test_soft_exclude_low_score_skipped(self):
        # "security" soft_exclude → threshold=4; "search"=2 only; title="Product Manager" (not senior)
        # score=2 < threshold=4, not senior, not high priority → skip
        job = make_prefilter_job(
            title="Product Manager",
            description="search security compliance",
        )
        ok, reason = should_score(job)
        assert ok is False
        assert reason == "low_domain_score"

    def test_high_priority_company_passes(self):
        # company_priority="high" + domain_score>=3 → target_company
        job = make_prefilter_job(
            title="Product Manager",
            description="search discovery ranking",
            company_priority="high",
        )
        ok, reason = should_score(job, company_priority="high")
        assert ok is True
        assert reason == "target_company"

    def test_senior_with_domain_score_2_passes(self):
        # is_senior=True (title has "senior") + domain_score=2 → senior_domain_match
        job = make_prefilter_job(
            title="Senior Product Manager",
            description="ecommerce product roadmap",
        )
        ok, reason = should_score(job)
        assert ok is True
        assert reason == "senior_domain_match"

    def test_medium_priority_low_score_skipped(self):
        # title="Product Manager" (not senior), score=2 (ecommerce=2), threshold=3 → skip
        job = make_prefilter_job(
            title="Product Manager",
            description="ecommerce product roadmap",
            company_priority="medium",
        )
        ok, reason = should_score(job)
        assert ok is False
