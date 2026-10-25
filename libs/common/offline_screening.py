"""Local screening answers from facts, resume summaries and general technical knowledge."""

import re

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
    from libs.common.screening_drafts import draft_answer
    from libs.common.screening_intents import narrative_kind

    direct = evidence_answer(question, settings, candidate)
    if direct:
        return direct, "saved_facts"
    if narrative_kind(question.get("question", "")):
        if question.get("options") or question.get("type") in ("number", "date", "file"):
            return "", "needs_input"
        draft = draft_answer(question, settings, candidate, job)
        return draft, "resume" if draft else "needs_input"
    text = str(question.get("question", "")).casefold().strip()
    if question.get("options") or question.get("type") in ("number", "date", "file"):
        return "", "needs_input"
    skills = list(
        dict.fromkeys(
            [*getattr(candidate, "skills", []), *getattr(candidate, "technical_skills", [])]
        )
    )
    value = ""
    if re.fullmatch(r"(?:add |key |technical )?skills?(?: set)?[?*:.\s]*", text):
        value = ", ".join(skills)
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
