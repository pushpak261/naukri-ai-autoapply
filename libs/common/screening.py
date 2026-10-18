"""Explicit evidence only for browser fallbacks; unknown answers stay blank."""

import re


def _basic_answer(question, settings, candidate=None):
    text = str(question.get("question", "")).casefold()
    profile = settings.profile
    value = ""
    if "email" in text:
        value = getattr(profile, "email", "") or getattr(candidate, "email", "")
    elif any(word in text for word in ("phone", "mobile", "contact number")):
        value = getattr(profile, "phone", "") or getattr(candidate, "phone", "")
    elif "first name" in text:
        value = getattr(profile, "first_name", "")
    elif "last name" in text or "surname" in text:
        value = getattr(profile, "last_name", "")
    elif "name" in text and not any(
        word in text for word in ("company", "employer", "school", "college")
    ):
        value = getattr(candidate, "name", "") or " ".join(
            filter(None, (getattr(profile, "first_name", ""), getattr(profile, "last_name", "")))
        )
    elif any(
        word in text
        for word in ("current location", "current city", "where do you live", "where are you based")
    ):
        value = profile.current_location
    elif any(word in text for word in ("expected salary", "expected ctc")):
        value = profile.expected_ctc
    elif any(word in text for word in ("current salary", "current ctc")):
        value = profile.current_ctc
    elif "notice period" in text:
        value = profile.notice_period
    elif (
        "experience" in text
        and ("total" in text or "overall" in text)
        and not re.search(r"\b(?:with|using|in)\s+\w+", text)
    ):
        value = profile.total_experience
    value = str(value or "").strip()
    if not value:
        return ""
    options = [
        str(option.get("text", "") if isinstance(option, dict) else option).strip()
        for option in question.get("options", [])
    ]
    if options:
        return next((option for option in options if option.casefold() == value.casefold()), "")
    if question.get("type", question.get("field_type")) == "number" and not re.fullmatch(
        r"\d+(?:\.\d+)?", value
    ):
        return ""
    return value


def question_key(text):
    # Preserve language punctuation: C, C++ and C# are different facts.
    return re.sub(r"[^\w+#]+", " ", str(text).casefold()).strip()


def _numeric(value):
    match = re.fullmatch(
        r"\s*(\d+(?:\.\d+)?)\s*(?:years?|yrs?|days?|lpa|lakhs?)?\s*", str(value), re.I
    )
    return float(match[1]) if match else None


def format_evidence(value, question):
    text = str(question.get("question", "")).casefold()
    value = str(value).strip()
    if not value:
        return ""
    number = _numeric(value)
    if number is not None and "month" in text and "experience" in text:
        number *= 12
    if (
        number is not None
        and "lpa" in value.casefold()
        and any(word in text for word in ("rupees", "inr", "per annum"))
    ):
        number *= 100000
    if number is not None and "notice" in text and "month" in text:
        return ""  # Converting calendar months to days requires a specified date.
    options = [
        str(o.get("text", "") if isinstance(o, dict) else o).strip()
        for o in question.get("options", [])
    ]
    exact = [o for o in options if o.casefold() == value.casefold()]
    if exact:
        return exact[0]
    if options:
        matches = []
        for option in options:
            nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", option)]
            if number is None:
                continue
            if (
                len(nums) == 2
                and re.search(r"[-–]|\bto\b", option, re.I)
                and nums[0] <= number <= nums[1]
            ):
                matches.append(option)
            elif len(nums) == 1:
                label = option.casefold()
                if re.search(r"\b(?:less than|under|below)\b", label):
                    fits = number < nums[0]
                elif re.search(r"\b(?:more than|above|over)\b", label):
                    fits = number > nums[0]
                elif "+" in option or "at least" in label:
                    fits = number >= nums[0]
                else:
                    fits = number == nums[0]
                if fits:
                    matches.append(option)
        return matches[0] if len(matches) == 1 else ""
    numeric_field = question.get("type", question.get("field_type")) == "number"
    numeric_question = any(
        word in text for word in ("how many", "number of", "in days", "in years", "in months")
    )
    if numeric_field or numeric_question:
        return format(number, "g") if number is not None else ""
    return value


def evidence_answer(question, settings, candidate=None):
    text = str(question.get("question", "")).casefold()
    profile = settings.profile
    confirmed = getattr(profile, "confirmed_answers", {})
    saved = [
        value
        for original, value in confirmed.items()
        if question_key(original) == question_key(text)
    ]
    if saved:
        return format_evidence(saved[0], question) if len(saved) == 1 else ""
    value = ""
    name = getattr(candidate, "name", "")
    if "first name" in text:
        value = getattr(profile, "first_name", "") or (name.split()[0] if name else "")
    elif "last name" in text or "surname" in text:
        value = getattr(profile, "last_name", "") or (
            name.split()[-1] if len(name.split()) > 1 else ""
        )
    elif "experience" in text or re.search(r"\b(?:years|months)\b.*\b(?:with|using)\b", text):
        from libs.common.local_matching import normalize_skill, contains_skill

        specific = re.search(r"\b(?:with|using|in)\s+\w+", text)
        facts = getattr(profile, "skill_experience_years", {})
        if specific:
            found = [
                (skill, years)
                for skill, years in facts.items()
                if contains_skill(text, normalize_skill(skill))
            ]
            if len(found) == 1 and found[0][1] >= 0:
                value = format(found[0][1], "g")
        elif any(
            word in text
            for word in (
                "total",
                "overall",
                "professional",
                "work experience",
                "years of experience",
            )
        ):
            value = getattr(profile, "total_experience", "")
            if not value and getattr(candidate, "total_experience_years", 0) > 0:
                value = format(candidate.total_experience_years, "g")
        if value and re.search(r"\b(?:do you have|at least|minimum|more than)\b", text):
            required = re.search(r"(\d+(?:\.\d+)?)\s*(years?|months?)", text)
            actual = _numeric(value)
            if required and actual is not None:
                limit = float(required[1]) / (12 if required[2].startswith("month") else 1)
                value = (
                    "Yes" if (actual > limit if "more than" in text else actual >= limit) else "No"
                )
            elif actual is not None and "do you have" in text:
                value = "Yes" if actual > 0 else "No"
            else:
                value = ""
    elif "notice period" in text or "when can you join" in text:
        value = getattr(profile, "notice_period", "")
        if value.casefold().strip() in ("immediate", "immediately"):
            value = (
                "0"
                if question.get("type", question.get("field_type")) == "number" or "days" in text
                else "Immediate"
            )
        if re.search(r"\b(?:are you|serving|buyout)\b", text):
            value = ""  # A duration does not establish current employment status.
    elif "expected" in text and any(
        word in text for word in ("salary", "ctc", "compensation", "package")
    ):
        value = getattr(profile, "expected_ctc", "")
    elif any(
        word in text for word in ("current salary", "current ctc", "present ctc", "current package")
    ):
        value = getattr(profile, "current_ctc", "")
    elif any(word in text for word in ("github", "linkedin")):
        value = getattr(profile, "github_url" if "github" in text else "linkedin_url", "")
    elif "reason for" in text and any(word in text for word in ("change", "leaving")):
        value = getattr(profile, "reason_for_change", "")
    else:
        # Existing simple contact/location rules still apply with identical option validation.
        plain = {**question, "options": [], "type": "text", "field_type": "text"}
        value = _basic_answer(plain, settings, candidate)
    return format_evidence(value, question)
