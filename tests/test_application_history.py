"""History evidence must preserve record identity and date precision."""

from types import SimpleNamespace

import pytest

from libs.common.application_history import (
    current_record,
    date_parts,
    history_answer,
    scope_fields,
)


def field(label, **history):
    return {
        "question": label,
        "type": "text",
        "options": [],
        "history": {"kind": "experience", "index": 0, "label": label, **history},
    }


@pytest.mark.parametrize("value", ["2024-02-30", "2024-13", "2024-00", "unknown", "Present"])
def test_invalid_dates_are_not_transformed_into_candidate_dates(value):
    assert date_parts(value) == {}


def test_month_precision_is_preserved_and_cannot_fill_a_daily_date():
    profile = SimpleNamespace(work_experience=[{"duration": "June 2026 - Present"}])
    date = field("Start date", datePart="start_date")
    date["type"] = "date"
    assert history_answer(date, profile) == ""
    date["type"] = "month"
    assert history_answer(date, profile) == "2026-06"
    assert current_record(profile.work_experience[0], "experience") is True
    assert history_answer(field("End year", datePart="end_year"), profile) == ""


def test_explicit_degree_subject_is_used_but_hsc_stream_is_not_invented():
    profile = SimpleNamespace(
        education=[
            {"degree": "Bachelor of Mechanical Engineering"},
            {"degree": "Higher Secondary Certificate (HSC)"},
        ]
    )
    assert (
        history_answer(field("Major / Department", kind="education"), profile)
        == "Mechanical Engineering"
    )
    assert history_answer(field("Major / Department", kind="education", index=1), profile) == ""


def test_confirmed_answers_are_scoped_to_record_identity_when_resume_order_changes():
    first = {"institution": "College A", "degree": "BSc", "year": "May 2023"}
    second = {"institution": "College B", "degree": "MSc", "year": "Aug 2024"}
    profile = SimpleNamespace(education=[first, second])
    a = scope_fields({"fields": [field("From", kind="education", datePart="start_year")]}, profile)[
        "fields"
    ][0]
    b = scope_fields(
        {"fields": [field("From", kind="education", index=1, datePart="start_year")]}, profile
    )["fields"][0]
    assert a["question"] != b["question"]
    profile.education.reverse()
    moved = scope_fields(
        {"fields": [field("From", kind="education", index=1, datePart="start_year")]}, profile
    )["fields"][0]
    assert moved["question"] == a["question"]


def test_resume_validation_preserves_education_dates_and_accepts_older_profiles():
    from src.naukri_agent.ai.resume_parser import EducationEntry, _map_to_domain_profile

    entry = EducationEntry(
        degree="PG-DAC",
        institution="College",
        year="2024",
        start_date="March 2024",
        end_date="Aug 2024",
        major="Advanced Computing",
    )
    parsed = _map_to_domain_profile({"education": [entry]}, "fixture-hash")
    assert parsed.education[0]["start_date"] == "March 2024"
    assert parsed.education[0]["end_date"] == "Aug 2024"
    assert parsed.education[0]["major"] == "Advanced Computing"
    assert EducationEntry(degree="BSc", institution="College", year="2023").start_date == ""
