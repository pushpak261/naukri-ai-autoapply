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
    text = f"{job.title} {job.description} {job.skills}"
    explicit = {normalize_skill(s) for s in re.split(r"[,;|]", job.skills or "") if s.strip()}
    requirements = explicit or {
        normalize_skill(s)
        for s in [*DEFAULT_TECH_SKILLS, *candidate]
        if contains_skill(text, normalize_skill(s))
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
    score = round(80 * coverage + (20 if role_fit and matching else 0), 1) if requirements else 0
    approved = bool(matching) and score >= threshold and (role_fit or len(matching) >= 2)
    reason = f"Resume rules: {len(matching)}/{len(requirements)} listed skills supported; role overlap {'yes' if role_fit else 'no'}."
    if not requirements:
        reason += " No usable skill requirements; review this listing manually."
    return score, approved, reason, matching, missing
