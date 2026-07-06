"""
AI-powered question answerer for application screening questions.

When Naukri's apply flow presents screening questions (CTC, notice period,
experience, skills, etc.), this module uses a combination of config values
and Gemini AI to generate contextually appropriate answers.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


from pydantic import BaseModel

from src.naukri_agent.config.settings import Settings
from src.naukri_agent.models.entities import Job, ResumeProfile
from src.naukri_agent.utils.exceptions import LLMAPIError, LLMQuotaExceededError
from src.naukri_agent.bot.interfaces import ILLMProvider, IQuestionAnswerer
from src.naukri_agent.utils.logger import get_logger, log_info


class ScreeningAnswer(BaseModel):
    question: str
    answer: str
    confidence: str


logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Question answering prompt
# ---------------------------------------------------------------------------
QUESTION_ANSWER_PROMPT = """You are an ultra-precise job application assistant. Your task is to extract exact answers for screening questions based on the candidate's profile. You MUST follow the strict formatting and reasoning rules below.

CANDIDATE DETAILS (from resume profile):
- Full Name: {candidate_name}
- Email: {candidate_email}
- Phone: {candidate_phone}
- Current Title: {current_title}
- Current Location: {current_location}
- Preferred Locations: {preferred_locations} (Willing to relocate: Yes)
- Total Experience: {total_experience}
- Current CTC: {current_ctc}
- Expected CTC: {expected_ctc} (negotiable)
- Notice Period: {notice_period}
- Technical Skills: {skills}
- Education:
{education_summary}
- Work Experience:
{work_summary}

{raw_text_section}

JOB DETAILS:
- Title: {job_title}
- Company: {job_company}

QUESTIONS TO ANSWER:
{questions_json}

CRITICAL RULES:
1. MULTIPLE CHOICE ENFORCEMENT: If the question provides options (e.g. checkbox/radio/dropdown), your answer MUST match one of the options EXACTLY. Select the best match from the options list.
   - For relocation: If asked about relocation or working in Pune/Mumbai/Bangalore, choose "Yes" or equivalent positive option.
   - For notice period: Choose "Immediate", "0 days", "15 days", or the shortest option available if "Immediate" is not listed.
   - For CTC: Choose the option closest to the candidate's CTC.
2. REASONING & INTENT:
   - Understand the intent of the question. For example, if asked "How many years of experience do you have in Spring Boot?", and the candidate has worked with Spring Boot in 2 jobs (Mastek and VestalCode), they have about 1 year of total experience. Answer "1" or "1 year" (or the option representing 1-2 years).
   - If asked about a skill the candidate has, answer "Yes" or the appropriate positive option.
   - If asked about a skill not explicitly listed in the skills list, scan the FULL RESUME TEXT. If it's mentioned or related to their projects, answer "Yes" or matching years of experience.
   - If asked "Are you comfortable working in Pune?", answer "Yes" (as candidate lives in Pune).
3. FORMAT COMPLIANCE:
   - For text fields, write a concise, professional answer (no conversational filler).
   - For number fields, return only the numeric digits (e.g. "1" instead of "1 year", "440000" instead of "4.4 Lakhs") unless the options dictate otherwise.
   - For date fields, write in standard YYYY-MM-DD or DD/MM/YYYY format if applicable.
4. DEFAULTING:
   - Never leave an answer blank. If you are unsure, choose/write the most reasonable positive option (e.g., "Yes" for consent, relocation, or shift availability; "1" for years of experience; "Immediate" for notice period; expected CTC for CTC questions).

