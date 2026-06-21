"""
AI-powered job-resume matching engine using Google Gemini.

Compares a job description against the candidate's parsed resume profile
to compute a match score (0-100) with detailed reasoning, matching skills,
and missing skills. Used by the orchestrator to decide whether to apply.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.core.interfaces import ILLMProvider, IJobMatcher
from src.core.exceptions import LLMQuotaExceededError
from src.config.settings import Settings
from src.utils.helpers import truncate_text, clean_text
from src.utils.logger import get_logger, log_match

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
        if result["should_apply"]:
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
        resume_profile: dict,
        job_data: dict,
    ) -> dict:
        """
        Score how well a candidate matches a job.

        Args:
            resume_profile: Structured resume profile from ResumeParser.
            job_data: Dict with keys: title, company, location, experience,
                      salary, description, skills.

        Returns:
            Dict with score, should_apply, matching_skills, missing_skills,
            experience_fit, reasoning, etc.
        """
        # Format resume profile for the prompt
        resume_summary = json.dumps(resume_profile, indent=2, ensure_ascii=False)
        resume_summary = truncate_text(resume_summary, max_length=6000)

        resume_hash = resume_profile.get("file_hash", "")
        job_id = job_data.get("naukri_job_id", "")
        if resume_hash and job_id:
            cached_result = self._cache.get(resume_hash, job_id)
            if cached_result:
                logger.debug(f"Cache hit for Job Match: {job_id}")
                return cached_result

        # Clean and truncate job description
        description = clean_text(job_data.get("description", ""))
        description = truncate_text(description, max_length=4000)

        prompt = MATCH_PROMPT.format(
            resume_profile=resume_summary,
            job_title=job_data.get("title", "Unknown"),
            job_company=job_data.get("company", "Unknown"),
            job_location=job_data.get("location", "Not specified"),
            job_experience=job_data.get("experience", "Not specified"),
            job_salary=job_data.get("salary", "Not disclosed"),
            job_description=description,
            job_skills=job_data.get("skills", "Not specified"),
            threshold=self._threshold,
        )

        try:
            response_text = await self._llm.generate_content(
                prompt=prompt,
                temperature=self._settings.ai.temperature,
                max_output_tokens=2048,
                response_mime_type="application/json",
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
                title=job_data.get("title", "Unknown"),
                company=job_data.get("company", "Unknown"),
                should_apply=result["should_apply"],
            )

            logger.info(
                f"Match: {result['score']}/100 | "
                f"Apply: {result['should_apply']} | "
                f"Skills: +{len(result['matching_skills'])} "
                f"-{len(result['missing_skills'])} | "
                f"Exp: {result['experience_fit']}"
            )

            return result

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
            logger.debug(f"Raw response: {response_text[:500]}")
            # Return a conservative default
            return {
                "score": 0,
                "should_apply": False,
                "matching_skills": [],
                "missing_skills": [],
                "experience_fit": "unknown",
                "reasoning": f"AI matching failed: {e}",
                "strengths": [],
                "concerns": ["AI matching error — skipping to be safe"],
            }
        except Exception as e:
            logger.error(f"Job matching failed: {e}")
            return {
                "score": 0,
                "should_apply": False,
                "matching_skills": [],
                "missing_skills": [],
                "experience_fit": "unknown",
                "reasoning": f"Error: {e}",
                "strengths": [],
                "concerns": [str(e)],
            }
