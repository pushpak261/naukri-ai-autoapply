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
    id: str | None = None
    question: str
    answer: str
    confidence: str


logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Question answering prompt
# ---------------------------------------------------------------------------
QUESTION_ANSWER_PROMPT = """You are an ultra-precise job application assistant. Your task is to analyze each screening question and answer it strictly based on the candidate's profile, skills, education, and work experience.

CANDIDATE DETAILS (from resume profile):
- Full Name: {candidate_name}
- Email: {candidate_email}
- Phone: {candidate_phone}
- Current Title: {current_title}
- Current Location: {current_location}
- Preferred Locations: {preferred_locations} (Willing to relocate: Yes)
- Total Experience: 1 year ({total_experience})
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
1. EXPERIENCE QUESTIONS (TOTAL OR SKILL-SPECIFIC):
   - The candidate has 1 year of total professional experience.
   - For ANY question asking about experience (whether total experience or experience in specific technologies/skills like Java, Spring Boot, HTML, CSS, JavaScript, React, Python, SQL, AWS, microservices, etc.):
     * ALWAYS answer "1 year" (or "1" if numeric field, or matching choice option like "1 Year" / "1-2 Years" / "0-1 Years").
     * NEVER write long 3rd person paragraphs, candidate bios, or conversational descriptions (e.g. NEVER output "Pushpak Pandharpatte has 1 year of professional experience...").
2. POSITIVE ANSWERS MANDATORY:
   - Answer ALL questions positively to maximize the candidate's chances of receiving interview calls.
   - NEVER leave any question blank, empty, or unanswered.
3. MULTIPLE CHOICE ENFORCEMENT:
   - If `options` are provided for a question, your answer MUST match one of the option text strings EXACTLY.
4. FORMAT COMPLIANCE:
   - For text fields: ultra-concise, direct answer (e.g., "1 year", "Yes", "Immediate", "6 LPA"). No conversational prefixes.
   - For number fields: numeric digits only (e.g. "1", "2023", "450000").
5. PRESERVE QUESTION ID:
   - Include the exact "id" provided in each input question object in your output object.

EXPECTED JSON OUTPUT (Strictly return a JSON array of objects with the exact structure below, no markdown wrappers, no explanation):
[
    {{
        "id": "original question id",
        "question": "Original question text",
        "answer": "Exact answer string matching one of the options (if choice field) or a precise string/number (if text/number field)",
        "confidence": "high"
    }}
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
    "overall experience": "total_experience",
    "total work experience": "total_experience",
    "years of experience": "total_experience",
    "experience in": "total_experience",
    "current location": "current_location",
    "current city": "current_location",
    "residence": "current_location",
    "live in": "current_location",
    "relocate": "reloc_consent",
    "willing to relocate": "reloc_consent",
    "graduation year": "graduation_year",
    "year of graduation": "graduation_year",
    "passing year": "graduation_year",
    "year of passing": "graduation_year",
    "passing out year": "graduation_year",
    "degree year": "graduation_year",
    "education year": "graduation_year",
    "gender": "gender",
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
        normalized = _normalize_question_text(question_key)
        if normalized in self._qa_cache:
            return self._qa_cache[normalized]
        return self._qa_cache.get(question_key)

    def set(self, question_key: str, answer: str) -> None:
        normalized = _normalize_question_text(question_key)
        k_lower = (normalized or "").lower().strip()
        if not k_lower or len(k_lower) < 6:
            return
        invalid_patterns = [
            "userinput", "inputbox", "agent ", "select ", "option ",
            "question 1", "question 2", "question 3"
        ]
        # Also check patterns against the original key (before normalization)
        orig_lower = (question_key or "").lower().strip()
        orig_invalid = ["userinput", "inputbox", "agent_", "select_", "option_"]
        if any(pat in orig_lower for pat in orig_invalid):
            return
        if any(pat in k_lower for pat in invalid_patterns):
            return
        if not answer or not str(answer).strip():
            return
        self._qa_cache[normalized] = answer

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
            "graduation_year": "2023",
            "qualification": "Bachelor of Mechanical Engineering / PG-DAC",
            "gender": "Male",
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

        # Safeguard: If question asks about experience/knowledge in a specific skill or technology,
        # or is descriptive, pass to LLM (which is prompted to answer 1 year from total experience).
        skill_patterns = r"\b(html|css|javascript|js|react|angular|vue|python|java|c#|\.net|cpp|c\+\+|sql|mysql|postgres|mongodb|aws|azure|gcp|docker|kubernetes|git|node|express|django|flask|spring|rest|api|microservices|testing|qa|agile|devops|flutter|dart|android|ios|swift|kotlin|pandas|numpy|ml|ai)\b"
        has_skill_word = re.search(skill_patterns, question_lower) is not None
        is_descriptive = any(kw in question_lower for kw in ["describe", "explain", "tell", "why", "project"])

        if (has_skill_word or is_descriptive) and not any(k in question_lower for k in ["total experience", "overall experience", "total work experience"]):
            return None

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
                        "id": q.get("id"),
                        "question": q.get("question", ""),
                        "answer": "",
                        "confidence": "low",
                        "index": q.get("index", 0),
                    }
                    for q in ai_questions
                ]
            elif not self._settings.application.answer_questions_with_pdf:
                logger.info(
                    "Skipping Gemini question answering because answer_questions_with_pdf is false."
                )
                ai_answers = [
                    {
                        "id": q.get("id"),
                        "question": q.get("question", ""),
                        "answer": "",
                        "confidence": "low",
                        "index": q.get("index", 0),
                    }
                    for q in ai_questions
                ]
            else:
                ai_answers = await self._ask_ai(ai_questions, job)

                # Handle missing or low-confidence answers with interactive prompt if stdin is interactive
                import sys
                for ans in ai_answers:
                    orig_q = next(
                        (
                            q for q in ai_questions
                            if (q.get("id") and q.get("id") == ans.get("id"))
                            or (q.get("question") == ans.get("question"))
                        ),
                        None,
                    )
                    if ans.get("confidence") == "low" or not (ans.get("answer") or "").strip():
                        q_text = ans.get("question", "")
                        q_key = _normalize_question_text(q_text)
                        if sys.stdin and hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
                            try:
                                print(f"\n❓ [User Clarification Required] Missing info for question: '{q_text}'")
                                if orig_q and orig_q.get("options"):
                                    opts = ", ".join([o.get("text", "") for o in orig_q["options"]])
                                    print(f"   Available Options: [{opts}]")
                                user_ans = input("   Enter answer: ").strip()
                                if user_ans:
                                    ans["answer"] = user_ans
                                    ans["confidence"] = "high"
                                    self._cache.set(q_key, user_ans)
                                    self._cache.save()
                            except Exception as user_e:
                                logger.debug(f"Interactive user prompt skipped: {user_e}")

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
                    "id": q.get("id", f"q_{idx}"),
                    "question": q.get("question", ""),
                    "type": q.get("type", "text"),
                    "options": q.get("options", []),
                }
                for idx, q in enumerate(questions)
            ],
            indent=2,
        )

        raw_text_section = ""
        if hasattr(self._profile, "raw_text") and self._profile.raw_text:
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

            # Strip code fences if present
            cleaned = response_text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:].lstrip()

            try:
                ai_answers_raw = json.loads(cleaned)
            except json.JSONDecodeError:
                logger.warning("JSON parse failed, retrying with correction prompt")
                correction_prompt = (
                    f"The previous response was not valid JSON. Return a valid JSON array for these questions:\n\n"
                    f"{questions_json}\n\n"
                    f"Return ONLY valid JSON, no markdown wrappers."
                )
                response_text = await self._llm.generate_content(
                    prompt=correction_prompt,
                    temperature=0.1,
                    max_output_tokens=2048,
                    response_mime_type="application/json",
                    response_schema=list[ScreeningAnswer],
                )
                cleaned = response_text.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("```")[1]
                    if cleaned.startswith("json"):
                        cleaned = cleaned[4:].lstrip()
                ai_answers_raw = json.loads(cleaned)

            if not isinstance(ai_answers_raw, list):
                ai_answers_raw = [ai_answers_raw]

            ans_by_id = {}
            ans_by_q = {}
            for item in ai_answers_raw:
                if isinstance(item, dict):
                    if item.get("id"):
                        ans_by_id[item["id"]] = item
                    if item.get("question"):
                        ans_by_q[_normalize_question_text(item["question"])] = item

            ai_answers = []
            cache_updated = False
            for idx, orig_q in enumerate(questions):
                orig_id = orig_q.get("id")
                orig_q_text = orig_q.get("question", "")
                orig_q_key = _normalize_question_text(orig_q_text)

                matched_ans = None
                if orig_id and orig_id in ans_by_id:
                    matched_ans = ans_by_id[orig_id]
                elif orig_q_key and orig_q_key in ans_by_q:
                    matched_ans = ans_by_q[orig_q_key]
                elif idx < len(ai_answers_raw) and isinstance(ai_answers_raw[idx], dict):
                    matched_ans = ai_answers_raw[idx]

                if matched_ans:
                    a_val = str(matched_ans.get("answer", "")).strip()
                    conf = matched_ans.get("confidence", "high")
                else:
                    a_val = ""
                    conf = "low"

                # Constrain answer to provided options if this is a choice field
                orig_options = orig_q.get("options", [])
                if orig_options and a_val:
                    opt_texts = [o.get("text", "") for o in orig_options]
                    if a_val not in opt_texts:
                        from src.naukri_agent.utils.fuzzy import fuzzy_similarity_ratio
                        best_opt = None
                        best_score = 0.0
                        a_lower = a_val.lower().strip()
                        for opt in opt_texts:
                            o_lower = opt.lower().strip()
                            score = fuzzy_similarity_ratio(a_lower, o_lower)
                            if score > best_score:
                                best_score = score
                                best_opt = opt
                        if best_opt and best_score >= 0.70:
                            a_val = best_opt
                            conf = "high"
                        else:
                            conf = "low"

                if orig_q_text and a_val and conf != "low":
                    self._cache.set(orig_q_text, a_val)
                    cache_updated = True

                ai_answers.append(
                    {
                        "id": orig_id,
                        "question": orig_q_text,
                        "answer": a_val,
                        "confidence": conf,
                        "index": orig_q.get("index", 0),
                    }
                )

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
                    "id": q.get("id"),
                    "question": q.get("question", ""),
                    "answer": "",
                    "confidence": "low",
                    "index": q.get("index", 0),
                }
                for q in questions
            ]
        except LLMAPIError as e:
            logger.error(str(e))
            return [
                {
                    "id": q.get("id"),
                    "question": q.get("question", ""),
                    "answer": "",
                    "confidence": "low",
                    "index": q.get("index", 0),
                }
                for q in questions
            ]
        except Exception as e:
            logger.error(f"AI question answering failed: {e}")
            return [
                {
                    "id": q.get("id"),
                    "question": q.get("question", ""),
                    "answer": "",
                    "confidence": "low",
                    "index": q.get("index", 0),
                }
                for q in questions
            ]

