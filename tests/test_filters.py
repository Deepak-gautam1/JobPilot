"""
tests/test_filters.py

Unit tests for filters.py — the most critical file in the pipeline.
Run with: python -m pytest tests/ -v
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from filters import is_entry_level, is_safe_url


# ── HELPER ───────────────────────────────────────────────
def check(title="", description="", job_level="", job_url=""):
    return is_entry_level(title=title, description=description,
                          job_level=job_level, job_url=job_url)


# ── TITLE BLOCKING ───────────────────────────────────────
class TestSeniorTitleBlocking:
    def test_blocks_senior_prefix(self):
        assert check(title="Senior Software Engineer") is False

    def test_blocks_sr_dot(self):
        assert check(title="Sr. Python Developer") is False

    def test_blocks_lead(self):
        assert check(title="Lead Backend Engineer") is False

    def test_blocks_staff(self):
        assert check(title="Staff Engineer") is False

    def test_blocks_principal(self):
        assert check(title="Principal SDE") is False

    def test_blocks_tech_lead(self):
        assert check(title="Tech Lead - AI Platform") is False

    def test_blocks_engineering_manager(self):
        assert check(title="Engineering Manager, ML") is False

    def test_blocks_director(self):
        assert check(title="Director of Engineering") is False

    def test_allows_plain_sde(self):
        assert check(title="Software Development Engineer") is True

    def test_allows_associate_engineer(self):
        assert check(title="Associate Software Engineer") is True

    def test_allows_junior(self):
        assert check(title="Junior Backend Developer") is True


# ── DESCRIPTION KEYWORD BLOCKING ─────────────────────────
class TestDescriptionKeywordBlocking:
    def test_blocks_2_plus_years(self):
        assert check(description="We require 2+ years of experience.") is False

    def test_blocks_minimum_2_years(self):
        assert check(description="Minimum 2 years experience required.") is False

    def test_blocks_3_plus_years(self):
        assert check(description="Must have 3+ years in Python.") is False

    def test_blocks_5_plus_years(self):
        assert check(description="5+ years of professional experience.") is False

    def test_blocks_2_to_4_years(self):
        assert check(description="2 to 4 years of relevant experience.") is False

    def test_blocks_2_dash_3_years(self):
        assert check(description="2-3 years experience preferred.") is False

    def test_blocks_3_to_5_years(self):
        assert check(description="3 to 5 years in software development.") is False

    def test_blocks_experienced_engineer(self):
        assert check(description="Looking for an experienced engineer.") is False

    def test_blocks_seasoned_engineer(self):
        assert check(description="We need a seasoned engineer for this role.") is False

    def test_allows_fresh_graduate(self):
        assert check(description="Great opportunity for fresh graduates.") is True

    def test_allows_clean_description(self):
        assert check(description="Python, React, FastAPI. Join our team.") is True


# ── REGEX-BASED EXPERIENCE BLOCKING ──────────────────────
class TestDigitExperienceRegex:
    def test_blocks_2_years_experience(self):
        assert check(description="2 years experience required") is False

    def test_blocks_3_years_of_experience(self):
        assert check(description="3 years of experience in cloud") is False

    def test_blocks_4_to_6_years(self):
        assert check(description="4 to 6 years of work experience") is False

    def test_blocks_five_years(self):
        assert check(description="five years of professional experience") is False

    def test_blocks_three_years(self):
        assert check(description="three years of industry experience") is False

    def test_allows_1_year(self):
        # "1 year" should NOT be blocked — within entry-level range
        assert check(description="1 year of experience preferred.") is True

    def test_allows_0_to_1_year(self):
        assert check(description="0 to 1 year of experience required.") is True


# ── LINKEDIN JOB LEVEL BLOCKING ───────────────────────────
class TestJobLevelBlocking:
    def test_blocks_mid_senior(self):
        assert check(job_level="Mid-Senior level") is False

    def test_blocks_senior_level(self):
        assert check(job_level="Senior level") is False

    def test_blocks_director_level(self):
        assert check(job_level="Director") is False

    def test_blocks_executive(self):
        assert check(job_level="Executive") is False

    def test_allows_entry_level(self):
        assert check(job_level="Entry level") is True

    def test_allows_associate(self):
        assert check(job_level="Associate") is True

    def test_allows_empty_level(self):
        assert check(job_level="") is True


# ── NAUKRI URL BLOCKING ───────────────────────────────────
class TestNaukriUrlBlocking:
    def test_blocks_naukri_range_2_to_5(self):
        assert check(job_url="https://www.naukri.com/sde-2-to-5-year-jobs") is False

    def test_blocks_naukri_single_3_year(self):
        assert check(job_url="https://www.naukri.com/python-3-year-experience") is False

    def test_allows_naukri_0_year(self):
        assert check(job_url="https://www.naukri.com/fresher-0-year-jobs") is True

    def test_allows_non_naukri_url(self):
        assert check(job_url="https://www.linkedin.com/jobs/view/12345") is True


# ── ENTRY-LEVEL WHITELIST ─────────────────────────────────
class TestEntryLevelWhitelist:
    def test_fresher_in_title_always_passes(self):
        assert check(title="Fresher Software Engineer") is True

    def test_new_grad_passes(self):
        assert check(title="New Graduate - SDE Role") is True

    def test_campus_hire_passes(self):
        assert check(description="This is a campus hire position for 2025 graduates.") is True

    def test_zero_to_one_year_passes(self):
        assert check(description="0-1 years of experience required.") is True

    def test_no_experience_required_passes(self):
        assert check(description="No experience required. Training provided.") is True


# ── URL SAFETY ────────────────────────────────────────────
class TestSafeUrl:
    def test_https_is_safe(self):
        assert is_safe_url("https://www.amazon.jobs/en/jobs/12345") is True

    def test_http_is_not_safe(self):
        assert is_safe_url("http://example.com/job") is False

    def test_javascript_is_not_safe(self):
        assert is_safe_url("javascript:void(0)") is False

    def test_data_uri_is_not_safe(self):
        assert is_safe_url("data:text/html,<script>alert(1)</script>") is False

    def test_empty_string_is_not_safe(self):
        assert is_safe_url("") is False


# ── COMBINED / EDGE CASES ─────────────────────────────────
class TestEdgeCases:
    def test_all_empty_passes(self):
        assert check() is True

    def test_senior_title_overrides_fresher_description(self):
        # Title check runs first — senior title always blocks
        assert check(title="Senior Engineer", description="fresher welcome") is False

    def test_clean_ai_engineer_role(self):
        assert check(
            title="AI Engineer",
            description="Work on LLMs, RAG pipelines, Python. Open to freshers.",
            job_level="Entry level",
        ) is True

    def test_realistic_senior_posting(self):
        assert check(
            title="Software Engineer II",
            description="We are looking for 3+ years of experience in distributed systems.",
            job_level="Mid-Senior level",
        ) is False

    def test_realistic_entry_posting(self):
        assert check(
            title="Software Development Engineer",
            description="Join our team. Python, React, AWS. No prior experience required.",
            job_level="Entry level",
            job_url="https://www.amazon.jobs/en/jobs/99999",
        ) is True
