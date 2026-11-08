"""Best-effort screening answers so a form never stalls on an empty field.

This is intentionally opt-in: ``application.answer_all_screening_questions``.
It only produces a value after the evidence-based answerers return nothing, and
it never overrides a confirmed answer.
"""

from __future__ import annotations

import re

from libs.common.screening_drafts import draft_answer
from libs.common.screening_intents import narrative_kind

_PLACEHOLDERS = (
    "select",
    "select an option",
    "choose",
    "please select",
    "please choose",
    "--",
    "-",
)

_DEMOGRAPHIC = (
    "gender",
    "ethnicity",
    "race",
    "veteran",
    "disability",
    "sexual orientation",
    "religion",
)

_NEGATIVE_POLARITY = (
    r"\b(?:require|need|requires|needs)\b[^?.]*\b(?:sponsor|visa)",
    r"\bvisa\s+sponsor",
    r"\bconvict",
    r"\bfelony\b",
    r"\bcriminal\b",
    r"\bdisability\b",
    r"\bveteran\b",
)

_LINK_FIELD = re.compile(r"\b(?:url|link|profile|portfolio|website|handle)\b", re.I)
_MONEY = re.compile(
    r"\b(?:ctc|salary|compensation|package|stipend|pay|inr|lpa)\b", re.I
)
_RATE = re.compile(r"\brate\b", re.I)
_RATE_CONTEXT = re.compile(
    r"\b(?:expected|current|monthly|hourly|daily|annual|yearly|per|inr|lpa|ctc|salary)\b",
    re.I,
)
_MONTHLY = re.compile(r"\bmonth(?:ly)?\b", re.I)


def _is_money(text):
    return bool(_MONEY.search(text)) or (
        bool(_RATE.search(text)) and bool(_RATE_CONTEXT.search(text))
    )


_RATING = re.compile(
    r"\bhow would you rate\b|\brate your\b[^?.]*\b(?:scale|out of|\d\s*(?:-|to)\s*\d)\b",
    re.I,
)
_PEOPLE = re.compile(
    r"\b(?:how many|number of|size of)\b[^?.]{0,60}"
    r"\b(?:people|persons?|team members?|members|employees|reports?|direct reports?)\b",
    re.I,
)
_NAME_FACT = re.compile(r"\b(?:full name|your name|name as per)\b", re.I)
_FIRST_NAME = re.compile(r"\b(?:first|given) name\b", re.I)
_LAST_NAME = re.compile(r"\b(?:last|family|sur)name\b", re.I)
_EDUCATION_FACT = re.compile(r"\b(?:highest|completed|qualification)\b", re.I)
_COMPANY_FACT = re.compile(
    r"\b(?:current|present)\b[^?.]*\b(?:company|employer|organization)\b"
    r"|\b(?:company|employer) name\b",
    re.I,
)
_LOCATION_FACT = re.compile(r"\b(?:location|city|based|located|reside|residing)\b", re.I)
_TECH_LIST = re.compile(
    r"\b(?:list|which|what)\b[^?.]*\b(?:tools?|platforms?|technologies|tech stack|skills?)\b",
    re.I,
)
_DATE_ANSWER = re.compile(
    r"\blast working day\b|\bstart(?:ing)? date\b|\bdate of joining\b|\bjoining date\b"
    r"|\bwhen can you (?:start|join)\b|\bwhen are you able to (?:start|join)\b"
    r"|\bhow soon can you (?:start|join)\b|\bavailability to (?:start|join)\b"
    r"|\bavailable to (?:start|join)\b|\bearliest (?:start|joining)\b",
    re.I,
)


def _highest_degree(candidate):
    entries = [entry for entry in getattr(candidate, "education", []) or [] if isinstance(entry, dict)]

    def year(entry):
        match = re.search(r"(?:19|20)\d{2}", str(entry.get("year") or entry.get("end_year") or ""))
        return int(match[0]) if match else 0

    for entry in sorted(entries, key=year, reverse=True):
        degree = str(entry.get("degree") or entry.get("qualification") or "").strip()
        if degree:
            return degree
    return ""


def _current_company(candidate):
    entries = [
        entry for entry in getattr(candidate, "work_experience", []) or [] if isinstance(entry, dict)
    ]
    current = next(
        (entry for entry in entries if "present" in str(entry.get("duration", "")).casefold()),
        None,
    )
    entry = current or (entries[0] if entries else {})
    return str(entry.get("company") or entry.get("employer") or "").strip()


