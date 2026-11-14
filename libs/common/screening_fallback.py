"""Best-effort screening answers so a form never stalls on an empty field.

This is intentionally opt-in: ``application.answer_all_screening_questions``.
It only produces a value after the evidence-based answerers return nothing, and
it never overrides a confirmed answer.
"""

from __future__ import annotations

import re

from libs.common.local_matching import contains_skill, normalize_skill
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
    "age",
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
    r"\bcurrent\s+or\s+former\s+employee\b",
    r"\bemployer\b[^?.]*\bpartner\b",
    r"\bapplied\s+to\s+or\s+been\s+referred\b",
    r"\breferr(?:ed|al)\b",
    r"\bintellectual\s+property\b",
    r"\boutside\s+employment\b",
    r"\bboard\s+memberships?\b",
    r"\bpersonal\s+relationships?\b",
    r"\bconflict\s+of\s+interest\b",
)

_LINK_FIELD = re.compile(r"\b(?:url|link|profile|portfolio|website|handle)\b", re.I)
_MONEY = re.compile(
    r"\b(?:ctc|salary|compensation|package|stipend|pay|income|inr|lpa)\b", re.I
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
_EXPERIENCE_YEARS = re.compile(
    r"\b(?:years?|months?)\b[^?.]*\bexperience\b"
    r"|\bexperience\b[^?.]*\b(?:years?|months?)\b",
    re.I,
)
_RATING_POSITIVE = re.compile(
    r"\b(?:excellent|outstanding|very good|strong|advanced|expert|great|high)\b", re.I
)
_SERVING_NOTICE = re.compile(
    r"\bserving\s+(?:your\s+)?notice\b|\bcurrently\s+(?:on|serving)\s+(?:a\s+)?notice\b"
    r"|\bon\s+(?:a\s+)?notice\b",
    re.I,
)
_OFFER_IN_HAND = re.compile(
    r"\boffers?\s+in\s+hand\b|\bcompeting\s+offers?\b|\bother\s+offers?\b", re.I
)
_CONDITIONAL_YES = re.compile(
    r"^\s*if\s+(?:you\s+(?:have\s+)?(?:answered|selected|chose)\s+)?['\"]?yes\b", re.I
)
_CONDITIONAL_NO = re.compile(
    r"^\s*if\s+(?:you\s+(?:have\s+)?(?:answered|selected|chose)\s+)?['\"]?no\b", re.I
)
_CONDITIONAL_SERVING = re.compile(
    r"^\s*if\s+(?:you\s+(?:are|have)\s+)?(?:already\s+)?serving\s+(?:a\s+)?notice\b",
    re.I,
)
# Follow-ups that ask for a referrer, a former manager or the names of
# relatives are only answerable when the preceding yes/no fact is true. No
# such fact is saved, so they must be N/A rather than the candidate's name.
_FOLLOW_UP_DETAIL = re.compile(
    r"^\s*if\s+['\"]?yes\b"
    r"|^\s*if\s+you\s+(?:were\s+referred|have\s+been\s+referred|answered\s+['\"]?yes)"
    r"|\b(?:name|names|details)\s+of\s+(?:the\s+)?(?:referr|individual|person\s+who\s+referred)"
    r"|\bwho\s+(?:referred|is\s+your\s+referrer)"
    r"|\breferrer\b"
    r"|\bname\s+of\s+your\s+(?:current|former|previous|most\s+recent)\s+manager"
    r"|\brelationship\s+to\s+you\b",
    re.I,
)
_YES_NO = re.compile(
    r"(?:^|[:;.?!]\s*)(?:do|does|are|is|were|was|have|has|will|would|can|could|did|should|may|am)\b",
    re.I,
)
_CURRENT_IN = re.compile(
    r"\b(?:currently\s+)?(?:based|residing|reside|living|live|located|staying|stay)\s+in\s+"
    r"([^?.!,;]+)",
    re.I,
)
_WORK_AUTH = re.compile(
    r"\b(?:right|authoris\w*|authoriz\w*|eligible|permit(?:ted)?)\s+to\s+work\b"
    r"|\bwork\s+(?:permit|authori[sz]ation)\b",
    re.I,
)
_CERTIFICATION = re.compile(r"\bcertif(?:icate|ication|ied|icates|ications)?\b", re.I)
_OPTIONAL_PROMPT = re.compile(
    r"\bis there anything else\b"
    r"|\banything else (?:you(?:'d| would) like|we should know)\b"
    r"|\banything you(?:'d| would) like us to know\b",
    re.I,
)
_SKILL_PHRASES = (
    re.compile(r"\bexperience\s+(?:do you have\s+)?with\s+(.+?)(?:\?|$)", re.I),
    re.compile(r"\b(?:working|work)\s+with\s+(.+?)(?:\?|$)", re.I),
    re.compile(
        r"\bhands[- ]on\s+(.+?)\s+(?:development\s+|engineering\s+)?experience\b", re.I
    ),
    re.compile(
        r"\b(?:years?|months?)\s+of\s+(.+?)\s+(?:development\s+|engineering\s+)?experience\b",
        re.I,
    ),
    re.compile(r"\bworked\s+on\s+(.+?)(?:\?|$)", re.I),
)
_GENERIC_EXPERIENCE_WORDS = {
    "additional",
    "and",
    "application",
    "architecture",
    "back",
    "backend",
    "both",
    "cloud",
    "commercial",
    "complex",
    "corporate",
    "development",
    "end",
    "engineering",
    "field",
    "for",
    "front",
    "frontend",
    "full",
    "hands",
    "in",
    "industry",
    "information",
    "integration",
    "integrations",
    "internship",
    "it",
    "large",
    "my",
    "non",
    "of",
    "on",
    "or",
    "overall",
    "practical",
    "product",
    "professional",
    "related",
    "relevant",
    "scale",
    "service",
    "services",
    "similar",
    "small",
    "software",
    "stack",
    "system",
    "systems",
    "technical",
    "technology",
    "the",
    "to",
    "total",
    "web",
    "with",
    "work",
    "your",
}
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
    r"|\bavailable to (?:start|join)\b|\bearliest (?:start|joining)\b"
    r"|\bavailable\s+time\s+to\s+(?:start|join)\b|\btime\s+to\s+(?:start|join)\b",
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


def _option_for(options, value):
    target = str(value).strip().casefold()
    return next((option for option in options if option.strip().casefold() == target), "")


def _offer_in_hand_answer(text):
    """An offer is a factual status, not a preference; never claim one by default."""
    if not _OFFER_IN_HAND.search(text):
        return ""
    if re.search(
        r"\b(?:list|name|names|details|company|companies|where|when|which|describe)\b", text
    ):
        return ""
    return "No"


def _skill_phrase(text):
    for pattern in _SKILL_PHRASES:
        match = pattern.search(text)
        if match:
            phrase = re.sub(r"\s+", " ", match[1]).lstrip(" ,:;*").rstrip(" .,:;*")
            if phrase:
                return phrase
    return ""


def _concrete_skill_phrase(phrase):
    lowered = phrase.casefold().strip()
    if lowered in {"c", "r"}:
        return True
    words = [
        word
        for word in re.findall(r"[a-z0-9+#./]+", lowered)
        if len(word) > 1 and word not in _GENERIC_EXPERIENCE_WORDS
    ]
    return bool(words)


def _supported_skill_phrase(phrase, candidate):
    skills = [
        *getattr(candidate, "skills", []),
        *getattr(candidate, "technical_skills", []),
    ]
    for skill in skills:
        variants = {normalize_skill(skill)}
        variants.update(
            normalized
            for part in re.split(r"[/,&()]", str(skill))
            if (normalized := normalize_skill(part))
        )
        if any(variant and contains_skill(phrase, variant) for variant in variants):
            return True
    return False


def _unsupported_skill_years(text, settings, candidate):
    """Zero years for a concrete skill the resume does not support."""
    phrase = _skill_phrase(text)
    if not phrase or not _concrete_skill_phrase(phrase):
        return ""
    if _supported_skill_phrase(phrase, candidate):
        return ""
    years = _years(settings, candidate)
    return "0" if years is not None else ""


def _unsupported_skill_claim(text, candidate):
    """True for an explicit 'experience with X' claim the resume cannot support."""
    phrase = _skill_phrase(text)
    return bool(
        phrase
        and _concrete_skill_phrase(phrase)
        and not _supported_skill_phrase(phrase, candidate)
    )


def _target_in_option(target, option):
    target = str(target or "").strip().casefold()
    if not target:
        return False
    if re.search(r"(?<![\w+#])" + re.escape(target) + r"(?![\w+#])", option.casefold()):
        return target not in _GENERIC_EXPERIENCE_WORDS
    return False


def _multi_checkbox_answer(question, options, settings, candidate):
    """Pick exact option labels for a multi-select group (newline-separated)."""
    text = _text(question)
    profile = settings.profile
    yes = _option_for(options, "Yes")
    no = _option_for(options, "No")
    if len(options) == 2 and yes and no:
        return no if _wants_negative(text) else yes

    targets = []
    if any(word in text for word in ("location", "city", "based", "relocate", "work from")):
        targets.extend(
            [
                *getattr(profile, "preferred_locations", []),
                getattr(profile, "current_city", ""),
                getattr(profile, "current_location", ""),
            ]
        )
    if any(
        word in text
        for word in (
            "skill",
            "technolog",
            "tool",
            "platform",
            "language",
            "framework",
            "database",
            "stack",
        )
    ):
        targets.extend(
            [
                *getattr(candidate, "skills", []),
                *getattr(candidate, "technical_skills", []),
            ]
        )
    if any(word in text for word in ("degree", "qualification", "education")):
        targets.extend(
            str(entry.get("degree") or entry.get("qualification") or "")
            for entry in getattr(candidate, "education", []) or []
            if isinstance(entry, dict)
        )

    picked = [
        option
        for option in options
        if any(_target_in_option(target, option) for target in targets)
    ]
    if picked:
        return "\n".join(dict.fromkeys(picked))
    affirmative = [
        option for option in options if _AFFIRMATIVE.search(option) and not _NEGATIVE.search(option)
    ]
    if affirmative:
        return "\n".join(affirmative)
    return next((option for option in options if not _NEGATIVE.search(option)), options[0])


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


def _option_numbers(option):
    return [float(number) for number in re.findall(r"\d+(?:\.\d+)?", str(option))]


def _pick_numeric_option(options, target):
    """Choose the option that contains (or exactly matches) a target number."""
    exact = []
    ranges = []
    for option in options:
        numbers = _option_numbers(option)
        if len(numbers) == 1 and numbers[0] == target:
            exact.append(option)
        elif len(numbers) >= 2 and re.search(r"[-–]|\bto\b", option, re.I):
            low, high = min(numbers[0], numbers[1]), max(numbers[0], numbers[1])
            if low <= target <= high:
                ranges.append((high - low, option))
    if exact:
        return exact[0]
    if ranges:
        return min(ranges, key=lambda item: item[0])[1]
    return ""


def _option_annual_range(option, question_text=""):
    """Annual-rupee span an option represents, honoring LPA/monthly/hourly units."""
    label = str(option).casefold().replace(",", "")
    question = str(question_text).casefold()
    numbers = _option_numbers(label)
    if not numbers:
        return None
    scale = 1.0
    unit_seen = False
    if re.search(r"\b(?:lpa|lakhs?|lacs?)\b", label):
        scale, unit_seen = 100000.0, True
    elif re.search(r"\b(?:crores?|cr)\b", label):
        scale, unit_seen = 10000000.0, True
    elif re.search(r"(?<!\w)k(?!\w)", label):
        scale, unit_seen = 1000.0, True
    if re.search(r"\bper\s+hour\b|\bhourly\b", label):
        scale, unit_seen = scale * 2080, True
    elif re.search(r"\bper\s+day\b|\bdaily\b", label):
        scale, unit_seen = scale * 260, True
    elif re.search(r"\bper\s+month\b|\bmonthly\b", label):
        scale, unit_seen = scale * 12, True
    if not unit_seen:
        if re.search(r"\b(?:lpa|lakhs?|lacs?)\b", question):
            scale = 100000.0
        elif re.search(r"\b(?:crores?|cr)\b", question):
            scale = 10000000.0
        if re.search(r"\bper\s+hour\b|\bhourly\b", question):
            scale *= 2080
        elif re.search(r"\bper\s+day\b|\bdaily\b", question):
            scale *= 260
        elif re.search(r"\bper\s+month\b|\bmonthly\b", question):
            scale *= 12
    values = sorted(number * scale for number in numbers[:2])
    low, high = values[0], values[-1]
    if re.search(r"\b(?:less than|under|below)\b", label):
        low = 0.0
    elif (
        re.search(r"\b(?:more than|above|over)\b", label)
        or "+" in label
        or re.search(r"\bat least\b", label)
    ):
        high = float("inf")
    return low, high


def _money_option(options, text, settings):
    annual = float(_ctc_amount(text, settings))
    if annual <= 0:
        return ""
    ranges = []
    singles = []
    for option in options:
        span = _option_annual_range(option, text)
        if not span:
            continue
        low, high = span
        if low <= annual <= high:
            ranges.append((high - low, option))
        if low == high:
            singles.append((abs(low - annual), option))
    if ranges:
        return min(ranges, key=lambda item: item[0])[1]
    if singles:
        return min(singles, key=lambda item: item[0])[1]
    return ""


def _notice_option(options, settings):
    days = int(_notice_days(settings))
    picked = _pick_numeric_option(options, float(days))
    if picked:
        return picked
    if days == 0:
        lowest = [
            (min(numbers), option)
            for option in options
            if (numbers := _option_numbers(option))
        ]
        if lowest:
            return min(lowest, key=lambda item: item[0])[1]
    return ""


def _experience_span(option):
    """Year span an option represents, including ranges and open-ended scales."""
    label = str(option).casefold()
    numbers = _option_numbers(label)
    if not numbers:
        return None
    if re.search(r"\b(?:more than|above|over|at least)\b|\+", label):
        return numbers[0], float("inf"), False
    if re.search(r"\b(?:less than|under|below|up to)\b", label):
        return 0.0, numbers[0], False
    if len(numbers) >= 2 and re.search(r"[-–]|\bto\b", label):
        low, high = sorted(numbers[:2])
        return low, high, False
    return numbers[0], numbers[0], True


def _experience_option(options, text, settings, candidate):
    if not re.search(r"\b(?:experience|years?|months?)\b", text):
        return ""
    stated = _years(settings, candidate)
    if stated is None:
        return ""
    wanted = stated
    if "month" in text and "year" not in text:
        wanted = stated * 12
    if "additional" in text:
        # Months/years beyond the saved total are zero.
        wanted = 0
    spans = [
        (span, option)
        for option in options
        if (span := _experience_span(option)) is not None
    ]
    if not spans:
        return ""
    exact = [
        option
        for (low, high, scalar), option in spans
        if scalar and low == wanted
    ]
    if exact:
        return exact[0]
    containing = [
        (high - low, high, option)
        for (low, high, _scalar), option in spans
        if low <= wanted <= high
    ]
    if containing:
        return min(containing, key=lambda item: (item[0], item[1]))[2]
    below = [
        (low, option)
        for (low, _high, _scalar), option in spans
        if low <= wanted
    ]
    if below:
        return max(below, key=lambda item: item[0])[1]
    return min(spans, key=lambda item: item[0][0])[1]


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
    if "email" in text:
        facts.extend([getattr(profile, "email", ""), getattr(candidate, "email", "")])
    if "country code" in text:
        phone = str(getattr(profile, "phone", "") or getattr(candidate, "phone", "") or "")
        match = re.search(r"^\s*\+\s*(\d{1,3})", phone)
        if match:
            code = match[1]
            for option in options:
                if re.search(r"(?<!\d)" + re.escape(code) + r"(?!\d)", option):
                    return option
    for fact in facts:
        target = str(fact or "").strip().casefold()
        if not target:
            continue
        for option in options:
            lowered = option.casefold()
            if (
                lowered == target
                or lowered.startswith(target + ",")
                or lowered.startswith(target + " (")
            ):
                return option
    return ""


def _choice_answer(question, settings, candidate):
    text = _text(question)
    options = [option for option in _options(question) if not _placeholder(option)]
    kind = question.get("field_type") or question.get("type") or ""
    if not options:
        if _unsupported_skill_claim(text, candidate):
            return "No"
        return "No" if _wants_negative(text) else "Yes"
    if kind == "checkbox" and len(options) == 1:
        # A lone checkbox is a consent/declaration control, not a list.
        if _unsupported_skill_claim(text, candidate):
            return "No"
        return "No" if _wants_negative(text) else "Yes"

    offer = _offer_in_hand_answer(text)
    if offer:
        return _option_for(options, offer) or next(
            (option for option in options if _NEGATIVE.search(option)), offer
        )

    place = _location_yes_no_answer(text, settings)
    if place:
        picked = _option_for(options, place)
        if picked:
            return picked

    authorization = _work_authorization_answer(text, settings)
    if authorization:
        picked = _option_for(options, authorization)
        if picked:
            return picked

    if any(term in text for term in _DEMOGRAPHIC):
        for option in options:
            if re.search(
                r"decline|prefer not|don't wish|do not wish|not to say|rather not", option, re.I
            ):
                return option

    serving = _serving_notice_answer(text, settings, options)
    if serving:
        return serving

    certification = _certification_choice(text, options, candidate)
    if certification:
        return certification

    optional = _optional_prompt_answer(text)
    if optional:
        picked = _option_for(options, optional) or next(
            (option for option in options if _NEGATIVE.search(option)), ""
        )
        if picked:
            return picked

    if _unsupported_skill_claim(text, candidate):
        no = _option_for(options, "No") or next(
            (option for option in options if _NEGATIVE.search(option)), ""
        )
        if no:
            return no

    if kind == "checkbox":
        return _multi_checkbox_answer(question, options, settings, candidate)

    fact = _fact_options(options, text, settings, candidate)
    if fact:
        return fact

    experience = _experience_option(options, text, settings, candidate)
    if experience:
        return experience

    if _RATING.search(text):
        picked = _pick_numeric_option(options, float(_rating_value(text)))
        if picked:
            return picked
        positive = next((option for option in options if _RATING_POSITIVE.search(option)), "")
        if positive:
            return positive

    if _PEOPLE.search(text) and not _EXPERIENCE_YEARS.search(text):
        picked = _pick_numeric_option(options, 2)
        if picked:
            return picked
        positive = next(
            (
                option
                for option in options
                if _option_numbers(option) and min(_option_numbers(option)) > 0
            ),
            "",
        )
        if positive:
            return positive

    conditional = _conditional_option(options, text, settings)
    if conditional:
        return conditional

    if _is_money(text):
        picked = _money_option(options, text, settings)
        if picked:
            return picked

    if "notice" in text:
        picked = _notice_option(options, settings)
        if picked:
            return picked

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


def _is_serving_notice(settings):
    serving = getattr(settings.profile, "serving_notice", None)
    if serving is not None:
        return bool(serving)
    notice = str(getattr(settings.profile, "notice_period", "") or "").casefold().strip()
    return notice not in ("", "immediate", "immediately", "0", "none")


def _serving_notice_answer(text, settings, options=None):
    """A yes/no notice question, never a duration and never a guessed Yes."""
    if not _SERVING_NOTICE.search(text):
        return ""
    if re.search(r"\b(?:last working|last day|date|when|what will be)\b", text, re.I):
        return ""
    answer = "Yes" if _is_serving_notice(settings) else "No"
    if options:
        return next(
            (option for option in options if option.strip().casefold() == answer.casefold()), ""
        )
    return answer


def _conditional_answer(text, settings):
    """Follow-up questions about a previous Yes/No answer are not yes/no facts."""
    matches = bool(
        _CONDITIONAL_YES.search(text)
        or _CONDITIONAL_NO.search(text)
        or _CONDITIONAL_SERVING.search(text)
        or _FOLLOW_UP_DETAIL.search(text)
    )
    if not matches:
        return ""
    if _PEOPLE.search(text) or _DATE_ANSWER.search(text):
        return ""
    if _CONDITIONAL_SERVING.search(text) and _is_serving_notice(settings):
        return ""
    return "N/A"


def _conditional_option(options, text, settings):
    answer = _conditional_answer(text, settings)
    if not answer:
        return ""
    exact = _option_for(options, answer)
    if exact:
        return exact
    for preferred in ("not applicable", "none", "no"):
        picked = next(
            (option for option in options if option.strip().casefold().startswith(preferred)),
            "",
        )
        if picked:
            return picked
    return next((option for option in options if _NEGATIVE.search(option)), "")


def _place_key(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _location_yes_no_answer(text, settings):
    """Answer 'are you based/residing in X?' from the saved current location."""
    match = _CURRENT_IN.search(text)
    if not match:
        return ""
    place = re.sub(
        r"\b(?:the|our|your|this|that|role|job|position|office|city|area|region|country)\b",
        " ",
        match[1],
        flags=re.I,
    )
    place = _place_key(place)
    if not place:
        return ""
    profile = settings.profile
    facts = [
        getattr(profile, "current_city", ""),
        getattr(profile, "current_location", ""),
        getattr(profile, "current_state", ""),
        getattr(profile, "current_country", ""),
    ]
    for fact in facts:
        known = _place_key(fact)
        if known and (place == known or place in known or known in place):
            return "Yes"
    return "No"


def _work_authorization_answer(text, settings):
    """Never claim a right to work in a country the profile does not live in."""
    if not _WORK_AUTH.search(text) or re.search(r"\b(?:require|need|sponsor)", text, re.I):
        return ""
    match = re.search(r"\b(?:in|for)\s+([a-z][a-z .'-]+)", text, re.I)
    if not match:
        return "Yes"
    place = re.sub(
        r"\b(?:the|this|that|which|where|country|role|job|position|office|city|location|"
        r"company|employer|is|are|located|based|work)\b",
        " ",
        match[1],
        flags=re.I,
    )
    place = _place_key(place)
    if not place or re.search(r"\b(?:country|role|position|office|city|location)\b", match[1], re.I):
        return "Yes"
    country = _place_key(getattr(settings.profile, "current_country", "") or "India")
    if country and (place in country or country in place):
        return "Yes"
    return "No"


def _certifications(candidate):
    values = [
        str(value).strip()
        for value in getattr(candidate, "certifications", []) or []
        if str(value or "").strip()
    ]
    return list(dict.fromkeys(values))


def _certification_answer(question, candidate):
    text = _text(question)
    if not _CERTIFICATION.search(text):
        return ""
    certifications = _certifications(candidate)
    if not certifications:
        return "No"
    answer = "; ".join(certifications)
    limit = question.get("max_length")
    if isinstance(limit, int) and 0 < limit < len(answer):
        answer = answer[:limit].rsplit(" ", 1)[0].rstrip(" ,;|") or answer[:limit]
    return answer


def _certification_choice(text, options, candidate):
    if not _CERTIFICATION.search(text):
        return ""
    answer = "Yes" if _certifications(candidate) else "No"
    return _option_for(options, answer) or next(
        (option for option in options if _NEGATIVE.search(option)), ""
    )


def _skill_claim_answer(text, candidate):
    phrase = _skill_phrase(text)
    if not phrase or not _concrete_skill_phrase(phrase):
        return ""
    return "Yes" if _supported_skill_phrase(phrase, candidate) else "No"


def _optional_prompt_answer(text):
    return "N/A" if _OPTIONAL_PROMPT.search(text) else ""


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
    if candidate is not None:
        unsupported = _unsupported_skill_years(text, settings, candidate)
        if unsupported:
            return unsupported
    if "additional" in text and "experience" in text:
        # Additional months/years are beyond the saved total.
        return "0"
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
    if "last working day" in text:
        value = str(getattr(settings.profile, "last_working_date", "") or "").strip()
        return value or "Immediate"
    if _RATING.search(text):
        return _rating_value(text)
    conditional = _conditional_answer(text, settings)
    if conditional:
        return conditional
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
    offer = _offer_in_hand_answer(text)
    if offer:
        return offer
    serving = _serving_notice_answer(text, settings)
    if serving:
        return serving
    if _DATE_ANSWER.search(text):
        return _availability_answer(settings)
    if _PEOPLE.search(text) and not _EXPERIENCE_YEARS.search(text):
        return "2"
    if (
        re.search(r"\b(?:how many|number of)\b", text)
        or re.search(r"\bhow much\b[^?.]*\bexperience\b", text)
        or question.get("input_type") == "number"
        or question.get("field_type") == "number"
        or "notice" in text
        or _is_money(text)
        or _EXPERIENCE_YEARS.search(text)
    ):
        return _number_answer(text, settings, candidate)
    certification = _certification_answer(question, candidate)
    if certification:
        return certification
    place = _location_yes_no_answer(text, settings)
    if place:
        return place
    authorization = _work_authorization_answer(text, settings)
    if authorization:
        return authorization
    optional = _optional_prompt_answer(text)
    if optional:
        return optional
    claim = _skill_claim_answer(text, candidate)
    if claim:
        return claim
    # A skill question mentioning GitHub Actions is still a number question,
    # not a profile-link box. Only an explicit link/profile prompt gets a URL.
    if _LINK_FIELD.search(text) or text.strip(" :*.-") in ("github", "linkedin"):
        link = _link(text, settings, candidate)
        if link:
            return link
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
    email = str(
        getattr(settings.profile, "email", "") or getattr(candidate, "email", "") or ""
    ).strip()
    if "email" in text and email:
        return email
    phone = str(
        getattr(settings.profile, "phone", "") or getattr(candidate, "phone", "") or ""
    ).strip()
    if any(word in text for word in ("phone", "mobile", "contact number")) and phone:
        return phone
    if _YES_NO.search(text):
        return "No" if _wants_negative(text) else "Yes"
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
    if _PEOPLE.search(text) and not _EXPERIENCE_YEARS.search(text):
        return "2"
    if _conditional_answer(text, settings) and question.get("field_type") != "number" and (
        question.get("input_type") != "number"
    ):
        # Conditional follow-ups are answered "N/A" on text fields; never turn
        # that into a numeric zero.
        return ""
    if "additional" in text and "experience" in text:
        return "0"
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
    if (
        _CONDITIONAL_YES.search(text)
        or _CONDITIONAL_NO.search(text)
        or _CONDITIONAL_SERVING.search(text)
    ) and not _PEOPLE.search(text):
        # "If yes..." and serving-notice follow-ups get "N/A" on prose fields.
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
