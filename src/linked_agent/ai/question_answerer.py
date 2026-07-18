"""
AI-powered question answerer for LinkedIn Easy Apply forms.
Uses Gemini LLM to generate accurate answers for screening questions.
"""

from __future__ import annotations

import json
from typing import Any

from src.linked_agent.bot.interfaces import ILLMProvider
from src.linked_agent.config.settings import Settings
from src.linked_agent.models.entities import Job, ResumeProfile
from src.linked_agent.utils.logger import get_logger

logger = get_logger(__name__)


class LinkedInQuestionAnswerer:
    """
    Answers LinkedIn Easy Apply screening questions using AI.

    Uses the resume profile and job details to generate contextually
    accurate answers for various question types (text, dropdown, radio).
    """

    def __init__(
        self,
        llm_provider: ILLMProvider,
        settings: Settings,
        resume_profile: ResumeProfile,
    ) -> None:
        self._llm = llm_provider
        self._settings = settings
        self._resume = resume_profile

    async def answer_questions(
        self, questions: list[dict[str, Any]], job: Job
    ) -> list[dict[str, str]]:
        """
        Answer a list of screening questions.

        Args:
            questions: List of dicts with 'question', 'field_type', 'options'
            job: The job being applied to

        Returns:
            List of dicts with 'question' and 'answer' keys
        """
        if not questions:
            return []

        if not self._settings.ai.use_gemini or not self._settings.ai.gemini_api_key:
            return self._default_answers(questions)

        prompt = self._build_prompt(questions, job)

        try:
            response = await self._llm.generate_content(
                prompt=prompt,
                temperature=0.2,
                max_output_tokens=2048,
                response_mime_type="application/json",
            )

            return self._parse_response(response, questions)

        except Exception as e:
            logger.error(f"AI question answering failed: {e}")
            return self._default_answers(questions)

    def _default_answers(self, questions: list[dict[str, Any]]) -> list[dict[str, str]]:
        """Provide default answers when AI is unavailable."""
        answers = []
        for q in questions:
            question_text = q.get("question", "").lower()
            field_type = q.get("field_type", "text")
            options = q.get("options", [])

            answer = ""

            # Dropdown/radio: ALWAYS pick from options first — keyword patterns
            # can produce wrong answers (e.g. "experience" returns "1" for a Yes/No dropdown)
            if field_type in ("radio", "dropdown") and options:
                answer = self._pick_from_options(question_text, options)
            elif field_type == "text":
                answer = self._pick_text_answer(question_text)
            else:
                answer = "Yes" if field_type == "radio" else "N/A"

            answers.append({"question": q.get("question", ""), "answer": answer})

        return answers

    def _pick_from_options(self, question_text: str, options: list[str]) -> str:
        """Pick the best answer from dropdown/radio options."""
        real_options = [
            o for o in options
            if o.lower().strip() not in ("select an option", "none", "n/a", "other", "")
        ]
        if not real_options:
            return options[0] if options else ""

        ql = question_text.lower()

        # Yes/No questions: prefer "Yes"
        if any(w in ql for w in ["comfortable", "willing", "able", "authorized",
                                   "available", "legally", "require sponsorship",
                                   "do you have", "are you", "can you"]):
            for opt in real_options:
                if opt.lower() == "yes":
                    return opt
            return real_options[0]

        # Experience/years questions: pick a numeric option or highest
        if any(w in ql for w in ["experience", "years"]):
            numeric_opts = []
            for opt in real_options:
                clean = opt.replace("+", "").replace("years", "").replace("yrs", "").strip()
                try:
                    numeric_opts.append((float(clean), opt))
                except ValueError:
                    pass
            if numeric_opts:
                # Pick the lowest option that covers our 1 year experience
                numeric_opts.sort(key=lambda x: x[0])
                for val, opt in numeric_opts:
                    if val >= 1:
                        return opt
                return numeric_opts[0][1]
            # No numeric options — just pick "Yes" or first
            for opt in real_options:
                if opt.lower() == "yes":
                    return opt
            return real_options[0]

        # Default: pick first real option
        return real_options[0]

    def _pick_text_answer(self, question_text: str) -> str:
        """Pick the best text answer based on keyword patterns."""
        if any(w in question_text for w in ["experience", "years"]):
            return str(int(self._resume.total_experience_years)) if self._resume.total_experience_years else str(self._settings.profile.total_experience or "3")
        elif any(w in question_text for w in ["notice period", "joining"]):
            raw = self._settings.profile.notice_period or "30"
            # Strip "days" suffix for numeric-only fields
            return raw.replace("days", "").replace("day", "").strip()
        elif any(w in question_text for w in ["current ctc", "salary"]):
            return self._settings.profile.current_ctc or "500000"
        elif any(w in question_text for w in ["expected ctc", "expected salary"]):
            return self._settings.profile.expected_ctc or "700000"
        elif any(w in question_text for w in ["how soon", "start date", "available to start"]):
            return "1"
        elif any(w in question_text for w in ["hours per week", "hours/week", "weekly hours"]):
            return "40"
        elif "how many" in question_text:
            return "1"
        elif any(w in question_text for w in ["email"]):
            return self._resume.email
        elif any(w in question_text for w in ["phone", "mobile"]):
            return self._resume.phone
        elif "first name" in question_text:
            return self._resume.name.split()[0] if self._resume.name else ""
        elif "last name" in question_text:
            parts = self._resume.name.split()
            return parts[-1] if len(parts) > 1 else ""
        elif any(w in question_text for w in ["name"]):
            return self._resume.name
        elif any(w in question_text for w in ["location", "city"]):
            return self._settings.profile.current_location or "Pune"
        return "N/A"

    def _build_prompt(self, questions: list[dict[str, Any]], job: Job) -> str:
        """Build the LLM prompt for answering questions."""
        resume_text = f"""
Name: {self._resume.name}
Email: {self._resume.email}
Phone: {self._resume.phone}
Current Title: {self._resume.current_title}
Summary: {self._resume.summary}
Skills: {', '.join(self._resume.skills)}
Experience: {self._resume.total_experience_years} years
Education: {json.dumps(self._resume.education[:2], default=str)}
Current CTC: {self._settings.profile.current_ctc or 'Not specified'}
Expected CTC: {self._settings.profile.expected_ctc or 'Not specified'}
Notice Period: {self._settings.profile.notice_period or '30 days'}
Current Location: {self._settings.profile.current_location or 'Not specified'}
"""

        questions_text = ""
        for i, q in enumerate(questions, 1):
            q_text = q.get("question", "")
            f_type = q.get("field_type", "text")
            options = q.get("options", [])
            required = q.get("is_required", False)
            questions_text += f"\n{i}. [{f_type.upper()}] {q_text}"
            if options:
                questions_text += f"\n   Options: {', '.join(options)}"
            if required:
                questions_text += " (REQUIRED)"

        return f"""You are helping a job candidate fill out LinkedIn Easy Apply screening questions.

CANDIDATE PROFILE:
{resume_text.strip()}

JOB:
Title: {job.title}
Company: {job.company}

SCREENING QUESTIONS:
{questions_text}

Answer each question based on the candidate's profile.

CRITICAL FORMATTING RULES:
1. For dropdown/radio questions, your answer MUST match one of the provided options exactly.
2. For any candidate comfort, willingness, commute, shift, availability, or eligibility questions (e.g. "Are you comfortable...?", "Are you willing to...?", "Can you...?", "Do you have...?", "Are you authorized...?"), ALWAYS answer POSITIVELY (select "Yes" or equivalent positive option).
3. For questions asking about years of experience (e.g., "How many years of experience...", "experience with..."), notice period, salary/CTC, weekly hours, or any "how many" counts, your answer MUST be a plain numeric value (integer or decimal, e.g. "3", "700000", "0", "30"). Do NOT include any units, text, or explanations (do NOT write "3 years" or "I have 3 years", just write "3").
4. Keep other text answers concise and direct.

Return a JSON array of objects with:
- "question": the original question text
- "answer": your answer

Be honest but highlight strengths. For salary questions, use the configured values.
For yes/no questions about authorization or relocation, answer positively ("Yes").

Return ONLY the JSON array, no other text."""

    def _clean_and_validate_answer(self, question: dict[str, Any], answer: str) -> str:
        """
        Validates and cleans the answer based on the question type and expected response formats.
        """
        import re
        field_type = question.get("field_type", "text")
        question_text = question.get("question", "")
        options = question.get("options", [])
        
        answer_str = str(answer).strip()
        question_lower = question_text.lower()
        
        # 1. Handle radio/dropdown options matching
        if field_type in ("radio", "dropdown") and options:
            # Positive bias for candidate comfort / willingness / eligibility questions
            is_positive_q = any(
                w in question_lower
                for w in ["comfortable", "willing", "able", "authorized", "available",
                          "legally", "relocate", "shift", "commute", "do you", "are you", "can you"]
            )
            if is_positive_q:
                for opt in options:
                    if opt.lower().strip() == "yes":
                        return opt

            # If answer is in options (case insensitive), return the exact option from list
            for opt in options:
                if opt.lower().strip() == answer_str.lower():
                    return opt
            # If not matching exactly, check if any option is a substring of answer or vice versa
            for opt in options:
                if opt.lower().strip() in answer_str.lower() or answer_str.lower() in opt.lower().strip():
                    return opt
            # If still not found, use default logic to select from options
            return self._pick_from_options(question_text, options)
            
        # 2. Handle numeric text field cleaning
        if field_type == "text":
            # A. Experience years
            if any(w in question_lower for w in ["experience", "years", "yrs"]) and "notice" not in question_lower:
                # Extract first number (integer or decimal)
                numbers = re.findall(r'\b\d+(?:\.\d+)?\b', answer_str)
                if numbers:
                    val = float(numbers[0])
                    if val.is_integer():
                        return str(int(val))
                    return str(val)
                # Fallback to total experience from profile or settings
                total_exp = self._resume.total_experience_years
                if total_exp is not None:
                    return str(int(total_exp))
                return str(self._settings.profile.total_experience or "3")
                
            # B. Salary/CTC
            elif any(w in question_lower for w in ["salary", "ctc", "compensation"]):
                # Strip commas/dots/currency symbols and extract first number
                cleaned_ans = re.sub(r'[\$,\s]', '', answer_str)
                numbers = re.findall(r'\b\d+\b', cleaned_ans)
                if numbers:
                    return numbers[0]
                # Fallback to profile setting
                if "expected" in question_lower:
                    return self._settings.profile.expected_ctc or "700000"
                return self._settings.profile.current_ctc or "500000"
                
            # C. Notice period / joining
            elif any(w in question_lower for w in ["notice period", "notice", "joining", "days"]):
                numbers = re.findall(r'\b\d+\b', answer_str)
                if numbers:
                    return numbers[0]
                raw_np = self._settings.profile.notice_period or "30"
                raw_np_numbers = re.findall(r'\b\d+\b', raw_np)
                if raw_np_numbers:
                    return raw_np_numbers[0]
                if "immediate" in raw_np.lower() or "0" in raw_np:
                    return "0"
                return "30"
                
            # D. Hours per week
            elif any(w in question_lower for w in ["hours per week", "hours/week", "weekly hours"]):
                numbers = re.findall(r'\b\d+\b', answer_str)
                if numbers:
                    return numbers[0]
                return "40"
                
            # E. Phone number / mobile (if it ended up as text)
            elif any(w in question_lower for w in ["phone", "mobile", "telephone"]):
                # Keep only digits
                digits = re.sub(r'\D', '', answer_str)
                if len(digits) >= 10:
                    return digits
                return self._resume.phone or ""
                
            # F. General count questions like "how many"
            elif "how many" in question_lower:
                numbers = re.findall(r'\b\d+\b', answer_str)
                if numbers:
                    return numbers[0]
                return "1"
                
            # G. Location / city questions
            elif any(w in question_lower for w in ["location", "city", "residence"]):
                if "pune" in answer_str.lower() or not answer_str or answer_str.lower() in ("n/a", "none"):
                    return "Pune Division, Maharashtra, India"
                
        return answer_str

    def _parse_response(
        self, response: str, questions: list[dict[str, Any]]
    ) -> list[dict[str, str]]:
        """Parse LLM response and align answers with the original questions list."""
        parsed_list = []
        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]

            answers = json.loads(cleaned)
            if isinstance(answers, list):
                parsed_list = answers
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}")

        # Build a mapping from lowercased question text to the LLM's answer
        llm_answers_map = {}
        for a in parsed_list:
            if isinstance(a, dict):
                q_text = a.get("question", "").strip().lower()
                if q_text:
                    llm_answers_map[q_text] = a.get("answer", "")

        aligned_answers = []
        for q in questions:
            orig_q_text = q.get("question", "").strip()
            orig_q_lower = orig_q_text.lower()
            
            ans_val = None
            # 1. Exact match
            if orig_q_lower in llm_answers_map:
                ans_val = llm_answers_map[orig_q_lower]
            else:
                # 2. Substring match or closest match
                for lq, la in llm_answers_map.items():
                    if lq in orig_q_lower or orig_q_lower in lq:
                        ans_val = la
                        break
            
            # If not found or empty, get the default answer
            if ans_val is None:
                default_ans_list = self._default_answers([q])
                ans_val = default_ans_list[0]["answer"] if default_ans_list else ""
                logger.warning(f"Could not find LLM answer for question: '{orig_q_text}'. Using default: '{ans_val}'")
            
            # Post-process and clean the answer (e.g. numeric cleaning, dropdown option matching)
            ans_val = self._clean_and_validate_answer(q, ans_val)
            
            aligned_answers.append({
                "question": orig_q_text,
                "answer": ans_val
            })
            
        return aligned_answers