def _skills_text(candidate, limit=10):
    values = [
        *getattr(candidate, "skills", []),
        *getattr(candidate, "technical_skills", []),
    ]
    unique = list(dict.fromkeys(str(value).strip() for value in values if str(value or "").strip()))
    return ", ".join(unique[:limit])


def _rating_value(text):
    match = re.search(r"\b(\d{1,2})\s*(?:-|to|–|—|/)\s*(\d{1,2})\b", text)
    if match:
        low, high = int(match[1]), int(match[2])
        if 1 <= low < high <= 100:
            return str(high)
    match = re.search(r"\bout of (\d{1,2})\b", text)
    return match[1] if match else "10"


_AFFIRMATIVE = re.compile(
    r"\b(?:yes|agree|authoriz|authoris|eligible|willing|open to|available|confirm|accept|"
    r"acknowledge|i have read|i understand|immediate)\b",
    re.I,
)
_NEGATIVE = re.compile(r"^(?:no\b|not |none\b|decline|prefer not|do not|don't|disagree)", re.I)


def _text(question):
    return str(question.get("question") or "").casefold().strip()


def _options(question):
    raw = question.get("options") or []
    values = [
        str(option.get("text", option)) if isinstance(option, dict) else str(option)
        for option in raw
    ]
    return [value.strip() for value in values if value.strip()]


def _placeholder(option):
    lowered = option.casefold().strip(" .:*")
    return not lowered or lowered in _PLACEHOLDERS


def _wants_negative(text):
    return any(re.search(pattern, text) for pattern in _NEGATIVE_POLARITY)


def _years(settings, candidate):
    from libs.common.resume_facts import duration_years

    stated = duration_years(getattr(settings.profile, "total_experience", ""))
    if stated is None:
        stated = getattr(candidate, "total_experience_years", None)
    return stated


def _option_number(option):
    match = re.search(r"(\d+(?:\.\d+)?)", option)
    return float(match[1]) if match else None


def _experience_option(options, text, settings, candidate):
    if not re.search(r"\b(?:experience|years?|months?)\b", text):
        return ""
    numbers = [_option_number(option) for option in options]
    if any(number is None for number in numbers):
        return ""
    stated = _years(settings, candidate)
    if stated is None:
        return ""
    wanted = stated
    if "month" in text and "year" not in text:
        wanted = stated * 12
    affordable = [
        (number, option)
        for number, option in zip(numbers, options, strict=True)
        if number is not None and number <= wanted
    ]
    if affordable:
        return max(affordable, key=lambda item: item[0])[1]
    return min(
        (
            (number, option)
            for number, option in zip(numbers, options, strict=True)
            if number is not None
        ),
        key=lambda item: item[0],
    )[1]


def _fact_options(options, text, settings, candidate):
    """Match the option list against a fact the profile already states."""
    profile = settings.profile
    facts = []
    if "location" in text or "city" in text:
        facts.extend(
            [
                *getattr(profile, "preferred_locations", []),
                getattr(profile, "current_city", ""),
                getattr(profile, "current_location", ""),
            ]
        )
    if "notice" in text:
        facts.append(getattr(profile, "notice_period", ""))
    if "ctc" in text or "salary" in text or "compensation" in text:
        facts.extend([getattr(profile, "expected_ctc", ""), getattr(profile, "current_ctc", "")])
    for fact in facts:
        target = str(fact or "").strip().casefold()
        if not target:
            continue
        for option in options:
            lowered = option.casefold()
            if lowered == target or lowered.startswith(target + ","):
                return option
    return ""


def _choice_answer(question, settings, candidate):
    text = _text(question)
    options = [option for option in _options(question) if not _placeholder(option)]
    kind = question.get("field_type") or question.get("type") or ""
    if not options:
        return "No" if _wants_negative(text) else "Yes"
    if kind == "checkbox" and len(options) == 1:
        # A lone checkbox is a consent/declaration control, not a list.
        return "No" if _wants_negative(text) else "Yes"

    if any(term in text for term in _DEMOGRAPHIC):
        for option in options:
            if re.search(
                r"decline|prefer not|don't wish|do not wish|not to say|rather not", option, re.I
            ):
                return option

    fact = _fact_options(options, text, settings, candidate)
    if fact:
        return fact

    experience = _experience_option(options, text, settings, candidate)
    if experience:
        return experience

    if _wants_negative(text):
        for option in options:
            if _NEGATIVE.search(option):
                return option
        for option in options:
            if re.search(r"\bno\b", option, re.I):
                return option
    else:
        for option in options:
            if re.fullmatch(r"yes[.!]?", option.strip(), re.I):
                return option
    for option in options:
        if _AFFIRMATIVE.search(option):
            return option
    for option in options:
        if not _NEGATIVE.search(option):
            return option
    return options[0]


