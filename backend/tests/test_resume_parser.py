"""
Tests for the resume parser module.

Tests PDF text extraction and profile parsing without making actual API calls.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.naukri_agent.ai.resume_parser import ResumeParser
from src.naukri_agent.models.entities import ResumeProfile


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

    def test_extract_docx_text(self, mock_settings, mock_repo, tmp_path):
        """Test that docx files can be parsed successfully using Python's zip/xml modules."""
        import zipfile

        mock_llm = AsyncMock()
        parser = ResumeParser(mock_llm, mock_repo, mock_settings)

        # Create a mock docx zip file
        docx_file = tmp_path / "resume.docx"
        with zipfile.ZipFile(docx_file, "w") as z:
            xml_content = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">\n'
                "<w:body>\n"
                "<w:p><w:r><w:t>John Doe Resume Content</w:t></w:r></w:p>\n"
                "<w:p><w:r><w:t>Skills: Python, Javascript</w:t></w:r></w:p>\n"
                "</w:body>\n"
                "</w:document>"
            )
            z.writestr("word/document.xml", xml_content)

        extracted_text = parser._extract_docx_text(docx_file)
        assert "John Doe Resume Content" in extracted_text
        assert "Skills: Python, Javascript" in extracted_text

    @pytest.mark.asyncio
    async def test_local_profile_ignored_during_parsing(
        self, mock_settings, mock_repo, sample_profile, tmp_path
    ):
        """Even if resume_profile.json exists, we ignore it and parse the file directly."""
        import json
        from src.naukri_agent.utils.helpers import hash_file

        mock_llm = AsyncMock()
        # Mock Gemini provider returning a dummy parsed JSON response
        mock_llm.generate_content.return_value = json.dumps(
            {
                "name": "Jane Doe",
                "email": "jane@example.com",
                "phone": "+91-9999999999",
                "current_title": "Software Engineer",
                "summary": "Jane's resume parsed from LLM",
                "total_experience_years": 2.0,
                "skills": ["Python"],
                "technical_skills": ["Python"],
                "soft_skills": [],
                "job_titles_held": [],
                "education": [],
                "work_experience": [],
                "certifications": [],
                "languages": [],
                "key_achievements": [],
            }
        )

        mock_settings.project_root = tmp_path
        mock_settings.application.answer_questions_with_pdf = False
        mock_settings.ai.use_gemini = True

        parser = ResumeParser(mock_llm, mock_repo, mock_settings)

        # Create a local resume_profile.json
        local_profile_file = tmp_path / "resume_profile.json"
        local_profile_file.write_text(
            json.dumps({"name": "Old John", "file_hash": "some_hash"}), encoding="utf-8"
        )

        # Create a new resume to parse
        new_resume = tmp_path / "new_resume.pdf"
        new_resume.write_bytes(b"%PDF-1.4 new resume contents")
        new_hash = hash_file(new_resume)

        # Ensure the mock repo also returns None for cache (db cache miss)
        mock_repo.get_cached_profile = AsyncMock(return_value=None)
        mock_repo.save_resume_profile = AsyncMock()

        # Mock pdf text extraction to avoid actually parsing a fake PDF with PyMuPDF
        parser._extract_pdf_text = MagicMock(return_value="Jane Doe Resume Content. Python.")

        # Trigger parse
        result = await parser.parse(new_resume)

        # It should ignore "Old John" and parse using LLM
        assert result.name == "Jane Doe"
        mock_llm.generate_content.assert_called_once()
        # It should write the newly parsed profile to the local file
        updated_profile = json.loads(local_profile_file.read_text(encoding="utf-8"))
        assert updated_profile["name"] == "Jane Doe"
        assert updated_profile["file_hash"] == new_hash
