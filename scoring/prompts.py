"""Claude API prompt construction with prompt caching.

The resume is large and stable across all calls in a run.
It is placed in the system prompt with cache_control: ephemeral.
The first call in a run is a cache miss; subsequent calls reuse the cached prefix
(5-min TTL), making per-job cost ~10% of a cold call.
"""

import json


SYSTEM_PREFIX = """\
You are an expert PM career coach and senior tech recruiter.
You evaluate PM job postings against a candidate's resume and provide:
  1. A structured fit score (0–100)
  2. Actionable resume coaching tailored to this specific role

Be honest and calibrated. A score above 75 means "seriously apply." 50–75 is "maybe with tailoring."
Under 50 is "significant gap." Do not inflate scores.

For sponsorship_status, base your judgment on explicit signals in the job description:
  - "we sponsor work visas / H-1B / relocation" → does_sponsor
  - "will not sponsor / no sponsorship / US citizen only" → does_not_sponsor (these are caught as hard_filter=true)
  - "must be authorized to work" (soft language) → unknown (leaning unlikely, note it)
  - No mention → unknown

For seniority_level:
  - too_junior: The role is IC2/junior, candidate would be overqualified
  - target: Matches candidate's target level (Senior PM / Staff PM)
  - stretch: One level above target — possible but competitive
  - too_senior: Director / VP level, significantly above target
  - unclear: Job description does not signal level clearly

SCORING RUBRIC:
  requirements_match (0–25): Do the required skills, tools, and domain expertise match the candidate's experience?
  domain_alignment (0–25): Does the product domain (AI/Search/Consumer/Growth/etc.) align with candidate's target archetypes?
  pm_archetype_fit (0–20): Does the PM type (Consumer/Growth/Platform/AI/B2B/etc.) match candidate's background?
  evidence_strength (0–15): How many of the candidate's resume bullets directly prove the requirements?
  seniority_fit (0–10): How well does the role level match the candidate's target seniority?
  nice_to_have_bonus (0–5): Brand value, interesting tech stack, team signals, growth stage, equity potential

"""

SCORING_RUBRIC_SUFFIX = """

Call the score_job tool with your complete assessment.
"""


def _format_skills(skills) -> str:
    """Handle both flat list and categorized dict skill formats."""
    if isinstance(skills, list):
        return ", ".join(skills)
    if isinstance(skills, dict):
        parts = []
        if skills.get("core"):
            parts.append("Core: " + ", ".join(skills["core"]))
        if skills.get("ai_ml"):
            parts.append("AI/ML: " + ", ".join(skills["ai_ml"]))
        if skills.get("tools"):
            parts.append("Tools: " + ", ".join(skills["tools"]))
        if skills.get("use_with_caution"):
            parts.append("Familiar (use with caution): " + ", ".join(skills["use_with_caution"]))
        return "\n  ".join(parts)
    return ""


def _format_visa(visa_status) -> str:
    """Handle both string and object visa_status formats."""
    if isinstance(visa_status, str):
        return visa_status
    if isinstance(visa_status, dict):
        status = visa_status.get("current_status", "unknown")
        needs = visa_status.get("needs", "")
        return f"{status} — {needs}" if needs else status
    return "unknown"


def _format_seniority(target_seniority) -> str:
    """Handle both flat list and object seniority formats."""
    if isinstance(target_seniority, list):
        return ", ".join(target_seniority)
    if isinstance(target_seniority, dict):
        parts = []
        if target_seniority.get("primary"):
            parts.append("Target: " + ", ".join(target_seniority["primary"]))
        if target_seniority.get("stretch"):
            parts.append("Stretch: " + ", ".join(target_seniority["stretch"]))
        if target_seniority.get("avoid"):
            parts.append("Avoid: " + ", ".join(target_seniority["avoid"]))
        return " | ".join(parts)
    return ""


def format_resume(resume: dict) -> str:
    """Convert resume.json to a readable string for the system prompt."""
    lines = []
    lines.append(f"CANDIDATE: {resume.get('name', 'Candidate')}")
    lines.append(f"HEADLINE: {resume.get('headline', '')}")
    lines.append(f"LOCATION: {resume.get('location', '')}")
    lines.append(f"YEARS OF EXPERIENCE: {resume.get('years_of_experience', '?')}")
    lines.append(f"VISA STATUS: {_format_visa(resume.get('visa_status', 'unknown'))}")
    lines.append("")

    if resume.get("summary"):
        lines.append(f"SUMMARY: {resume['summary']}")
        lines.append("")

    lines.append(f"TARGET ARCHETYPES: {', '.join(resume.get('target_archetypes', []))}")
    lines.append(f"TARGET SENIORITY: {_format_seniority(resume.get('target_seniority', []))}")
    lines.append(f"PREFERRED LOCATIONS: {', '.join(resume.get('preferred_locations', []))}")
    lines.append("")

    lines.append(f"SKILLS:\n  {_format_skills(resume.get('skills', []))}")
    lines.append("")

    lines.append("EXPERIENCE:")
    for exp in resume.get("experience", []):
        lines.append(f"  {exp.get('title')} at {exp.get('company')} ({exp.get('dates', '')})")
        lines.append(f"  Domain: {exp.get('domain', '')}")
        for bullet in exp.get("bullets", []):
            lines.append(f"    • {bullet}")
        # Include role-specific keywords if present — helps Claude match JD language
        if exp.get("keywords"):
            lines.append(f"    Keywords: {', '.join(exp['keywords'][:15])}")
        lines.append("")

    lines.append("EDUCATION:")
    for edu in resume.get("education", []):
        lines.append(f"  {edu.get('degree')} — {edu.get('school')} ({edu.get('year', '')})")
    lines.append("")

    lines.append("KEY ACHIEVEMENTS:")
    for ach in resume.get("key_achievements", []):
        lines.append(f"  • {ach}")

    return "\n".join(lines)


def build_system_prompt(resume: dict) -> list[dict]:
    """Return system prompt blocks with cache_control on the resume block."""
    resume_text = format_resume(resume)
    full_text = SYSTEM_PREFIX + resume_text + SCORING_RUBRIC_SUFFIX
    return [
        {
            "type": "text",
            "text": full_text,
            "cache_control": {"type": "ephemeral"},
        }
    ]


def build_user_message(job, company_note: str) -> str:
    """Build the per-job user message. Truncates description to ~6000 chars."""
    description = (job.description_raw or "")[:6000]
    days = f"{job.days_old:.0f}" if job.days_old is not None else "unknown"
    return f"""\
Score this PM job posting:

COMPANY: {job.company}
COMPANY NOTE: {company_note}
TITLE: {job.title}
LOCATION: {job.location}{"  (remote)" if job.remote else ""}
POSTED: {days} days ago
SOURCE: {job.platform}
URL: {job.url}

JOB DESCRIPTION:
{description}

---
Call the score_job tool with your complete assessment."""
