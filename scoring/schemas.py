"""Pydantic schemas for scored job output."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ScoreBreakdown(BaseModel):
    requirements_match: int = Field(ge=0, le=25, description="Stack/requirements vs resume skills")
    domain_alignment: int = Field(ge=0, le=25, description="Domain (AI/Search/etc.) vs target archetypes")
    pm_archetype_fit: int = Field(ge=0, le=20, description="Consumer/Growth/Platform/AI archetype match")
    evidence_strength: int = Field(ge=0, le=15, description="How many resume bullets are provably relevant")
    seniority_fit: int = Field(ge=0, le=10, description="Level match to candidate target seniority")
    nice_to_have_bonus: int = Field(ge=0, le=5, description="Perks, team signals, brand value")


class ScoredJob(BaseModel):
    # Identity (from RawJob)
    id: str
    platform: str
    company: str
    company_priority: Literal["high", "medium", "low"]
    title: str
    location: str
    remote: bool
    url: str
    posted_at: Optional[str] = None   # ISO string
    days_old: Optional[float] = None
    scraped_at: str

    # Fit score
    fit_score: int = Field(ge=0, le=100)
    score_breakdown: ScoreBreakdown
    score_rationale: str  # 2-3 sentences

    # Recommendation
    recommendation: Literal["Apply", "Maybe", "Skip"]
    recommendation_reason: str  # one-line

    # Separate metadata (not part of score)
    sponsorship_status: Literal["does_sponsor", "unknown", "does_not_sponsor"]
    location_fit: Literal["exact", "remote", "mismatch"]
    seniority_level: Literal["too_junior", "target", "stretch", "too_senior", "unclear"]
    hard_filter: bool
    hard_filter_reason: Optional[str] = None

    # Resume coaching
    resume_keywords: list[str]       # top 5-8 keywords to add/emphasize
    suggested_summary: str           # 2-sentence tailored summary
    top_bullets: list[str]           # top 3 existing bullets to lead with
    gap_handling: Optional[str] = None  # how to address gaps honestly

    # Dashboard metadata
    run_id: str
    status: str = "new"              # overridden by localStorage on client
