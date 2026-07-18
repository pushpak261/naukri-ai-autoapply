"""
Resume parser for the LinkedIn Agent.
Parses PDF resumes using PyMuPDF with Gemini LLM for structured extraction.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.linked_agent.bot.interfaces import ILLMProvider, IRepository
from src.linked_agent.config.settings import Settings
from src.linked_agent.models.entities import ResumeProfile
from src.linked_agent.utils.logger import get_logger

logger = get_logger(__name__)


class LinkedInResumeParser:
    """Parse PDF resumes into structured ResumeProfile using AI."""

    def __init__(
        self,
        llm_provider: ILLMProvider,
        repository: IRepository,
        settings: Settings,
    ) -> None:
        self._llm = llm_provider
        self._repo = repository
        self._settings = settings

    async def parse(self, pdf_path: str) -> ResumeProfile:
        """Parse a resume PDF and return a structured profile."""
        path = Path(pdf_path)
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()

        # Check local resume_profile.json first for shared/synchronized profile
        profile_json_path = self._settings.project_root / "resume_profile.json"
        if profile_json_path.exists():
            try:
                logger.info("Loading resume profile from shared resume_profile.json")
                with open(profile_json_path, encoding="utf-8") as f:
                    cached_data = json.load(f)
                    profile = self._profile_from_json(json.dumps(cached_data))
                    profile.file_hash = file_hash
                    # Save to SQLite database cache if it's not already there
                    cached = await self._repo.get_cached_profile(file_hash)
                    if not cached:
                        await self._repo.save_resume_profile(
                            file_hash=file_hash,
                            file_path=str(path),
                            parsed_json=json.dumps(cached_data),
                        )
                    return profile
            except Exception as e:
                logger.warning(f"Failed to read local resume_profile.json: {e}")

        # Check cache
        cached = await self._repo.get_cached_profile(file_hash)
        if cached:
            logger.info("Using cached resume profile")
            return self._profile_from_json(cached.parsed_json)

        # Extract text from PDF
        raw_text = self._extract_text(path)
        if not raw_text:
            logger.error(f"Could not extract text from {pdf_path}")
            return ResumeProfile(file_hash=file_hash, raw_text="")

        # Use AI to parse
        if self._settings.ai.use_gemini and self._settings.ai.gemini_api_key:
            profile = await self._parse_with_ai(raw_text, file_hash)
        else:
            profile = self._parse_basic(raw_text, file_hash)

        # Cache the result
        profile_dict = {
            "name": profile.name,
            "email": profile.email,
            "phone": profile.phone,
            "current_title": profile.current_title,
            "summary": profile.summary,
            "total_experience_years": profile.total_experience_years,
            "skills": profile.skills,
            "technical_skills": profile.technical_skills,
            "soft_skills": profile.soft_skills,
            "job_titles_held": profile.job_titles_held,
            "education": profile.education,
            "work_experience": profile.work_experience,
            "certifications": profile.certifications,
            "languages": profile.languages,
            "key_achievements": profile.key_achievements,
        }

        await self._repo.save_resume_profile(
            file_hash=file_hash,
            file_path=str(path),
            parsed_json=json.dumps(profile_dict, default=str),
        )

        return profile

    def _extract_text(self, path: Path) -> str:
        """Extract text from a PDF file."""
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(str(path))
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text.strip()
        except ImportError:
            logger.warning("PyMuPDF not installed. Install with: pip install pymupdf")
            return ""
        except Exception as e:
            logger.error(f"Failed to extract PDF text: {e}")
            return ""

    async def _parse_with_ai(self, raw_text: str, file_hash: str) -> ResumeProfile:
        """Use Gemini LLM to parse resume text into structured data."""
        prompt = f"""Parse the following resume text into a structured JSON profile.

RESUME TEXT:
{raw_text[:6000]}

Return a JSON object with these fields:
- "name": string
- "email": string
- "phone": string
- "current_title": string (most recent job title)
- "summary": string (2-3 sentence professional summary)
- "total_experience_years": number
- "skills": array of strings (all skills mentioned)
- "technical_skills": array of strings (programming languages, frameworks, tools)
- "soft_skills": array of strings
- "job_titles_held": array of strings (all job titles in chronological order)
- "education": array of objects with "degree", "institution", "year"
- "work_experience": array of objects with "title", "company", "duration", "description"
- "certifications": array of strings
- "languages": array of strings
- "key_achievements": array of strings

Return ONLY the JSON, no other text."""

        try:
            response = await self._llm.generate_content(
                prompt=prompt,
                temperature=0.1,
                max_output_tokens=4096,
                response_mime_type="application/json",
            )

            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]

            data = json.loads(cleaned)

            return ResumeProfile(
                name=data.get("name", ""),
                email=data.get("email", ""),
                phone=data.get("phone", ""),
                current_title=data.get("current_title", ""),
                summary=data.get("summary", ""),
                total_experience_years=float(data.get("total_experience_years", 0)),
                skills=data.get("skills", []),
                technical_skills=data.get("technical_skills", []),
                soft_skills=data.get("soft_skills", []),
                job_titles_held=data.get("job_titles_held", []),
                education=data.get("education", []),
                work_experience=data.get("work_experience", []),
                certifications=data.get("certifications", []),
                languages=data.get("languages", []),
                key_achievements=data.get("key_achievements", []),
                file_hash=file_hash,
                raw_text=raw_text,
            )

        except Exception as e:
            logger.error(f"AI resume parsing failed: {e}")
            return self._parse_basic(raw_text, file_hash)

    def _parse_basic(self, raw_text: str, file_hash: str) -> ResumeProfile:
        """Basic regex-based parsing fallback."""
        import re

        # Extract email
        email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", raw_text)
        email = email_match.group(0) if email_match else ""

        # Extract phone
        phone_match = re.search(r"\b\d{10}\b", raw_text)
        if not phone_match:
            phone_match = re.search(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", raw_text)
        phone = phone_match.group(0) if phone_match else ""

        # Extract name (usually first line)
        lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
        name = lines[0] if lines else ""

        return ResumeProfile(
            name=name,
            email=email,
            phone=phone,
            file_hash=file_hash,
            raw_text=raw_text,
        )

    def _profile_from_json(self, json_str: str) -> ResumeProfile:
        """Reconstruct a ResumeProfile from cached JSON."""
        try:
            data = json.loads(json_str)
            return ResumeProfile(
                name=data.get("name", ""),
                email=data.get("email", ""),
                phone=data.get("phone", ""),
                current_title=data.get("current_title", ""),
                summary=data.get("summary", ""),
                total_experience_years=float(data.get("total_experience_years", 0)),
                skills=data.get("skills", []),
                technical_skills=data.get("technical_skills", []),
                soft_skills=data.get("soft_skills", []),
                job_titles_held=data.get("job_titles_held", []),
                education=data.get("education", []),
                work_experience=data.get("work_experience", []),
                certifications=data.get("certifications", []),
                languages=data.get("languages", []),
                key_achievements=data.get("key_achievements", []),
            )
        except Exception as e:
            logger.error(f"Failed to reconstruct profile from cache: {e}")
            return ResumeProfile()