def _notice_days(settings):
    value = str(getattr(settings.profile, "notice_period", "") or "").casefold()
    if value.strip() in ("immediate", "immediately", "0", "none"):
        return "0"
    match = re.search(r"(\d+)", value)
    if not match:
        return "0"
    days = int(match[1])
    if "week" in value:
        days *= 7
    elif "month" in value:
        days *= 30
    return str(days)


def _availability_answer(settings):
    """Earliest start date: saved last working day, else the notice period."""
    profile = settings.profile
    last_day = str(getattr(profile, "last_working_date", "") or "").strip()
    if last_day:
        return last_day
    notice = str(getattr(profile, "notice_period", "") or "").strip()
    return notice or "Immediate"


def _ctc_amount(text, settings):
    profile = settings.profile
    raw = profile.current_ctc if "current" in text else profile.expected_ctc
    raw = raw or profile.expected_ctc or profile.current_ctc
    value = str(raw or "").casefold()
    numbers = re.findall(r"\d+(?:\.\d+)?", value)
    if not numbers:
        return "0"
    amount = float(numbers[0])
    if "lpa" in value or "lakh" in value or "lac" in value:
        amount *= 100000
    elif "k" in value:
        amount *= 1000
    rounded = round(amount)
    if abs(amount - rounded) < 0.01:
        return str(rounded)
    return format(amount, ".2f").rstrip("0").rstrip(".")


def _number_answer(text, settings, candidate):
    if "month" in text and "experience" in text:
        stated = _years(settings, candidate)
        return str(max(int(round(stated * 12)), 1)) if stated is not None else "0"
    if "year" in text and "experience" in text:
        stated = _years(settings, candidate)
        return format(stated, "g") if stated is not None else "0"
    if "experience" in text:
        stated = _years(settings, candidate)
        return format(stated, "g") if stated is not None else "0"
    if "notice" in text:
        return _notice_days(settings)
    if _is_money(text):
        return _money_amount(text, settings)
    return "0"


def _money_amount(text, settings):
    """Annual, monthly, daily or hourly money amount from the saved CTC."""
    annual = float(_ctc_amount(text, settings))
    if _MONTHLY.search(text):
        amount = annual / 12
    elif re.search(r"\b(?:per\s+hour|hourly)\b", text):
        amount = annual / 2080
    elif re.search(r"\b(?:per\s+day|daily)\b", text):
        amount = annual / 260
    elif re.search(r"\b(?:in|as)\s+(?:lpa|lakhs?|lacs?)\b", text):
        amount = annual / 100000
    else:
        amount = annual
    return format(round(amount, 2), "g")


def _link(text, settings, candidate):
    key = "github_url" if "github" in text else "linkedin_url"
    value = str(getattr(settings.profile, key, "") or "").strip()
    if value:
        return value
    pattern = r"github\.com/[\w.-]+" if key == "github_url" else r"linkedin\.com/in/[\w.-]+"
    match = re.search(pattern, str(getattr(candidate, "raw_text", "") or ""), re.I)
    return "https://" + match[0].rstrip(").,;:") if match else ""


def _location_answer(settings):
    profile = settings.profile
    values = [
        getattr(profile, "current_city", ""),
        getattr(profile, "current_location", ""),
        *getattr(profile, "preferred_locations", []),
    ]
    return next((str(value).strip() for value in values if str(value or "").strip()), "")


def _profile_sentence(text, settings, candidate, question):
    title = getattr(candidate, "current_title", "") or "Software Engineer"
    skills = list(
        dict.fromkeys(
            [*getattr(candidate, "skills", []), *getattr(candidate, "technical_skills", [])]
        )
    )
    if any(word in text for word in ("headline", "current title", "job title", "designation")):
        answer = title if not skills else f"{title} | {', '.join(skills[:2])}"
    else:
        years = _years(settings, candidate)
        experience = f" with {years:g}+ years of experience" if years else ""
        answer = f"{title}{experience}"
        if skills:
            answer += f" in {', '.join(skills[:4])}"
        answer += "."
    limit = question.get("max_length")
    if isinstance(limit, int) and limit > 0 and len(answer) > limit:
        answer = answer[:limit].rsplit(" ", 1)[0].rstrip(" ,;|") or answer[:limit]
    return answer


