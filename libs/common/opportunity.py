"""Explainable opportunity evidence shared by the dashboard and both agents.

No model calls, inferred credentials or predictions about hiring outcomes.
"""

import json
import re
from collections.abc import Mapping

ALIASES = {
    "js": "javascript",
    "ts": "typescript",
    "reactjs": "react",
    "react.js": "react",
    "nodejs": "node.js",
    "node js": "node.js",
    "postgres": "postgresql",
    "py": "python",
    "c sharp": "c#",
    "csharp": "c#",
    "dotnet": ".net",
}


def skills(value):
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            value = parsed if isinstance(parsed, list) else value
        except (ValueError, TypeError):
            pass
        if isinstance(value, str):
            value = re.split(r"[,;|\n]", value)
    if not isinstance(value, (list, tuple)):
        return []
    result = {}
    for item in value:
        if isinstance(item, str) and 0 < len(item.strip()) <= 100:
            cleaned = re.sub(r"\s+", " ", item.strip())
            result.setdefault(ALIASES.get(cleaned.casefold(), cleaned.casefold()), cleaned)
    return list(result.values())


def canonical(value):
    key = str(value).strip().casefold()
    return ALIASES.get(key, key)


def value(item, key, default=""):
    return item.get(key, default) if isinstance(item, Mapping) else getattr(item, key, default)


def skill_evidence(job, profile):
    required = skills(value(job, "skills"))
    candidate = {
        canonical(item)
        for item in skills(value(profile, "skills", []))
        + skills(value(profile, "technical_skills", []))
    }
    matching = [item for item in required if canonical(item) in candidate]
    missing = [item for item in required if canonical(item) not in candidate]
    return required, candidate, matching, missing


def evidence_priority(job, profile):
    """Small tie-break boost only; never bypasses filters or changes AI scores."""
    required, candidate, matching, _ = skill_evidence(job, profile)
    return 0.15 * len(matching) / len(required) if required and candidate else 0.0


def assess_opportunity(job, profile, application_status=None, preferred_locations=()):
    required, candidate, matching, missing = skill_evidence(job, profile)
    reasons, cautions = [], []
    score = round(100 * len(matching) / len(required)) if required and candidate else None
    if matching:
        reasons.append("Resume evidence matches: " + ", ".join(matching[:6]))
    if missing:
        cautions.append("Not evidenced in your saved profile: " + ", ".join(missing[:6]))
    if not candidate:
        cautions.append("Add resume skills before relying on this shortlist.")
    if not required:
        cautions.append("Listing has no structured skills; review its full description.")
    location = str(value(job, "location")).casefold()
    preferences = [
        str(item).strip().casefold() for item in preferred_locations if str(item).strip()
    ]
    needs_review = False
    if preferences and location:
        if any(
            re.search(r"(?<!\w)" + re.escape(item) + r"(?!\w)", location) for item in preferences
        ):
            reasons.append("Location matches a saved preference.")
        else:
            cautions.append("Location does not match your saved preferences; check flexibility.")
            needs_review = True
    experience = re.match(
        r"^\s*(\d+(?:\.\d+)?)\s*(?:-|–|to\b|\+|years?\b|yrs?\b)",
        str(value(job, "experience")),
        re.IGNORECASE,
    )
    candidate_years = value(profile, "total_experience_years", None)
    if (
        experience
        and isinstance(candidate_years, (float, int))
        and not isinstance(candidate_years, bool)
        and candidate_years >= 0
    ):
        minimum = float(experience[1])
        if candidate_years < minimum:
            cautions.append(
                f"Listing asks for at least {minimum:g} years; saved profile records {candidate_years:g}. Check eligibility."
            )
            needs_review = True
        else:
            reasons.append(
                "Saved experience meets the listing’s stated minimum; verify the full requirements."
            )
    posted = str(value(job, "posted_date")).casefold()
    if re.search(r"\b(today|just now|\d+\s+hours?)\b", posted):
        reasons.append("Recently posted according to the listing.")
    recommendation = (
        "prioritize"
        if score is not None and score >= 70
        else "prepare" if score is not None else "review"
    )
    if needs_review:
        recommendation = "review"
    if application_status in ("applied", "applying", "pending_retry"):
        recommendation = "already_in_progress"
        cautions.append("Already submitted or in progress; avoid a duplicate application.")
    confidence = (
        "high"
        if required and len(required) >= 3 and candidate
        else "medium" if required and candidate else "low"
    )
    return {
        "score": score,
        "confidence": confidence,
        "recommendation": recommendation,
        "matching_skills": matching,
        "missing_skills": missing,
        "reasons": reasons,
        "cautions": cautions,
    }
