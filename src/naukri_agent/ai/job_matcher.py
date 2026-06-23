"""
AI-powered job-resume matching engine using Google Gemini.

Compares a job description against the candidate's parsed resume profile
to compute a match score (0-100) with detailed reasoning, matching skills,
and missing skills. Used by the orchestrator to decide whether to apply.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from pydantic import BaseModel

from src.naukri_agent.config.settings import Settings
from src.naukri_agent.core.domain.entities import Job, JobApplication, ResumeProfile
from src.naukri_agent.core.exceptions import LLMQuotaExceededError
from src.naukri_agent.core.interfaces import IJobMatcher, ILLMProvider
from src.naukri_agent.utils.helpers import clean_text, truncate_text
from src.naukri_agent.utils.logger import get_logger, log_match


class JobMatchResult(BaseModel):
    score: int
    should_apply: bool
    matching_skills: list[str]
    missing_skills: list[str]
    experience_fit: str
    location_fit: str
    reasoning: str
    strengths: list[str]
    concerns: list[str]


logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Match scoring prompt
# ---------------------------------------------------------------------------
MATCH_PROMPT = """You are an expert job-resume matching engine. Compare the candidate's resume profile with the job description and provide a detailed match assessment.

CANDIDATE RESUME PROFILE:
{resume_profile}

JOB DETAILS:
- Title: {job_title}
- Company: {job_company}
- Location: {job_location}
- Experience Required: {job_experience}
- Salary: {job_salary}

JOB DESCRIPTION:
{job_description}

JOB SKILLS REQUIRED:
{job_skills}

Analyze the match and return a valid JSON object with EXACTLY this structure (no markdown, no code fences, just raw JSON):

{{
    "score": <integer 0-100>,
    "should_apply": <true or false>,
    "matching_skills": ["skill1", "skill2", ...],
    "missing_skills": ["skill1", "skill2", ...],
    "experience_fit": "strong" | "moderate" | "weak" | "overqualified",
    "location_fit": "match" | "partial" | "mismatch" | "remote",
    "reasoning": "A 2-3 sentence explanation of the overall match quality",
    "strengths": ["strength1", "strength2"],
    "concerns": ["concern1", "concern2"]
}}

SCORING GUIDELINES:
- 90-100: Perfect match — skills, experience, and role align extremely well
- 75-89: Strong match — most required skills present, good experience fit
- 60-74: Moderate match — some skill gaps but transferable experience
- 40-59: Weak match — significant gaps, stretch role
- 0-39: Poor match — fundamentally different role or experience level

