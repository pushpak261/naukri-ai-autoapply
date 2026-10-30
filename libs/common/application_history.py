"""Record-scoped resume evidence for repeatable employer history sections."""

import calendar
import re

from libs.common.screening import format_evidence


def records(profile, kind):
    key = "education" if kind == "education" else "work_experience"
    return [entry for entry in getattr(profile, key, []) if isinstance(entry, dict)]


def first(record, *keys):
    return next((str(record[k]).strip() for k in keys if record.get(k) not in (None, "")), "")


def dates(record, kind):
    start = first(record, "start_date", "from_date", "start")
    end = first(record, "end_date", "to_date", "end")
    duration = first(record, "duration")
    parts = re.split(r"\s+(?:-|to)\s+|[–—]", duration, maxsplit=1, flags=re.I)
    if len(parts) == 2:
        start, end = start or parts[0], end or parts[1]
    if kind == "education":
        end = end or first(record, "year", "graduation_date", "completion_date")
    return start, end


def current_record(record, kind):
    key = "currently_pursuing" if kind == "education" else "is_current"
    if isinstance(record.get(key), bool):
        return record[key]
    _, end = dates(record, kind)
    if re.fullmatch(r"present|current|ongoing|now", end.strip(), re.I):
        return True
    return False if date_parts(end) else None


