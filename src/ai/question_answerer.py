"""
AI-powered question answerer for application screening questions.

When Naukri's apply flow presents screening questions (CTC, notice period,
experience, skills, etc.), this module uses a combination of config values
and Gemini AI to generate contextually appropriate answers.
"""

from __future__ import annotations

import json
from pathlib import Path
from pydantic import BaseModel

from src.core.interfaces import ILLMProvider, IQuestionAnswerer
from src.core.exceptions import LLMAPIError, LLMQuotaExceededError
from src.config.settings import Settings
from src.utils.logger import get_logger, log_info


class ScreeningAnswer(BaseModel):
    question: str
    answer: str
    confidence: str


logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Question answering prompt
# ---------------------------------------------------------------------------
QUESTION_ANSWER_PROMPT = """You are helping a job applicant fill in screening questions on a job application form. Use the candidate's profile information to answer each question accurately and professionally.

CANDIDATE PROFILE:
- Current CTC: {current_ctc}
- Expected CTC: {expected_ctc}
- Notice Period: {notice_period}
- Total Experience: {total_experience}
- Current Location: {current_location}
- Skills: {skills}

JOB BEING APPLIED TO:
- Title: {job_title}
- Company: {job_company}

QUESTIONS TO ANSWER:
{questions_json}

For each question, provide the best answer based on the candidate's profile.
Return a valid JSON array with answers in the same order as the questions:

[
    {{
        "question": "Original question text",
        "answer": "Your answer",
        "confidence": "high" | "medium" | "low"
    }},
    ...
]

RULES:
1. Be truthful — use actual profile data, don't fabricate experience or skills.
2. For CTC questions, use the provided values directly.
3. For notice period, use the exact value from the profile.
4. For experience questions, use total_experience value.
5. For Yes/No questions about skills, say "Yes" only if the skill is in the profile.
6. For open-ended questions, keep answers concise (1-2 sentences max).
7. If you're unsure about an answer, set confidence to "low".
8. Return ONLY the JSON array. No extra text."""


# ---------------------------------------------------------------------------
# Common question patterns (can be answered without AI)
# ---------------------------------------------------------------------------
DIRECT_ANSWER_PATTERNS = {
    "current ctc": "current_ctc",
    "current salary": "current_ctc",
    "present ctc": "current_ctc",
    "expected ctc": "expected_ctc",
    "expected salary": "expected_ctc",
    "notice period": "notice_period",
    "total experience": "total_experience",
    "years of experience": "total_experience",
    "current location": "current_location",
    "current city": "current_location",
}


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

    def get(self, question: str) -> str | None:
        return self._qa_cache.get(question)

    def set(self, question: str, answer: str) -> None:
        self._qa_cache[question] = answer

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
        self, llm_provider: ILLMProvider, settings: Settings, resume_profile: dict
    ) -> None:
        self._llm = llm_provider
        self._settings = settings
        self._profile = resume_profile

        # Build answer lookup from config
        self._direct_answers = {
            "current_ctc": settings.profile.current_ctc,
            "expected_ctc": settings.profile.expected_ctc,
            "notice_period": settings.profile.notice_period,
            "total_experience": settings.profile.total_experience,
            "current_location": settings.profile.current_location,
        }

        # Load local QA cache to save API tokens
        cache_file = settings.project_root / "data" / "qa_cache.json"
        self._cache = QACache(cache_file)

    def _try_direct_answer(self, question_text: str) -> str | None:
        """
        Try to answer a question directly from config values using
        pattern matching. Returns None if no pattern matches.
        """
        question_lower = question_text.lower().strip()

        for pattern, config_key in DIRECT_ANSWER_PATTERNS.items():
            if pattern in question_lower:
                answer = self._direct_answers.get(config_key, "")
                if answer:
                    logger.debug(f"Direct answer for '{pattern}': {answer}")
                    return answer

        return None

    async def answer_questions(
        self,
        questions: list[dict[str, str]],
        job_data: dict,
    ) -> list[dict]:
        """
        Answer a list of screening questions.

        Args:
            questions: List of dicts with keys: "question" (text),
                      "type" (text/dropdown/radio), "options" (list, if applicable).
            job_data: Dict with job title, company, etc.

        Returns:
            List of dicts with "question", "answer", "confidence" keys.
        """
        if not questions:
            return []

        answers: list[dict] = []
        ai_questions = []

        # First pass: try direct answers and CACHE
        for q in questions:
            question_text = q.get("question", "")
            direct = self._try_direct_answer(question_text)
            cached = self._cache.get(question_text)

            if direct:
                answers.append(
                    {
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
            ai_answers = await self._ask_ai(ai_questions, job_data)
            # Map original index back to AI answers
            for ans, orig_q in zip(ai_answers, ai_questions, strict=False):
                ans["index"] = orig_q.get("index", 0)
            answers.extend(ai_answers)

        # Sort by original index
        answers.sort(key=lambda x: x.get("index", 0))
        return answers

    async def _ask_ai(
        self,
        questions: list[dict],
        job_data: dict,
    ) -> list[dict]:
        """Use Gemini to answer complex screening questions."""
        skills_list = ", ".join(self._profile.get("skills", [])[:30])

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

        prompt = QUESTION_ANSWER_PROMPT.format(
            current_ctc=self._settings.profile.current_ctc or "Not specified",
            expected_ctc=self._settings.profile.expected_ctc or "Not specified",
            notice_period=self._settings.profile.notice_period or "Not specified",
            total_experience=self._settings.profile.total_experience or "Not specified",
            current_location=self._settings.profile.current_location or "Not specified",
            skills=skills_list,
            job_title=job_data.get("title", "Unknown"),
            job_company=job_data.get("company", "Unknown"),
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
