"""Explainable resume matching without network calls or invented requirements."""

import re

ALIASES = {
    "core java": "java",
    "java developer": "java",
    "microservice": "microservices",
    "reacts js": "react",
    "springboot": "spring boot",
    "postgres": "postgresql",
    "node.js": "nodejs",
    "node js": "nodejs",
    "react.js": "react",
    "reactjs": "react",
    "spring-boot": "spring boot",
    "restful api": "rest api",
    "restful apis": "rest api",
    "amazon web services": "aws",
    "rest apis": "rest api",
    "restful": "rest api",
    "javascript": "javascript",
}


def normalize_skill(value):
    value = re.sub(r"\s+", " ", str(value).casefold().strip())
    return ALIASES.get(value, value)


def contains_skill(text, skill):
    names = [skill, *(name for name, canonical in ALIASES.items() if canonical == skill)]
    return any(
        re.search(r"(?<![\w+#])" + re.escape(name) + r"(?![\w+#])", text.casefold())
        for name in names
    )


def software_development_role(title):
    """Recognize development titles without equating every engineering discipline."""
    return bool(
        re.search(
            r"\b(?:software(?:\s+development)?|applications?|back[ -]?end|front[ -]?end|"
            r"full[ -]?stack|java|python|web|mobile)\s+(?:engineer|developer)\b|\b(?:programmer|sde)\b",
            str(title or ""),
            re.I,
        )
    )


def local_match(profile, job, threshold):
    from src.naukri_agent.ai.resume_parser import DEFAULT_TECH_SKILLS

    candidate = {
        normalize_skill(s) for s in [*profile.skills, *profile.technical_skills] if str(s).strip()
    }
    candidate_text = " ".join(candidate)
    candidate.update(
        normalize_skill(s)
        for s in DEFAULT_TECH_SKILLS
        if contains_skill(candidate_text, normalize_skill(s))
    )
    if "spring boot" in candidate:
        candidate.add("spring")
    text = f"{job.description} {job.skills}".strip() or job.title
    explicit = set()
    vocabulary = {normalize_skill(s) for s in [*DEFAULT_TECH_SKILLS, *candidate]}
    for label in re.split(r"[,;|\n]|\s+/\s+|\s+&\s+", job.skills or ""):
        if not label.strip():
            continue
        known = {skill for skill in vocabulary if contains_skill(label, skill)}
        explicit.update(known or {normalize_skill(label)})
    # Naukri sometimes supplies generic tags such as "Core" and "Application"
    # while the description contains the actual Java/Spring/SQL requirements.
    # Keep unfamiliar named skills as missing evidence, but don't let those
    # generic categories hide the concrete stack in the description.
    generic_tags = {
        "coding",
        "core",
        "architecture",
        "application",
        "software development",
        "application development",
        "agile software",
        "agile software development",
        "development",
        "technology",
        "technology solutions",
        "office",
        "analytics",
    }
    role_tags = {"backend", "frontend", "fullstack", "developer", "architect", "software engineer"}
    requirements = (explicit - generic_tags - role_tags) | {
        normalize_skill(s)
        for s in [*DEFAULT_TECH_SKILLS, *candidate]
        if normalize_skill(s) not in role_tags and contains_skill(text, normalize_skill(s))
    }
    matching = sorted(requirements & candidate)
    missing = sorted(requirements - candidate)
    coverage = len(matching) / len(requirements) if requirements else 0
    role_words = set(re.findall(r"[a-z]+", (profile.current_title or "").casefold())) - {
        "senior",
        "junior",
        "lead",
        "the",
        "and",
        "of",
    }
    role_fit = bool(role_words & set(re.findall(r"[a-z]+", (job.title or "").casefold())))
    role_fit = role_fit or (
        software_development_role(profile.current_title) and software_development_role(job.title)
    )
    if not role_words and len(matching) >= 2:
        # Older locally parsed profiles may have no job title. Supported stack
        # terms in the listing title can supply role evidence without inventing
        # a candidate title or accepting a single incidental skill.
        role_fit = any(contains_skill(job.title or "", skill) for skill in matching)
    score = round(80 * coverage + (20 if role_fit and matching else 0), 1) if requirements else 0
    approved = bool(matching) and score >= threshold and (role_fit or len(matching) >= 2)
    reason = f"Resume rules: {len(matching)}/{len(requirements)} listed skills supported; role overlap {'yes' if role_fit else 'no'}."
    # LinkedIn's experience-level filter is coarse; enforce stated minimum
    # tenure locally as well, without treating a range's upper bound as a minimum.
    from libs.common.resume_facts import minimum_experience_years

    required_years = minimum_experience_years(job.experience or "")
    from libs.common.agent_reasoning import description_experience_minimum

    labelled_minimum = description_experience_minimum(job.description or "")
    if labelled_minimum is not None:
        required_years = max(required_years or 0, labelled_minimum)
    stated = re.search(
        r"\b\d+(?:\.\d+)?\s*(?:(?:[-–]|to)\s*\d+(?:\.\d+)?\s*)?\+?\s*(?:years?|yrs?|months?|mos?)\s+(?:of\s+)?(?:[a-z][\w+#./-]*\s+){0,4}(?:experience|development)\b",
        job.description or "",
        re.I,
    )
    if stated:
        stated_years = minimum_experience_years(stated[0])
        required_years = max(required_years or 0, stated_years or 0)
    if required_years is not None and required_years > profile.total_experience_years:
        approved = False
        reason += f" Required experience is {required_years:g} years; the saved resume supports {profile.total_experience_years:g}."
    if not requirements:
        reason += " No usable skill requirements; review this listing manually."
    return score, approved, reason, matching, missing
