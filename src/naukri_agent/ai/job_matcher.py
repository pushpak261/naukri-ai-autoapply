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
from src.naukri_agent.models.entities import Job, JobApplication, ResumeProfile
from src.naukri_agent.utils.exceptions import LLMAPIError, LLMQuotaExceededError
from src.naukri_agent.bot.interfaces import IJobMatcher, ILLMProvider
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
MATCH_PROMPT = """You are a strict, precise job-resume matching engine. Compare the candidate's resume profile with the job description and assess whether they are a genuinely strong fit. Be critical — only recommend applying when there is clear, substantive overlap in core technical skills and relevant domain experience.

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
- Base score on ACTUAL core skill overlap. The candidate's primary stack is Java, Spring Boot, React, AWS, Microservices, SQL, Docker.
- Score 80+ only if the job clearly requires the candidate's primary stack and the candidate meets most requirements.
- Score 60-79 if there is reasonable overlap but some gaps in secondary skills or domain.
- Score 40-59 if only peripheral skills match (e.g., generic "JavaScript" or "Python" overlap but core stack is different).
- Score below 40 if the role requires a fundamentally different tech stack (e.g., .NET-only, Salesforce, SAP, Oracle ERP, data science, DevOps-only, mobile-only) or a completely different domain (finance, banking, healthcare, manufacturing, civil, mechanical).
- Subtract 20-40 for missing core skills that are central to the role.
- Subtract 10-20 if the industry/domain is completely different from the candidate's experience (retail, ERP, review management systems).
- Score 0 ONLY for clear SCAMS (asks for money/fees) or completely unrelated roles.

CRITICAL — DO NOT APPLY TO THESE:
1. SCAM / FINANCIAL FRAUD: money request → score 0
2. DIFFERENT TECH STACK: Salesforce, SAP, Oracle ERP, ServiceNow, Workday, data science, AI/ML-only, DevOps-only, mobile-only (iOS/Android/Flutter), embedded systems, hardware, IoT, mainframe, COBOL → score below 40
3. DIFFERENT DOMAIN: banking, finance, insurance, healthcare, pharma, civil, mechanical, electrical, electronics, automobile, teacher, faculty, nurse, doctor → score below 40
4. COMPLETELY WRONG ROLE: title says one thing but description is for something fundamentally different
5. EXPIRED / UNAVAILABLE
6. DUPLICATE / REPOSTED

IMPORTANT:
- The candidate is a Full-Stack Software Engineer with 3 years experience in Java, Spring Boot, React, AWS, microservices. They have worked on enterprise web applications (ERP, review management, retail). Do NOT recommend roles from unrelated domains or fundamentally different tech stacks.
- Indian IT services companies (TCS, Infosys, Wipro, Accenture, Cognizant, Capgemini, etc.) posting real Java/React developer roles ARE relevant and should be scored normally on skill match.
- Short descriptions that clearly ask for the candidate's stack are fine.
- DO NOT be generous. A score of {threshold} means "highly relevant and should apply." Only recommend applying when there is genuine, strong alignment.

"should_apply" should be true only if score >= {threshold} AND no red flags are detected.
Return ONLY the JSON object. No explanations outside the JSON."""


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

        # Check if we should use Gemini
        if not self._settings.ai.use_gemini:
            logger.info("Gemini AI is disabled. Using local deterministic matching.")
            return self._match_locally(resume_profile, job)
        if not self._settings.ai.enable_matching:
            logger.info(
                "Gemini matching is disabled via enable_matching: false. Using local deterministic matching."
            )
            return self._match_locally(resume_profile, job)

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

        except (LLMQuotaExceededError, LLMAPIError):
            # Don't swallow these — the caller (orchestrator) needs to know
            # if API limits or errors occurred so it can switch models or halt.
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

    def _match_locally(self, resume_profile: ResumeProfile, job: Job) -> JobApplication:
        from src.naukri_agent.utils.trie import AhoCorasick
        from src.naukri_agent.ai.resume_parser import DEFAULT_TECH_SKILLS

        matcher = AhoCorasick(DEFAULT_TECH_SKILLS)

        job_text = f"{job.title or ''} {job.description or ''} {job.skills or ''}".lower()
        job_skills = set(matcher.search(job_text).keys())

        if job.skills:
            explicit_skills = [s.strip().lower() for s in job.skills.split(",")]
            job_skills.update(explicit_skills)

        resume_skills = {s.lower() for s in resume_profile.skills}

        matching_skills = list(job_skills.intersection(resume_skills))
        missing_skills = list(job_skills.difference(resume_skills))

        score = 80.0 if not job_skills else (len(matching_skills) / len(job_skills)) * 100.0

        should_apply = score >= self._threshold

        log_match(
            score=score,
            title=job.title or "Unknown",
            company=job.company or "Unknown",
            should_apply=should_apply,
        )

        logger.info(
            f"Local Match: {score:.1f}/100 | "
            f"Apply: {should_apply} | "
            f"Skills: +{len(matching_skills)} "
            f"-{len(missing_skills)}"
        )

        return JobApplication(
            match_score=score,
            status="applied" if should_apply else "skipped_low_score",
            match_reasoning="Calculated using local deterministic algorithm based on skill overlap.",
            matching_skills=", ".join(matching_skills),
            missing_skills=", ".join(missing_skills),
            should_apply=should_apply,
        )
