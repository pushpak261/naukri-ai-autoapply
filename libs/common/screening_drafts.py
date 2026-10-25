"""Positive application prose assembled from candidate evidence and this job."""

import re

from libs.common.local_matching import contains_skill, normalize_skill
from libs.common.resume_facts import duration_years
from libs.common.screening_intents import narrative_kind


def _skills(candidate):
    skills = [*getattr(candidate, "skills", []), *getattr(candidate, "technical_skills", [])]
    unique = {}
    for skill in skills:
        if isinstance(skill, str) and skill.strip():
            unique.setdefault(normalize_skill(skill), skill.strip())
    return list(unique.values())


def _experience(settings, candidate):
    years = duration_years(getattr(settings.profile, "total_experience", ""))
    if years is None:
        years = getattr(candidate, "total_experience_years", 0)
    title = getattr(candidate, "current_title", "")
    if years and years > 0:
        return (
            f"I have {years:g} {'year' if years == 1 else 'years'} of professional experience."
            + (f" My current role is {title}." if title else "")
        )
    return f"My current role is {title}." if title else ""


def _project(candidate, job):
    projects = [p for p in getattr(candidate, "projects", []) if isinstance(p, dict)]
    if not projects:
        return []
    job_text = f"{job.title} {job.skills} {job.description}"
    skills = _skills(candidate)
    project = max(
        projects,
        key=lambda p: sum(
            contains_skill(str(p), normalize_skill(s))
            and contains_skill(job_text, normalize_skill(s))
            for s in skills
        ),
    )
    parts = [project.get("name", ""), project.get("description", "")]
    highlights = project.get("highlights", [])
    if isinstance(highlights, list):
        parts.extend(highlights[:2])
    return [str(p).strip().rstrip(".") + "." for p in parts if isinstance(p, str) and p.strip()]


def _fit_length(parts, question):
    limit = question.get("max_length")
    limit = min(limit, 2000) if isinstance(limit, int) and limit > 0 else 2000
    selected = []
    for part in parts:
        part = re.sub(r"\s+", " ", str(part)).strip()
        if part and len(" ".join([*selected, part])) <= limit:
            selected.append(part)
    result = " ".join(selected)
    minimum = question.get("min_length")
    return "" if isinstance(minimum, int) and len(result) < minimum else result


def _relevant_skills(question, skills, job_text):
    relevant = [s for s in skills if contains_skill(job_text, normalize_skill(s))]
    from src.naukri_agent.ai.resume_parser import DEFAULT_TECH_SKILLS

    requested = {
        normalize_skill(s)
        for s in [*DEFAULT_TECH_SKILLS, *skills]
        if contains_skill(str(question.get("question", "")), normalize_skill(s))
    }
    supported = {normalize_skill(s) for s in skills}
    if requested - supported:
        return None
    explicit = re.search(
        r"your (?:professional )?experience (?:working )?(?:with|in|using) (.+)",
        str(question.get("question", "")).casefold(),
    )
    if explicit:
        subjects = re.split(r"\band\b|\bor\b|[,;&]", explicit[1])
        if any(
            not any(contains_skill(subject, skill) for skill in supported) for subject in subjects
        ):
            return None
        if (
            re.search(r"\d", explicit[1])
            and normalize_skill(explicit[1].strip(" ?.")) not in supported
        ):
            return None
    if requested:
        relevant = [s for s in skills if normalize_skill(s) in requested]
    return relevant


def draft_answer(question, settings, candidate, job):
    """Write only supported narratives; personal declarations still need facts."""
    kind = narrative_kind(question.get("question", ""))
    if not kind:
        return ""
    skills = _skills(candidate)
    relevant = _relevant_skills(question, skills, f"{job.title} {job.skills} {job.description}")
    if relevant is None:
        return ""
    experience = _experience(settings, candidate)
    if kind == "project":
        return _fit_length(_project(candidate, job), question)
    if kind == "introduction":
        parts = [experience, "My skills include " + ", ".join(skills[:6]) + "." if skills else ""]
    elif not relevant:
        return ""
    elif kind == "motivation":
        role = str(job.title).strip() or "advertised"
        employer = f" at {job.company}" if str(job.company).strip() else ""
        parts = [
            f"I am interested in the {role} role{employer}.",
            "Its published requirements align with my skills in " + ", ".join(relevant[:6]) + ".",
            experience,
            "I would welcome the opportunity to contribute these skills and develop further in this role.",
        ]
    else:
        parts = [
            experience,
            "My relevant skills include " + ", ".join(relevant[:6]) + ".",
            *_project(candidate, job),
            "I would bring this background to the advertised role and build on it through the work.",
        ]
    return _fit_length(parts, question)
