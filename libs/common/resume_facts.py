"""Small, explainable extractors shared by both agents' no-network workflows."""

import re


def duration_years(value):
    """Read a stated duration, including mixed years/months; never assume tenure."""
    text = str(value).strip().casefold()
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return float(text)
    parts = re.findall(r"(\d+(?:\.\d+)?)\s*(years?|yrs?|months?|mos?)\b", text)
    if not parts:
        return None
    remainder = re.sub(r"\d+(?:\.\d+)?\s*(?:years?|yrs?|months?|mos?)\b", "", text)
    if remainder.strip(" ,&") not in ("", "and"):
        return None
    return sum(float(n) / (12 if unit.startswith("mo") else 1) for n, unit in parts)


def minimum_experience_years(text):
    match = re.search(
        r"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:(?:[-–]|to)\s*\d+(?:\.\d+)?\s*)?\+?\s*(years?|yrs?|months?|mos?)\b",
        str(text),
        re.I,
    )
    return float(match[1]) / (12 if match[2].casefold().startswith("mo") else 1) if match else None


def extract_resume_facts(text, configured_experience=""):
    from libs.common.local_matching import contains_skill, normalize_skill
    from src.naukri_agent.ai.resume_parser import DEFAULT_TECH_SKILLS

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    email = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text)
    phone = re.search(r"(?<!\d)(?:\+\d{1,3}[- ]?)?(?:\d[ ()-]*){10}(?!\d)", text)
    title = next(
        (
            line
            for line in lines[1:8]
            if len(line) < 100
            and re.search(
                r"\b(?:developer|engineer|analyst|designer|architect|consultant)\b", line, re.I
            )
            and not re.search(
                r"\b(?:seeking|looking|aspiring|experience|developed|responsible)\b", line, re.I
            )
        ),
        "",
    )
    years = duration_years(configured_experience)
    if years is None:
        explicit = re.search(
            r"\b(\d+(?:\.\d+)?\s*(?:years?|yrs?)(?:\s*(?:and)?\s*\d+\s*months?)?|\d+\s*months?)\s+(?:of\s+)?(?:professional\s+|work\s+|hands-on\s+)?experience\b",
            text,
            re.I,
        )
        years = duration_years(explicit[1]) if explicit else None
    skills = list(
        dict.fromkeys(
            normalize_skill(skill)
            for skill in DEFAULT_TECH_SKILLS
            if contains_skill(text, normalize_skill(skill))
        )
    )
    # Only attach a degree to facts on the same line. An adjacent work date or
    # institution must not silently become a graduation fact.
    education = []
    for line in lines:
        if re.search(
            r"\b(?:bachelor|master|b\.?tech|m\.?tech|b\.e\.|m\.e\.|bsc|msc|bca|mca|mba|ph\.?d|pg-dac)(?!\w)",
            line,
            re.I,
        ):
            dates = re.findall(r"\b(?:19|20)\d{2}\b", line)
            education.append(
                {"degree": line, "institution": "", "year": dates[-1] if dates else ""}
            )
    return {
        "name": lines[0] if lines else "",
        "email": email[0] if email else "",
        "phone": phone[0].strip() if phone else "",
        "current_title": title,
        "summary": "Parsed locally without AI.",
        "total_experience_years": years if years is not None else 0.0,
        "skills": skills,
        "technical_skills": skills,
        "job_titles_held": [title] if title else [],
        "education": education,
        "raw_text": text,
    }