def date_parts(value):
    """Retain the supplied precision; a month never becomes an invented day."""
    value = str(value).strip()
    iso = re.fullmatch(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", value)
    if iso:
        return iso_date_parts(iso)
    named = re.fullmatch(r"([A-Za-z]+)\s+(\d{4})", value)
    if not named:
        return {}
    month, year = named.groups()
    months = {
        name.casefold(): i
        for i in range(1, 13)
        for name in (calendar.month_name[i], calendar.month_abbr[i])
    }
    number = months.get(month.casefold())
    return {"year": year, "month": f"{number:02d}"} if number and 1900 <= int(year) <= 2100 else {}


def iso_date_parts(match):
    year, month, day = match.groups()
    if not 1900 <= int(year) <= 2100:
        return {}
    if month and not 1 <= int(month) <= 12:
        return {}
    if day and not 1 <= int(day) <= calendar.monthrange(int(year), int(month))[1]:
        return {}
    return {k: v for k, v in zip(("year", "month", "day"), (year, month, day), strict=True) if v}


def record_identity(record, kind):
    keys = (
        ("institution", "degree", "year")
        if kind == "education"
        else ("company", "title", "duration")
    )
    return " / ".join(first(record, key) for key in keys if first(record, key))[:500]


def scope_fields(state, profile):
    """Make repeated labels durable and specific to the resume record, not the DOM ID."""
    for field in state["fields"]:
        history = field.get("history")
        if not history:
            continue
        entries = records(profile, history["kind"])
        index = history["index"]
        record = entries[index] if index < len(entries) else {}
        identity = record_identity(record, history["kind"]) or f"unsaved record {index + 1}"
        label = history.get("datePart", "").replace("_", " ").title() or field["question"]
        field["question"] = f"{history['kind'].title()} — {identity} — {label}"
    return state


def history_date(record, kind, field):
    part = field["history"].get("datePart", "")
    if not part:
        return ""
    endpoint, component = part.split("_", 1)
    value = dates(record, kind)[0 if endpoint == "start" else 1]
    parts = date_parts(value)
    if component in ("month", "year"):
        return date_component(parts, component, field)
    if component == "month_year":
        return f"{parts['month']}/{parts['year']}" if "month" in parts and "year" in parts else ""
    required = ("year", "month") if field["type"] == "month" else ("year", "month", "day")
    return "-".join(parts[k] for k in required) if all(k in parts for k in required) else ""


def date_component(parts, component, field):
    value = parts.get(component, "")
    if not value or field["type"] != "dropdown":
        return value
    alternatives = {value, str(int(value))}
    if component == "month":
        alternatives.update((calendar.month_name[int(value)], calendar.month_abbr[int(value)]))
    alternatives = {v.casefold() for v in alternatives}
    matches = [
        o["text"]
        for o in field["options"]
        if str(o["text"]).casefold() in alternatives or str(o["value"]).casefold() in alternatives
    ]
    return matches[0] if len(matches) == 1 else ""


def degree_subject(degree):
    match = re.search(r"\bin ", degree, re.I)
    if match:
        return degree[match.end() :].partition("(")[0].strip()
    match = re.search(r"\bof ", degree, re.I)
    if match:
        subject = degree[match.end() :].partition("(")[0].strip()
        if subject.casefold().endswith("engineering"):
            return subject
    abbreviation, separator, subject = degree.partition(",")
    if separator and abbreviation.replace(".", "").casefold() in ("be", "btech"):
        return subject.strip()
    return ""


def record_value(record, kind, label):
    label = re.sub(r"[^a-z ]", " ", label.casefold())
    if re.search(r"institute|institution|school|university|college", label):
        return first(record, "institution", "school", "university")
    if re.search(r"degree|qualification", label):
        return first(record, "degree", "qualification")
    if re.search(r"\bgpa\b|grade|overall result", label):
        return first(record, "grade", "gpa", "result")
    if re.search(r"major|department|field of study|stream", label):
        explicit = first(record, "major", "field_of_study", "department", "stream")
        return explicit or degree_subject(first(record, "degree"))
    if kind == "experience" and re.search(r"location|city", label):
        return first(record, "location", "city")
    if re.search(r"company|employer|organization", label):
        return first(record, "company", "employer", "organization")
    if re.search(r"occupation|title|position|designation", label):
        return first(record, "title", "job_title", "position")
    if kind == "experience" and re.search(r"summary|description|responsibilit|achievement", label):
        explicit = first(record, "summary", "description")
        highlights = record.get("highlights", [])
        return explicit or "\n".join(h for h in highlights if isinstance(h, str))
    return ""


def education_category(value, label):
    if re.search(r"degree|qualification", label, re.I):
        if re.search(r"\bdiploma\b", value, re.I):
            return "Diploma"
        if re.match(r"(?:B\.?E\.?|B\.?Tech\.?|Bachelor(?:s| of)?)\b", value, re.I):
            return "Bachelors"
    elif value.casefold() == "advanced computing":
        return "Computing"
    return ""


def history_answer(field, profile):
    history = field["history"]
    entries = records(profile, history["kind"])
    if history["index"] >= len(entries):
        return ""
    record = entries[history["index"]]
    if history.get("datePart"):
        return history_date(record, history["kind"], field)
    if history.get("current"):
        current = current_record(record, history["kind"])
        return "Yes" if current else "No" if current is False else ""
    value = record_value(record, history["kind"], history["label"])
    if not value:
        return ""
    answer = format_evidence(value, field, experience_in_years=False)
    if answer or field["type"] != "dropdown" or history["kind"] != "education":
        return answer
    # Common ATS categories are broader than the full degree name on a resume.
    category = education_category(value, history["label"])
    return format_evidence(category, field, experience_in_years=False) if category else ""


def identity_conflict(field, profile):
    history = field.get("history")
    if not history or not field["value"]:
        return False
    if not re.search(
        r"company|employer|institution|institute|school|degree|title|position",
        history["label"],
        re.I,
    ):
        return False
    expected = history_answer(field, profile)

    def normalize(text):
        value = " ".join(text.casefold().split())
        if re.search(r"title|position", history["label"], re.I):
            title, _, qualifier = value.rpartition("(")
            if qualifier in ("contract)", "full time)", "full-time)", "part time)", "part-time)"):
                value = title.rstrip()
        return value

    return bool(expected) and normalize(field["value"]) != normalize(expected)


def optional_current_end(field, fields):
    """An ongoing record has no end date; require the employer's checked control."""
    history = field.get("history") or {}
    if field["required"] or not history.get("datePart", "").startswith("end_"):
        return False
    return any(
        (f.get("history") or {}).get("section") == history.get("section")
        and f["history"]["index"] == history["index"]
        and f["history"].get("current")
        and f["value"] == "Yes"
        for f in fields
    )