RULES:
1. Be realistic and honest in scoring. Don't inflate scores.
2. Consider transferable skills and related technologies.
3. If experience requirement is significantly higher than candidate's, reduce score.
4. "should_apply" should be true if score >= {threshold}.
5. Return ONLY the JSON object. No explanations outside the JSON."""


class MatchCache:
    """Persistent cache for job matching results to save AI tokens."""

    def __init__(self, cache_file: Path) -> None:
        self._cache_file = cache_file
        self._cache: dict[str, dict] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        if self._cache_file.exists():
            try:
                import json

                with open(self._cache_file, encoding="utf-8") as f:
                    self._cache = json.load(f)
            except Exception:
                self._cache = {}

    def _save_cache(self) -> None:
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            import json

            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.debug(f"Failed to save Match cache: {e}")

    def get(self, resume_hash: str, job_id: str) -> dict | None:
        key = f"{resume_hash}_{job_id}"
        return self._cache.get(key)

    def set(self, resume_hash: str, job_id: str, result: dict) -> None:
        key = f"{resume_hash}_{job_id}"
        self._cache[key] = result
        self._save_cache()


class JobMatcher(IJobMatcher):
    """
    AI-powered job-resume matching engine.

    Usage:
        matcher = JobMatcher(llm_provider, settings)
        result = await matcher.match(resume_profile, job_data)
        if result.should_apply:
            # proceed with application
    """

    def __init__(self, llm_provider: ILLMProvider, settings: Settings) -> None:
        self._llm = llm_provider
        self._settings = settings
        self._threshold = settings.application.match_score_threshold

        cache_file = settings.project_root / "data" / "match_cache.json"
        self._cache = MatchCache(cache_file)

    async def match(
        self,
        resume_profile: ResumeProfile,
        job: Job,
    ) -> JobApplication:
        """
        Score how well a candidate matches a job.

        Args:
            resume_profile: Structured resume profile from ResumeParser.
            job: Domain Job entity.

        Returns:
            JobApplication domain entity.
        """
        # Format resume profile for the prompt
        profile_dict = dataclasses.asdict(resume_profile)
        resume_summary = json.dumps(profile_dict, indent=2, ensure_ascii=False)
        resume_summary = truncate_text(resume_summary, max_length=6000)

        resume_hash = resume_profile.file_hash
        job_id = job.naukri_job_id
        if resume_hash and job_id:
            cached_result = self._cache.get(resume_hash, job_id)
            if cached_result:
                logger.debug(f"Cache hit for Job Match: {job_id}")
                return JobApplication(
                    match_score=float(cached_result.get("score", 0)),
                    status=(
                        "applied"
                        if cached_result.get("should_apply", False)
                        else "skipped_low_score"
                    ),
                    match_reasoning=cached_result.get("reasoning", ""),
                    matching_skills=", ".join(cached_result.get("matching_skills", [])),
                    missing_skills=", ".join(cached_result.get("missing_skills", [])),
                    should_apply=cached_result.get("should_apply", False),
                )

        # Clean and truncate job description
        description = clean_text(job.description)
        description = truncate_text(description, max_length=4000)

        prompt = MATCH_PROMPT.format(
            resume_profile=resume_summary,
            job_title=job.title or "Unknown",
            job_company=job.company or "Unknown",
            job_location=job.location or "Not specified",
            job_experience=job.experience or "Not specified",
            job_salary=job.salary or "Not disclosed",
            job_description=description,
            job_skills=job.skills or "Not specified",
            threshold=self._threshold,
        )

        try:
            response_text = await self._llm.generate_content(
                prompt=prompt,
                temperature=self._settings.ai.temperature,
                max_output_tokens=self._settings.ai.max_output_tokens,
                response_mime_type="application/json",
                response_schema=JobMatchResult,
            )

            try:
                result = json.loads(response_text)
            except json.JSONDecodeError as e:
                logger.warning(
                    f"⚠️ Failed to parse match response as JSON, retrying once with stricter prompt: {e}"
                )

                stricter_prompt = (
                    f"{prompt}\n\n"
                    "CRITICAL: The previous response was truncated or invalid. "
                    "You MUST return a complete, valid JSON object matching the schema exactly. "
                    "Keep all explanations (reasoning, strengths, concerns) extremely concise so the response fits within limits."
                )
                response_text = await self._llm.generate_content(
                    prompt=stricter_prompt,
                    temperature=self._settings.ai.temperature,
                    max_output_tokens=self._settings.ai.max_output_tokens,
                    response_mime_type="application/json",
                    response_schema=JobMatchResult,
                )
                result = json.loads(response_text)

            # Defensive defaults — the LLM is expected to follow the schema,
            # but we never trust external output blindly.
            result.setdefault("score", 0)
            result.setdefault("matching_skills", [])
            result.setdefault("missing_skills", [])
            result.setdefault("experience_fit", "unknown")
            result.setdefault("reasoning", "")

            # Ensure should_apply logic matches threshold
            score = result["score"]
            result["should_apply"] = score >= self._threshold

            if resume_hash and job_id:
                self._cache.set(resume_hash, job_id, result)

            # Log the match result
            log_match(
                score=result["score"],
                title=job.title or "Unknown",
                company=job.company or "Unknown",
                should_apply=result["should_apply"],
            )

            logger.info(
                f"Match: {result['score']}/100 | "
                f"Apply: {result['should_apply']} | "
                f"Skills: +{len(result['matching_skills'])} "
                f"-{len(result['missing_skills'])} | "
                f"Exp: {result['experience_fit']}"
            )

            return JobApplication(
                match_score=float(result["score"]),
                status="applied" if result["should_apply"] else "skipped_low_score",
                match_reasoning=result["reasoning"],
                matching_skills=", ".join(result["matching_skills"]),
                missing_skills=", ".join(result["missing_skills"]),
                should_apply=result["should_apply"],
            )

        except LLMQuotaExceededError:
            # Don't swallow this into a fake "score 0" result — every
            # subsequent job would silently get marked as a non-match even
            # though no actual evaluation happened. The caller (the
            # orchestrator's job-processing loop) needs to know evaluation
            # has stopped working so it can halt gracefully instead of
            # burning through the remaining job list pretending to score it.
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse match response as JSON: {e}")
            logger.error(f"Raw response: {response_text}")
            # Return a conservative default
            return JobApplication(
                match_score=0.0,
                status="failed",
                match_reasoning=f"AI matching failed to decode JSON: {e}",
                should_apply=False,
                error_message=str(e),
            )
        except Exception as e:
            logger.error(f"Job matching failed: {e}")
            return JobApplication(
                match_score=0.0,
                status="error",
                match_reasoning=f"Error: {e}",
                should_apply=False,
                error_message=str(e),
            )