def _text_answer(question, settings, candidate, job):
    text = _text(question)
    if narrative_kind(text) or any(
        word in text
        for word in (
            "summary",
            "cover letter",
            "additional information",
            "why ",
            "describe",
            "tell us",
        )
    ):
        draft = draft_answer(question, settings, candidate, job)
        if draft:
            return draft
    if _RATING.search(text):
        return _rating_value(text)
    if "last working day" in text:
        value = str(getattr(settings.profile, "last_working_date", "") or "").strip()
        return value or "Immediate"
    if _DATE_ANSWER.search(text):
        return _availability_answer(settings)
    if _PEOPLE.search(text):
        return "2"
    if (
        re.search(r"\b(?:how many|number of)\b", text)
        or re.search(r"\bhow much\b[^?.]*\bexperience\b", text)
        or question.get("input_type") == "number"
        or question.get("field_type") == "number"
        or "notice" in text
        or _is_money(text)
    ):
        return _number_answer(text, settings, candidate)
    # A skill question mentioning GitHub Actions is still a number question,
    # not a profile-link box. Only an explicit link/profile prompt gets a URL.
    if _LINK_FIELD.search(text) or text.strip(" :*.-") in ("github", "linkedin"):
        link = _link(text, settings, candidate)
        if link:
            return link
    if re.match(r"^(?:do|does|are|is|have|has|will|would|can|could|did)\b", text):
        return "No" if _wants_negative(text) else "Yes"
    name = str(getattr(candidate, "name", "") or "").strip()
    if _FIRST_NAME.search(text) and name:
        return name.split()[0]
    if _LAST_NAME.search(text) and name:
        return name.split()[-1]
    if (_NAME_FACT.search(text) or text.strip(" :*.-") == "name") and name:
        return name
    if _EDUCATION_FACT.search(text):
        degree = _highest_degree(candidate)
        if degree:
            return degree
    if _COMPANY_FACT.search(text):
        company = _current_company(candidate)
        if company:
            return company
    if _LOCATION_FACT.search(text):
        location = _location_answer(settings)
        if location:
            return location
    if _TECH_LIST.search(text):
        skills = _skills_text(candidate)
        if skills:
            return skills
    email = str(getattr(candidate, "email", "") or "").strip()
    if "email" in text and email:
        return email
    phone = str(getattr(candidate, "phone", "") or "").strip()
    if any(word in text for word in ("phone", "mobile", "contact number")) and phone:
        return phone
    return _profile_sentence(text, settings, candidate, question)


def positive_answer(question, settings, candidate=None, job=None):
    """Return a non-empty, application-friendly answer for one screening field."""
    if candidate is None:
        return "Yes"
    kind = question.get("field_type") or question.get("type") or "text"
    if kind in ("radio", "dropdown", "checkbox") or _options(question):
        return _choice_answer(question, settings, candidate)
    return _text_answer(question, settings, candidate, job)


def numeric_answer(question, settings, candidate=None):
    """Positive number for a text field whose form rejects a prose answer.

    LinkedIn sometimes renders numeric screening questions as plain text
    inputs and only reveals the requirement after the first value is rejected.
    Whatever the wording, this must return a non-empty number.
    """
    text = _text(question)
    if _DATE_ANSWER.search(text):
        # A date or "Immediate" is never a number; a numeric fallback would
        # turn an available-to-start date into 0.
        return ""
    if _RATING.search(text):
        return _rating_value(text)
    if _PEOPLE.search(text):
        return "2"
    if "notice" in text:
        return _notice_days(settings)
    if _is_money(text):
        return _money_amount(text, settings)
    years = _years(settings, candidate) if candidate is not None else None
    if years is None:
        return "1"
    if "month" in text and "year" not in text:
        return str(max(int(round(years * 12)), 1))
    return format(max(float(years), 1), "g")


def needs_numeric(question):
    """True when an answer must be a number rather than prose or a URL."""
    text = _text(question)
    if question.get("input_type") == "number" or question.get("field_type") == "number":
        return True
    if _DATE_ANSWER.search(text):
        # Dates and availability are answered with a date or "Immediate",
        # even when the wording also contains "notice".
        return False
    if _RATING.search(text) or _PEOPLE.search(text):
        return True
    if "notice" in text or _is_money(text):
        return True
    if re.search(r"\b(?:how many|number of)\b", text):
        return True
    if re.search(r"\bhow much\b[^?.]*\bexperience\b", text):
        return True
    return bool(
        re.search(
            r"\b(?:years?|months?)\b[^?.]*\bexperience\b"
            r"|\bexperience\b[^?.]*\b(?:years?|months?)\b",
            text,
        )
    )
