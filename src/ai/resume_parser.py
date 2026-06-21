"""
AI-powered resume parser using Google Gemini.

Extracts text from PDF resumes and uses Gemini to produce a structured
JSON profile with skills, experience, education, and other key details.
Results are cached in the database by file hash to avoid redundant API calls.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.core.interfaces import ILLMProvider, IRepository, IResumeParser
from src.core.exceptions import LLMAPIError, LLMQuotaExceededError
from src.config.settings import Settings
from src.utils.helpers import hash_file, truncate_text
from src.utils.logger import get_logger, log_info, log_success, log_error

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Resume profile schema (what Gemini should return)
# ---------------------------------------------------------------------------
RESUME_PARSE_PROMPT = """You are an expert resume analyzer. Parse the following resume text and extract structured information.

Return a valid JSON object with EXACTLY this structure (no markdown, no code fences, just raw JSON):

{{
    "name": "Full name of the candidate",
    "email": "Email address if found, else empty string",
    "phone": "Phone number if found, else empty string",
    "current_title": "Current or most recent job title",
    "summary": "A 2-3 sentence professional summary",
    "total_experience_years": <number>,
    "skills": ["skill1", "skill2", ...],
    "technical_skills": ["tech_skill1", "tech_skill2", ...],
    "soft_skills": ["soft_skill1", "soft_skill2", ...],
    "job_titles_held": ["title1", "title2", ...],
    "education": [
        {{
            "degree": "Degree name",
            "institution": "Institution name",
            "year": "Graduation year or empty string"
        }}
    ],
    "work_experience": [
        {{
            "title": "Job title",
            "company": "Company name",
            "duration": "Duration string (e.g., 'Jan 2020 - Present')",
            "highlights": ["Key achievement 1", "Key achievement 2"]
        }}
    ],
    "certifications": ["cert1", "cert2", ...],
    "languages": ["language1", "language2", ...],
    "key_achievements": ["achievement1", "achievement2", ...]
}}

IMPORTANT RULES:
1. Extract ALL skills mentioned, including programming languages, frameworks, tools, and platforms.
2. For total_experience_years, calculate from work history. If unclear, estimate conservatively.
3. Return ONLY the JSON object. No explanations, no markdown formatting.
4. If a field is not found in the resume, use an empty string or empty list as appropriate.

RESUME TEXT:
{resume_text}"""


class ResumeParser(IResumeParser):
    """
    Parses PDF resumes into structured profiles using AI.

    Usage:
        parser = ResumeParser(llm_provider, repository, settings)
        profile = await parser.parse("path/to/resume.pdf")
    """

    def __init__(
        self, llm_provider: ILLMProvider, repository: IRepository, settings: Settings
    ) -> None:
        self._llm = llm_provider
        self._repo = repository
        self._settings = settings

    def _extract_pdf_text(self, pdf_path: str | Path) -> str:
        """
        Extract raw text from a PDF file using PyMuPDF.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            Extracted text content.

        Raises:
            FileNotFoundError: If the PDF file doesn't exist.
            ValueError: If no text could be extracted.
        """
        import fitz  # PyMuPDF

        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"Resume file not found: {path}")

        doc = fitz.open(str(path))
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text("text"))
        doc.close()

        full_text = "\n".join(text_parts).strip()
        if not full_text:
            raise ValueError(f"No text could be extracted from: {path}")

        logger.debug(f"Extracted {len(full_text)} characters from {path.name}")
        return full_text

    async def parse(self, pdf_path: str | Path) -> dict:
        """
        Parse a resume PDF into a structured profile.

        Checks the database cache first. If cached, returns immediately.
        Otherwise, extracts text, sends to Gemini, and caches the result.

        Args:
            pdf_path: Path to the PDF resume file.

        Returns:
            Dict with structured resume profile.
        """
        path = Path(pdf_path)
        file_hash = hash_file(path)

        # Check cache
        if self._repo:
            cached = await self._repo.get_cached_profile(file_hash)
            if cached:
                log_info(f"Using cached resume profile for {path.name}")
                return cached

        log_info(f"Parsing resume: {path.name}")

        # Extract text
        resume_text = self._extract_pdf_text(path)
        truncated_text = truncate_text(resume_text, max_length=15000)

        # Call Gemini
        prompt = RESUME_PARSE_PROMPT.format(resume_text=truncated_text)

        try:
            response_text = await self._llm.generate_content(
                prompt=prompt,
                temperature=0.1,
                max_output_tokens=8192,
                response_mime_type="application/json",
            )

            profile = json.loads(response_text)
            log_success(f"Resume parsed successfully: {profile.get('name', 'Unknown')}")
            logger.info(
                f"Found {len(profile.get('skills', []))} skills, "
                f"{profile.get('total_experience_years', '?')} years experience"
            )

            # Cache the result
            if self._repo:
                await self._repo.save_resume_profile(
                    file_hash=file_hash,
                    file_path=str(path),
                    parsed_json=json.dumps(profile, ensure_ascii=False),
                )

            return profile

        except LLMQuotaExceededError as e:
            if e.is_daily_quota:
                log_error(f"⚠️  Gemini daily quota exhausted: {e}")
            else:
                log_error(f"⚠️  Gemini rate limit hit: {e}")
            return {}
        except LLMAPIError as e:
            logger.error(str(e))
            return {}
        except Exception as e:
            log_error(f"Failed to parse resume with AI: {e}")
            return {}

    def parse_sync(self, pdf_path: str | Path) -> dict:
        """Synchronous wrapper for parse()."""
        import asyncio

        return asyncio.run(self.parse(pdf_path))
