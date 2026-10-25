"""Conservative question identities: paraphrases share facts, not guesses."""

import re

from libs.common.screening import question_key

LAST_NAME_FACT = "name.last"
EMAIL_FACT = "contact.email"
PHONE_FACT = "contact.phone"
CHANGE_REASON_FACT = "career.change_reason"
MOTIVATION_INTENT = "motivation"
PROJECT_INTENT = "project"
PERSONAL_WORDS = frozenset(
    [
        "salary",
        "compensation",
        "ctc",
        "notice",
        "birth",
        "visa",
        "sponsorship",
        "legal",
        "authorized",
        "citizenship",
        "relocation",
        "disability",
        "gender",
        "criminal",
        "terminated",
        "leaving",
    ]
)


def answer_identity(text):
    """Collapse only complete, equivalent questions; retain entities and units."""
    key = question_key(text)
    label = re.sub(r"^(?:please )?(?:enter|provide|mention|specify|state) (?:your )?", "", key)
    label = re.sub(r"^(?:what is|what s) (?:your )?", "", label)
    label = re.sub(r"^your ", "", label)
    aliases = {
        "full name": "name.full",
        "name as per resume": "name.full",
        "first name": "name.first",
        "given name": "name.first",
        "last name": LAST_NAME_FACT,
        "surname": LAST_NAME_FACT,
        "family name": LAST_NAME_FACT,
        "email": EMAIL_FACT,
        "email address": EMAIL_FACT,
        "e mail address": EMAIL_FACT,
        "mobile number": PHONE_FACT,
        "phone number": PHONE_FACT,
        "contact number": PHONE_FACT,
        "reason for change": CHANGE_REASON_FACT,
        "reason for job change": CHANGE_REASON_FACT,
        "reason for leaving": CHANGE_REASON_FACT,
    }
    if label in aliases:
        return "fact:" + aliases[label]
    for pattern, identity in (
        (
            r"(?:are you )?(?:currently |presently )?(?:employed|working)(?: currently)?",
            "employment.current",
        ),
        (
            r"(?:are you )?(?:currently )?(?:serving|on)(?: your| a)? notice(?: period)?",
            "employment.serving_notice",
        ),
        (r"(?:are you )?(?:willing|open|prepared) to relocat(?:e|ion)", "preference.relocate"),
        (r"(?:are you )?(?:willing|open|prepared) to travel", "preference.travel"),
    ):
        if re.fullmatch(pattern, label):
            return "fact:" + identity
    duration = re.fullmatch(
        r"(?:how many )?(years?|months?)(?: of)? (?:professional |work |hands on )?experience"
        r"(?: do you have)? (?:in|with|using) (.+)",
        label,
    )
    if not duration:
        duration = re.fullmatch(
            r"(.+?) (?:professional |work )?experience in (years?|months?)", label
        )
        if duration:
            skill, unit = duration[1], duration[2]
        else:
            return key
    else:
        unit, skill = duration[1], duration[2]
    # Do not alias thresholds, compound questions or changed meanings.
    if re.search(r"\b(?:not|minimum|least|over|more|less|prefer|required|or|and)\b|\d", skill):
        return key
    from libs.common.local_matching import normalize_skill

    skill = normalize_skill(skill)
    return f"fact:experience.{skill}.{unit.rstrip('s')}"


def _has_phrase(key, phrases):
    return any(f" {phrase} " in f" {key} " for phrase in phrases)


def _motivation(key, words):
    if _has_phrase(key, (MOTIVATION_INTENT, "motivate", "motivates", "motivated", "cover letter")):
        return True
    if "why" not in words:
        return False
    return bool(words & {"interested", "join", "apply", "applying"}) or _has_phrase(
        key, ("work here", "work with", "work for")
    )


def _role_fit(key, words):
    if _has_phrase(
        key,
        (
            "why should we hire",
            "relevant experience",
            "suitable experience",
            "relevant skills",
            "suitable skills",
            "key strengths",
            "greatest strengths",
            "professional strengths",
            "additional information",
            "additional comments",
            "what can you bring",
            "what would you bring",
            "what can you contribute",
            "what would you contribute",
        ),
    ):
        return True
    if _has_phrase(key, ("what makes you",)) and words & {"good", "suitable", "fit"}:
        return True
    if "your" not in words or "experience" not in words and "skills" not in words:
        return False
    return bool(words & {"describe", "summarize", "tell", "explain"}) or {"how", "match"} <= words


def narrative_kind(text):
    key = question_key(text)
    words = set(key.split())
    if (
        words & PERSONAL_WORDS
        or "employment gap" in key
        or re.match(r"why (?:did|have|were|was)\b", key)
    ):
        return ""
    if _has_phrase(
        key,
        (
            "tell me about yourself",
            "tell us about yourself",
            "introduce yourself",
            "brief introduction",
            "brief profile",
            "professional summary",
        ),
    ):
        return "introduction"
    if _motivation(key, words):
        return MOTIVATION_INTENT
    project = bool(
        words & {PROJECT_INTENT, "projects"}
        and words & {"describe", "tell", "explain", "brief", "details"}
        and words & {"your", "recent", "previous"}
    )
    if project or _has_phrase(key, ("project description", "project details")):
        return PROJECT_INTENT
    return "fit" if _role_fit(key, words) else ""


def job_specific_question(text):
    return narrative_kind(text) in (MOTIVATION_INTENT, "fit", PROJECT_INTENT) or bool(
        re.search(
            r"\b(?:our company|this company|this role|this position|our organization|consent|agreement|signature|declaration|country where|country in which|country of employment)\b",
            question_key(text),
        )
    )
