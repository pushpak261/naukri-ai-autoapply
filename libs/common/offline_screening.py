"""Local screening answers from facts, resume summaries and general technical knowledge."""

import re

from libs.common.local_matching import contains_skill, normalize_skill
from libs.common.screening import evidence_answer, format_evidence


def general_technical_question(question):
    text = str(question.get("question", "")).casefold().strip()
    return (
        not question.get("options")
        and question.get("type", "text") in ("text", "textarea", "contenteditable")
        and bool(
            re.match(r"(?:what (?:is|are)|define|explain|difference between|how does)\b", text)
        )
        and bool(
            re.search(
                r"\b(?:java|sql|spring|python|javascript|react|http|https|api|rest|database|transaction|thread|concurrency|synchronization|garbage collection|dependency injection|oop|polymorphism|inheritance|encapsulation|microservices|algorithm|data structure|cache|caching|oauth|jwt|docker|kubernetes|kafka|git|jvm|jdk|jre|acid)\b",
                text,
            )
        )
        and not re.search(
            r"\b(?:you|your|candidate|applicant|worked|project|employer|experience|years|months|history|salary|compensation|ctc|notice|birth|criminal|gender|disability|religion|ethnicity|certification|license|nationality|citizenship|visa|sponsorship|consent|agree|signature|password|passport|ssn)\b",
            text,
        )
    )


def offline_answer(question, settings, candidate, job):
    direct = evidence_answer(question, settings, candidate)
    if direct:
        return direct, "saved_facts"
    text = str(question.get("question", "")).casefold().strip()
    if question.get("options") or question.get("type") in ("number", "date", "file"):
        return "", "needs_input"
    skills = list(
        dict.fromkeys(
            [*getattr(candidate, "skills", []), *getattr(candidate, "technical_skills", [])]
        )
    )
    relevant = [
        skill
        for skill in skills
        if contains_skill(f"{job.title} {job.skills} {job.description}", normalize_skill(skill))
    ]
    value = ""
    if re.fullmatch(r"(?:add |key |technical )?skills?(?: set)?[?*:.\s]*", text):
        value = ", ".join(skills)
    elif re.search(
        r"tell (?:me|us) about yourself|introduce yourself|brief (?:introduction|profile)|professional summary",
        text,
    ):
        years = getattr(candidate, "total_experience_years", 0)
        title = getattr(candidate, "current_title", "")
        parts = [f"I work as a {title}." if title else ""]
        if years:
            parts.append(
                f"I have {years:g} {'year' if years == 1 else 'years'} of professional experience."
            )
        if skills:
            parts.append("My skills include " + ", ".join(skills[:6]) + ".")
        value = " ".join(part for part in parts if part)
    elif re.search(
        r"why should we hire|what makes you (?:a good|suitable)|how (?:do|does) your (?:skills|experience).*match",
        text,
    ):
        if relevant:
            value = (
                "My resume supports skills in "
                + ", ".join(relevant[:6])
                + ". I can bring these skills to the role."
            )
    elif re.search(
        r"(?:describe|tell|explain|brief|details).*(?:your|recent|previous).*(?:project)|project (?:description|details)",
        text,
    ):
        projects = getattr(candidate, "projects", [])
        if projects and isinstance(projects[0], dict):
            project = projects[0]
            pieces = [project.get("name", ""), project.get("description", "")]
            highlights = project.get("highlights", [])
            if isinstance(highlights, list):
                pieces.extend(highlights[:2])
            value = ". ".join(str(piece).strip().rstrip(".") for piece in pieces if piece)
    # General technical questions do not make claims about the candidate's
    # employment history. Personal project/experience questions require facts.
    elif re.match(
        r"(?:what (?:is|are)|define|explain|difference between|how does)\b", text
    ) and not re.search(r"\b(?:you|your|worked|project|employer)\b", text):
        bank = [
            (
                r"dependency injection",
                "Dependency injection supplies an object's dependencies from outside the object instead of constructing them internally. Spring manages beans and commonly injects dependencies through constructors, which makes dependencies explicit and simplifies testing.",
            ),
            (
                r"\boop\b|object.oriented|four pillars",
                "The four main object-oriented principles are encapsulation, abstraction, inheritance and polymorphism. They organize related state and behavior, hide implementation details and allow implementations to vary behind shared contracts.",
            ),
            (
                r"\bjvm\b.*\bjre\b|\bjdk\b.*\bjre\b",
                "The JVM executes Java bytecode. A runtime includes the JVM and libraries needed to run applications. The JDK adds development tools such as the Java compiler and debugger.",
            ),
            (
                r"\brest\b|restful",
                "REST models resources with URLs and uses standard HTTP methods such as GET, POST, PUT, PATCH and DELETE. Requests are stateless, and responses use appropriate HTTP status codes and resource representations, often JSON.",
            ),
            (
                r"\bacid\b",
                "ACID describes database transaction properties: atomicity means all-or-nothing execution; consistency preserves defined constraints; isolation controls concurrent transaction effects; durability preserves committed changes.",
            ),
            (
                r"inner join.*left join|left join.*inner join",
                "An INNER JOIN returns matching rows from both tables. A LEFT JOIN keeps every row from the left table and returns NULL for right-table columns when no matching row exists.",
            ),
            (
                r"\bspring boot\b",
                "Spring Boot builds on Spring with auto-configuration, starter dependencies and embedded application servers. It reduces setup while allowing configuration to be overridden for application requirements.",
            ),
            (
                r"\bmicroservices\b",
                "Microservices divide an application into independently deployable services organized around business capabilities. They communicate through APIs or messaging and require explicit handling of distributed failures, observability and data consistency.",
            ),
        ]
        value = next((answer for pattern, answer in bank if re.search(pattern, text)), "")
        if value:
            return format_evidence(value, question), "technical_knowledge"
    return format_evidence(value, question), "resume" if value else "needs_input"
