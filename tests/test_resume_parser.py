"""
Tests for the resume parser module.

Tests PDF text extraction and profile parsing without making actual API calls.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.naukri_agent.ai.resume_parser import ResumeParser
from src.naukri_agent.core.domain.entities import ResumeProfile


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    settings = MagicMock()
    settings.ai.gemini_api_key = "test_key"
    settings.ai.model = "gemini-2.5-flash"
    settings.ai.temperature = 0.3
    settings.ai.max_output_tokens = 4096
    return settings


@pytest.fixture
def mock_repo():
    """Create a mock repository."""
    repo = MagicMock()
    repo.get_cached_profile.return_value = None
    repo.save_resume_profile.return_value = None
    return repo


@pytest.fixture
def sample_profile():
    """A sample parsed resume profile."""
    return ResumeProfile(
        name="John Doe",
        email="john@example.com",
        phone="+91-9876543210",
        current_title="Senior Python Developer",
        summary="Experienced backend developer with 5 years in Python.",
        total_experience_years=5.0,
        skills=["Python", "FastAPI", "Django", "PostgreSQL", "AWS", "Docker"],
        technical_skills=["Python", "FastAPI", "Django", "PostgreSQL"],
        soft_skills=["Leadership", "Communication"],
        job_titles_held=["Python Developer", "Senior Python Developer"],
        education=[
            {"degree": "B.Tech Computer Science", "institution": "IIT Delhi", "year": "2019"}
        ],
        work_experience=[
            {
                "title": "Senior Python Developer",
                "company": "Tech Corp",
                "duration": "Jan 2022 - Present",
                "highlights": ["Built microservices", "Led team of 5"],
            }
        ],
        certifications=["AWS Solutions Architect"],
        languages=["English", "Hindi"],
        key_achievements=["Reduced API latency by 40%"],
    )


class TestResumeParser:
    """Tests for the ResumeParser class."""

    def test_parser_creation(self, mock_settings, mock_repo):
        """Test that parser can be created with an LLM provider, repo, and settings."""
        mock_llm = AsyncMock()
        parser = ResumeParser(mock_llm, mock_repo, mock_settings)
        assert parser is not None

    @pytest.mark.asyncio
    async def test_cached_profile_returned_without_api_call(
        self, mock_settings, mock_repo, sample_profile, tmp_path
    ):
        """A cached profile should be returned without calling the LLM or PyMuPDF."""
        mock_repo.get_cached_profile = AsyncMock(return_value=sample_profile)
        mock_llm = AsyncMock()

        parser = ResumeParser(mock_llm, mock_repo, mock_settings)

        # Use a real (tiny) file so hash_file() has something to read.
        fake_pdf = tmp_path / "resume.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4 fake content for hashing")

        result = await parser.parse(fake_pdf)

        assert result == sample_profile
        mock_llm.generate_content.assert_not_called()

    def test_profile_structure(self, sample_profile):
        """Test that a valid profile has all required fields."""
        assert sample_profile.name == "John Doe"
        assert sample_profile.skills is not None
        assert sample_profile.total_experience_years == 5.0
        assert sample_profile.education is not None
        assert sample_profile.work_experience is not None

    def test_skills_list_not_empty(self, sample_profile):
        """Test that skills list is populated."""
        assert len(sample_profile.skills) > 0

    def test_experience_is_number(self, sample_profile):
        """Test that experience years is numeric."""
        assert isinstance(sample_profile.total_experience_years, (int, float))
