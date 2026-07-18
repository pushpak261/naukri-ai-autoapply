"""
AI-powered job matcher for the LinkedIn Agent.
Compares a resume profile against a job listing and returns a match score.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

from src.linked_agent.bot.interfaces import ILLMProvider
from src.linked_agent.config.settings import Settings
from src.linked_agent.models.entities import Job, JobApplication, ResumeProfile
from src.linked_agent.utils.exceptions import LLMAPIError, LLMQuotaExceededError
from src.linked_agent.utils.logger import get_logger

logger = get_logger(__name__)


class LinkedInJobMatcher:
    """
    AI-powered job matcher using Gemini LLM.

    Compares resume profile against job description and returns:
    - match_score (0-100)
    - should_apply (bool)
    - match_reasoning (str)
    - matching_skills (list)
    - missing_skills (list)
    """

    def __init__(self, llm_provider: ILLMProvider, settings: Settings) -> None:
        self._llm = llm_provider
        self._settings = settings
        self._cache = _MatchCache(settings.data_dir / "linkedin_match_cache.json")

    async def match(self, resume_profile: ResumeProfile, job: Job) -> JobApplication:
        """Match a resume against a job and return scoring results."""
        # Check cache
        cache_key = self._cache_key(resume_profile, job)
        cached = self._cache.get(cache_key)
        if cached:
            logger.debug(f"Cache hit for job {job.linkedin_job_id}")
            return cached

        if not self._settings.ai.use_gemini or not self._settings.ai.gemini_api_key:
            return self._local_match(resume_profile, job)

        # Build prompt
        prompt = self._build_match_prompt(resume_profile, job)

        try:
            response = await self._llm.generate_content(
                prompt=prompt,
                temperature=0.2,
                max_output_tokens=2048,
                response_mime_type="application/json",
            )

            result = self._parse_response(response, job, resume_profile)
            self._cache.set(cache_key, result)
            return result

        except (LLMQuotaExceededError, LLMAPIError) as e:
            logger.error(f"AI API error for job {job.linkedin_job_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"AI matching failed for job {job.linkedin_job_id}: {e}")
            return self._local_match(resume_profile, job)

    def _local_match(self, resume_profile: ResumeProfile, job: Job) -> JobApplication:
        """Fallback local matching using skill overlap with word boundaries."""
        import re as _re
        resume_skills = set(s.lower().strip() for s in resume_profile.skills if len(s.strip()) > 2)
        job_text = f"{job.title} {job.description} {job.skills}".lower()

        def word_boundary_match(skill: str) -> bool:
            pattern = _re.compile(r'\b' + _re.escape(skill) + r'\b')
            return bool(pattern.search(job_text))

        matching = [s for s in resume_skills if word_boundary_match(s)]
        all_skills = [s for s in resume_skills if len(s) > 2]
        missing = [s for s in all_skills if not word_boundary_match(s)]

        total = len(all_skills) or 1
        ratio = len(matching) / total
        score = min(100, int(ratio * 60 + len(matching) * 5 + 20)) if matching else max(5, min(30, int(ratio * 30)))

        return JobApplication(
            match_score=score,
            should_apply=True,
            match_reasoning=f"Local match: {len(matching)}/{total} skills found ({ratio:.0%})",
            matching_skills=", ".join(matching[:10]),
            missing_skills=", ".join(missing[:10]),
        )

    def _build_match_prompt(self, resume: ResumeProfile, job: Job) -> str:
        """Build the LLM prompt for job matching."""
        resume_text = f"""
Name: {resume.name}
Current Title: {resume.current_title}
Summary: {resume.summary}
Skills: {', '.join(resume.skills)}
Technical Skills: {', '.join(resume.technical_skills)}
Experience: {resume.total_experience_years} years
Education: {json.dumps(resume.education[:3], default=str)}
Work Experience: {json.dumps(resume.work_experience[:3], default=str)}
"""

        return f"""You are an expert job matching AI. Compare the following resume profile against the job listing and provide a match score.

RESUME PROFILE:
{resume_text.strip()}

JOB LISTING:
Title: {job.title}
Company: {job.company}
Location: {job.location}
Description: {job.description[:3000]}

Provide your analysis as JSON with these fields:
- "match_score": number (0-100, where higher means better match)
- "should_apply": always true (we apply to all relevant jobs)
- "match_reasoning": string (2-3 sentences explaining the match)
- "matching_skills": array of strings (skills from resume that match job requirements)
- "missing_skills": array of strings (key skills from job that are missing from resume)

Consider:
1. Skill overlap (most important)
2. Experience level alignment
3. Role relevance
4. Location compatibility

Return ONLY the JSON object, no other text."""

    def _parse_response(self, response: str, job: Job, resume_profile: ResumeProfile | None = None) -> JobApplication:
        """Parse the LLM JSON response into a JobApplication."""
        try:
            # Clean response
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]

            data = json.loads(cleaned)

            return JobApplication(
                match_score=float(data.get("match_score", 0)),
                should_apply=bool(data.get("should_apply", False)),
                match_reasoning=data.get("match_reasoning", ""),
                matching_skills=", ".join(data.get("matching_skills", [])),
                missing_skills=", ".join(data.get("missing_skills", [])),
            )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error(f"Failed to parse match response: {e}")
            return self._local_match(resume_profile or ResumeProfile(), job)

    def _cache_key(self, resume: ResumeProfile, job: Job) -> str:
        """Generate a cache key from resume hash + job ID."""
        resume_hash = hashlib.md5(
            f"{resume.name}{resume.current_title}{','.join(resume.skills)}".encode()
        ).hexdigest()[:16]
        return f"{resume_hash}_{job.linkedin_job_id}"


class _MatchCache:
    """Simple disk-based cache for match results."""

    def __init__(self, cache_path: Path) -> None:
        self._path = cache_path
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                import json
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                self._data = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        import json
        self._path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def get(self, key: str) -> JobApplication | None:
        if key in self._data:
            d = self._data[key]
            return JobApplication(
                match_score=d.get("match_score", 0),
                should_apply=d.get("should_apply", False),
                match_reasoning=d.get("match_reasoning", ""),
                matching_skills=d.get("matching_skills", ""),
                missing_skills=d.get("missing_skills", ""),
            )
        return None

    def set(self, key: str, result: JobApplication) -> None:
        self._data[key] = {
            "match_score": result.match_score,
            "should_apply": result.should_apply,
            "match_reasoning": result.match_reasoning,
            "matching_skills": result.matching_skills,
            "missing_skills": result.missing_skills,
        }
        self._save()
