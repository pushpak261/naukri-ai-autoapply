"""Conservative question identities: paraphrases share facts, not guesses."""

import re

from libs.common.screening import question_key


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
        "last name": "name.last",
        "surname": "name.last",
        "family name": "name.last",
        "email": "contact.email",
        "email address": "contact.email",
        "e mail address": "contact.email",
        "mobile number": "contact.phone",
        "phone number": "contact.phone",
        "contact number": "contact.phone",
        "reason for change": "career.change_reason",
        "reason for job change": "career.change_reason",
        "reason for leaving": "career.change_reason",
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


def narrative_kind(text):
    key = question_key(text)
    if re.search(
        r"\b(?:salary|compensation|ctc|notice|birth|visa|sponsorship|legal|authorized|citizenship|relocation|disability|gender|criminal|terminated|employment gap|leaving)\b|why (?:did|have|were|was)\b",
        key,
    ):
        return ""
    if re.search(
        r"tell (?:me|us) about yourself|introduce yourself|brief (?:introduction|profile)|professional summary",
        key,
    ):
        return "introduction"
    if re.search(
        r"why.*(?:interested|join|apply|applying|work (?:here|with|for))|(?:motivat(?:ion|es?|ed)|cover letter)",
        key,
    ):
        return "motivation"
    if re.search(
        r"(?:describe|tell|explain|brief|details).*(?:your|recent|previous).*project|project (?:description|details)",
        key,
    ):
        return "project"
    if re.search(
        r"why should we hire|what makes you.*(?:good|suitable|fit)|how.*your (?:skills|experience).*match|(?:relevant|suitable) (?:experience|skills)|(?:describe|summarize|tell|explain).*your.*experience|(?:key|greatest|professional) strengths|what (?:can|would) you (?:bring|contribute)|additional (?:information|comments)",
        key,
    ):
        return "fit"
    return ""


def job_specific_question(text):
    return narrative_kind(text) in ("motivation", "fit", "project") or bool(
        re.search(
            r"\b(?:our company|this company|this role|this position|our organization|consent|agreement|signature|declaration)\b",
            question_key(text),
        )
    )