EXPECTED JSON OUTPUT (Strictly return a JSON array of objects with the exact structure below, no markdown wrappers, no explanation):
[
    {{
        "question": "Original question text",
        "answer": "Exact answer string matching one of the options (if choice field) or a precise string/number (if text/number field)",
        "confidence": "high"
    }},
    ...
]"""


# ---------------------------------------------------------------------------
# Common question patterns (can be answered without AI)
# ---------------------------------------------------------------------------
DIRECT_ANSWER_PATTERNS = {
    "current ctc": "current_ctc",
    "current salary": "current_ctc",
    "present ctc": "current_ctc",
    "current fixed ctc": "current_ctc",
    "expected ctc": "expected_ctc",
    "expected salary": "expected_ctc",
    "notice period": "notice_period",
    "noticeperiod": "notice_period",
    "serving notice": "notice_period",
    "total experience": "total_experience",
    "years of experience": "total_experience",
    "total exp": "total_experience",
    "work experience": "total_experience",
    "current location": "current_location",
    "current city": "current_location",
    "residence": "current_location",
    "live in": "current_location",
    "relocate": "reloc_consent",
    "willing to relocate": "reloc_consent",
}


def _normalize_question_text(question_text: str) -> str:
    """Normalize question text for robust matching and caching."""
    q = question_text or ""
    q = q.lower().strip()
    q = re.sub(r"\s+", " ", q)
    q = re.sub(r"[^a-z0-9 ]+", " ", q)
    q = re.sub(r"\s+", " ", q)
    return q.strip()


class QACache:
    """Manages local caching of generated AI answers."""

    def __init__(self, cache_file: Path) -> None:
        self._cache_file = cache_file
        self._qa_cache: dict[str, str] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        """Load previously generated AI answers from disk."""
        if self._cache_file.exists():
            try:
                import json

                with open(self._cache_file, encoding="utf-8") as f:
                    self._qa_cache = json.load(f)
            except Exception:
                self._qa_cache = {}

    def _save_cache(self) -> None:
        """Persist new AI answers to disk."""
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            import json

            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(self._qa_cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.debug(f"Failed to save QA cache: {e}")

    def get(self, question_key: str) -> str | None:
        return self._qa_cache.get(question_key)

    def set(self, question_key: str, answer: str) -> None:
        self._qa_cache[question_key] = answer

    def save(self) -> None:
        self._save_cache()


class QuestionAnswerer(IQuestionAnswerer):
    """
    Answers application screening questions using config + AI.

    First attempts pattern matching against common questions (CTC, notice
    period, etc.) using config values. Falls back to LLM for complex
    or ambiguous questions.

    Usage:
        answerer = QuestionAnswerer(llm_provider, settings, resume_profile)
        answers = await answerer.answer_questions(questions, job_data)
    """

    def __init__(
        self, llm_provider: ILLMProvider, settings: Settings, resume_profile: ResumeProfile
    ) -> None:
        self._llm = llm_provider
        self._settings = settings
        self._profile = resume_profile

        # Build answer lookup from config, falling back to parsed resume profile
        profile_experience = (
            f"{resume_profile.total_experience_years} years"
            if resume_profile.total_experience_years
            else None
        )
        self._direct_answers = {
            "current_ctc": settings.profile.current_ctc or "4.4 LPA",
            "expected_ctc": settings.profile.expected_ctc or "6 LPA",
            "notice_period": settings.profile.notice_period or "Immediate",
            "total_experience": settings.profile.total_experience
            or profile_experience
            or "1 years",
            "current_location": settings.profile.current_location
            or resume_profile.current_title
            or "Pune",
            "reloc_consent": "Yes",
        }

        # Load local QA cache to save API tokens
        cache_file = settings.project_root / "data" / "qa_cache.json"
        self._cache = QACache(cache_file)

        # Initialize Trie/Aho-Corasick on DIRECT_ANSWER_PATTERNS keys
        from src.naukri_agent.utils.trie import AhoCorasick

        self._trie = AhoCorasick(list(DIRECT_ANSWER_PATTERNS.keys()))

    def _try_direct_answer(
        self, question_text: str, q_type: str = "text", options: list[dict] | None = None
    ) -> str | None:
        """
        Try to answer a question directly from config values using Trie lookup
        or Fuzzy Levenshtein Distance matching. If options are present,
        resolves the value to the best matching choice.
        Returns None if no match.
        """
        question_lower = question_text.lower().strip()
        config_key = None
        best_pattern = None

        # 1. Exact/Substring match using Aho-Corasick (Trie)
        matched_patterns = self._trie.search(question_lower)
        if matched_patterns:
            best_pattern = str(max(matched_patterns.keys(), key=len))
            config_key = DIRECT_ANSWER_PATTERNS.get(best_pattern, "")

        # 2. Fuzzy Levenshtein match fallback
        if not config_key:
            from src.naukri_agent.utils.fuzzy import fuzzy_similarity_ratio

            best_fuzzy_pattern = None
            best_fuzzy_score = 0.0

            for pattern in DIRECT_ANSWER_PATTERNS:
                score = fuzzy_similarity_ratio(pattern, question_lower)
                if score > best_fuzzy_score:
                    best_fuzzy_score = score
                    best_fuzzy_pattern = pattern

            if best_fuzzy_pattern and best_fuzzy_score >= 0.80:
                best_pattern = best_fuzzy_pattern
                config_key = DIRECT_ANSWER_PATTERNS[best_fuzzy_pattern]

        if not config_key:
            return None

        raw_val = self._direct_answers.get(config_key, "")
        if not raw_val:
            return None

        # If it's a choice field (dropdown/radio/checkbox), match the choice!
        if q_type in ("dropdown", "radio", "checkbox") and options:
            opt_texts = [o.get("text", "") for o in options]
            val_lower = raw_val.lower().strip()

            # Exact match first
            for opt in opt_texts:
                if opt.lower().strip() == val_lower:
                    return opt

            # Number-based range matching for CTC or Experience
            if config_key in ("current_ctc", "expected_ctc", "total_experience"):
                # Extract number from config value
                candidate_nums = re.findall(r"\d+(?:\.\d+)?", raw_val)
                if candidate_nums:
                    candidate_num = float(candidate_nums[0])
                    # Parse ranges from option texts
                    for opt in opt_texts:
                        opt_nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", opt)]
                        if len(opt_nums) == 2:
                            if min(opt_nums) <= candidate_num <= max(opt_nums):
                                return opt
                        elif len(opt_nums) == 1:
                            parsed_num = opt_nums[0]
                            if "above" in opt.lower() or "more" in opt.lower() or "+" in opt:
                                if candidate_num >= parsed_num:
                                    return opt
                            elif "less" in opt.lower() or "below" in opt.lower() or "under" in opt:
                                if candidate_num <= parsed_num:
                                    return opt
                            elif candidate_num == parsed_num:
                                return opt

            # Fuzzy/Substring match
            for opt in opt_texts:
                opt_lower = opt.lower().strip()
                if val_lower in opt_lower or opt_lower in val_lower:
                    return opt

            # Fallback specifically for relocation
            if config_key == "reloc_consent":
                for opt in opt_texts:
                    if "yes" in opt.lower() or "willing" in opt.lower() or "agree" in opt.lower():
                        return opt

            # Fallback specifically for notice period (shortest)
            if config_key == "notice_period":
                for opt in opt_texts:
                    if (
                        "immediate" in opt.lower()
                        or "0 days" in opt.lower()
                        or "serving" in opt.lower()
                    ):
                        return opt

            # If we couldn't match, fall back to LLM to prevent wrong selections
            return None

        # For text fields, format appropriately if it expects a number
        if q_type == "number" or "years" in question_lower or "digit" in question_lower:
            nums = re.findall(r"\d+(?:\.\d+)?", raw_val)
            if nums:
                return nums[0]

        logger.debug(f"Direct answer matched for '{best_pattern}': {raw_val}")
        return raw_val

    async def answer_questions(
        self,
        questions: list[dict],
        job: Job,
    ) -> list[dict]:
        """
        Answer a list of screening questions.

        Args:
            questions: List of dicts with keys: "question" (text),
                      "type" (text/dropdown/radio), "options" (list, if applicable).
            job: Job domain entity.

        Returns:
            List of dicts with "question", "answer", "confidence", "id" keys.
        """
        if not questions:
            return []

        answers: list[dict] = []
        ai_questions = []

        # First pass: try direct answers and CACHE
        for q in questions:
            question_text = q.get("question", "")
            q_type = q.get("type", "text")
            options = q.get("options", [])
            direct = self._try_direct_answer(question_text, q_type, options)
            q_key = _normalize_question_text(question_text)
            cached = self._cache.get(q_key)

            if direct:
                answers.append(
                    {
                        "id": q.get("id"),
                        "question": question_text,
                        "answer": direct,
                        "confidence": "high",
                        "index": q.get("index", len(answers)),
                    }
                )
            elif cached:
                logger.debug(f"Cache hit for QA: {question_text}")
                answers.append(
                    {
                        "id": q.get("id"),
                        "question": question_text,
                        "answer": cached,
                        "confidence": "high",
                        "index": q.get("index", len(answers)),
                    }
                )
            else:
                ai_questions.append(q)

        # Second pass: use AI for remaining questions
        if ai_questions:
            if not self._settings.ai.use_gemini:
                logger.info("Gemini AI is disabled. Skipping complex AI questions.")
                ai_answers = [
                    {
                        "question": q.get("question", ""),
                        "answer": "",
                        "confidence": "low",
                    }
                    for q in ai_questions
                ]
            elif not self._settings.application.answer_questions_with_pdf:
                logger.info(
                    "Skipping Gemini question answering because answer_questions_with_pdf is false."
                )
                ai_answers = [
                    {
                        "question": q.get("question", ""),
                        "answer": "",
                        "confidence": "low",
                    }
                    for q in ai_questions
                ]
            else:
                ai_answers = await self._ask_ai(ai_questions, job)
            # Map original index back to AI answers
            for ans, orig_q in zip(ai_answers, ai_questions, strict=False):
                ans["index"] = orig_q.get("index", 0)
                ans["id"] = orig_q.get("id")
            answers.extend(ai_answers)

        # Sort by original index
        answers.sort(key=lambda x: x.get("index", 0))
        return answers

    @staticmethod
    def _format_education(education_list: list[dict]) -> str:
        if not education_list:
            return "  * No formal education listed"
        lines = []
        for edu in education_list:
            degree = edu.get("degree", edu.get("qualification", ""))
            institution = edu.get("institution", edu.get("university", ""))
            year = edu.get("year", edu.get("graduation_year", ""))
            parts = [f"  * {degree}"] if degree else []
            if institution:
                parts.append(f"from {institution}")
            if year:
                parts.append(f"({year})")
            lines.append(" ".join(parts) if parts else "  * Unknown")
        return "\n".join(lines)

    @staticmethod
    def _format_work_experience(work_list: list[dict]) -> str:
        if not work_list:
            return "  * No work experience listed"
        lines = []
        for exp in work_list:
            title = exp.get("title", exp.get("role", exp.get("position", "")))
            company = exp.get("company", exp.get("organization", ""))
            location = exp.get("location", "")
            description = exp.get("description", exp.get("summary", ""))
            parts = [f"  * {title}"] if title else ["  * Position"]
            if company:
                parts.append(f"at {company}")
            if location:
                parts.append(f"({location})")
            if description:
                parts.append(f": {description}")
            lines.append(" ".join(parts))
        return "\n".join(lines)

    async def _ask_ai(
        self,
        questions: list[dict],
        job: Job,
    ) -> list[dict]:
        """Use Gemini to answer complex screening questions."""
        skills_list = ", ".join(self._profile.skills[:30])

        questions_json = json.dumps(
            [
                {
                    "question": q.get("question", ""),
                    "type": q.get("type", "text"),
                    "options": q.get("options", []),
                }
                for q in questions
            ],
            indent=2,
        )

        raw_text_section = ""
        if (
            getattr(self._settings.application, "answer_questions_with_pdf", False)
            and hasattr(self._profile, "raw_text")
            and self._profile.raw_text
        ):
            raw_text_section = (
                "FULL RESUME TEXT:\n"
                "The following is the candidate's complete raw resume text. Use this to find precise, highly specific details "
                "(such as exact years of experience in niche technologies like Dart, Flutter, etc.) that might not be in the high-level summary.\n"
                "---\n"
                f"{self._profile.raw_text}\n"
                "---"
            )

        preferred_locations = (
            ", ".join(self._settings.profile.preferred_locations)
            if self._settings.profile.preferred_locations
            else "Not specified"
        )

        prompt = QUESTION_ANSWER_PROMPT.format(
            candidate_name=self._profile.name or "Not specified",
            candidate_email=self._profile.email or "Not specified",
            candidate_phone=self._profile.phone or "Not specified",
            current_title=self._profile.current_title or "Not specified",
            current_ctc=self._settings.profile.current_ctc or "Not specified",
            expected_ctc=self._settings.profile.expected_ctc or "Not specified",
            notice_period=self._settings.profile.notice_period or "Not specified",
            total_experience=self._settings.profile.total_experience or "Not specified",
            current_location=self._settings.profile.current_location or "Not specified",
            preferred_locations=preferred_locations,
            skills=skills_list,
            education_summary=self._format_education(self._profile.education),
            work_summary=self._format_work_experience(self._profile.work_experience),
            raw_text_section=raw_text_section,
            job_title=job.title or "Unknown",
            job_company=job.company or "Unknown",
            questions_json=questions_json,
        )

        try:
            response_text = await self._llm.generate_content(
                prompt=prompt,
                temperature=0.2,
                max_output_tokens=2048,
                response_mime_type="application/json",
                response_schema=list[ScreeningAnswer],
            )

            ai_answers = json.loads(response_text)

            # Save new high-confidence answers to cache
            cache_updated = False
            for ans in ai_answers:
                q_text = ans.get("question", "")
                a_text = ans.get("answer", "")
                if q_text and a_text and ans.get("confidence") != "low":
                    self._cache.set(q_text, a_text)
                    cache_updated = True

            if cache_updated:
                self._cache.save()

            log_info(f"AI answered {len(ai_answers)} screening questions")
            return ai_answers

        except LLMQuotaExceededError as e:
            if e.is_daily_quota:
                logger.error(f"⚠️  Gemini daily quota exhausted while answering questions: {e}")
            else:
                logger.error(f"⚠️  Gemini rate limit hit while answering questions: {e}")
            return [
                {
                    "question": q.get("question", ""),
                    "answer": "",
                    "confidence": "low",
                }
                for q in questions
            ]
        except LLMAPIError as e:
            logger.error(str(e))
            return [
                {
                    "question": q.get("question", ""),
                    "answer": "",
                    "confidence": "low",
                }
                for q in questions
            ]
        except Exception as e:
            logger.error(f"AI question answering failed: {e}")
            return [
                {
                    "question": q.get("question", ""),
                    "answer": "",
                    "confidence": "low",
                }
                for q in questions
            ]
