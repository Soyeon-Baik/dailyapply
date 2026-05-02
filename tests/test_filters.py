"""Unit tests for all filter modules."""

import pytest

from filters.hard_filters import apply_hard_filters, detect_soft_sponsorship_concern
from filters.location_filter import compute_location_fit, passes_location_filter
from filters.role_filter import is_pm_role
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
