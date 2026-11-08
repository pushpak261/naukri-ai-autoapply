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
    r"\b(?:ctc|salary|compensation|package|stipend|pay|rate|inr|lpa)\b", re.I
)
_MONTHLY = re.compile(r"\bmonth(?:ly)?\b", re.I)

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
        wanted = (stated - int(stated)) * 12
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
        return str(int(round((stated - int(stated)) * 12)) % 12) if stated is not None else "0"
    if "year" in text and "experience" in text:
        stated = _years(settings, candidate)
        return format(stated, "g") if stated is not None else "0"
    if "notice" in text:
        return _notice_days(settings)
    if _MONEY.search(text):
        return _money_amount(text, settings)
    return "0"


def _money_amount(text, settings):
    """Annual or monthly money amount from the saved CTC facts."""
    amount = float(_ctc_amount(text, settings))
    if _MONTHLY.search(text):
        amount /= 12
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
    if (
        re.search(r"\b(?:how many|number of)\b", text)
        or question.get("input_type") == "number"
        or question.get("field_type") == "number"
        or "notice" in text
        or _MONEY.search(text)
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
    if "location" in text or "city" in text:
        location = _location_answer(settings)
        if location:
            return location
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
    if "notice" in text:
        return _notice_days(settings)
    if _MONEY.search(text):
        return _money_amount(text, settings)
    years = _years(settings, candidate) if candidate is not None else None
    if years is None:
        return "1"
    if "month" in text and "year" not in text:
        months = int(round((years - int(years)) * 12))
        return str(max(months, 1))
    return format(max(float(years), 1), "g")
