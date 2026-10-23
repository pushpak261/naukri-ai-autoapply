"""Related engineering titles must not hide supported development matches."""

import pytest

from libs.common.local_matching import local_match, software_development_role
from src.naukri_agent.models.entities import Job, ResumeProfile


@pytest.mark.parametrize(
    "title",
    [
        "Software Engineer",
        "Associate Software Engineer",
        "Software Development Engineer I",
        "Java Developer",
        "Back-end Engineer",
        "Application Developer",
        "SDE I",
    ],
)
def test_development_title_aliases(title):
    assert software_development_role(title)


@pytest.mark.parametrize(
    "title",
    [
        "Mechanical Engineer",
        "Sales Engineer",
        "Data Engineer",
        "QA Engineer",
        "Business Development Manager",
    ],
)
def test_other_disciplines_do_not_get_development_role_bonus(title):
    assert not software_development_role(title)


def test_generic_software_title_can_match_java_developer_with_evidence():
    profile = ResumeProfile(
        current_title="Java Developer", skills=["Java", "SQL"], total_experience_years=1
    )
    job = Job(
        "example",
        "Software Engineer",
        "Employer",
        "https://example.invalid",
        skills="Java, SQL, Oracle",
        experience="0-2 years",
    )
    score, approved, reason, matching, missing = local_match(profile, job, 70)
    assert approved and score >= 70
    assert "role overlap yes" in reason
    assert matching == ["java", "sql"]
    assert missing == ["oracle"]


def test_role_alias_never_approves_missing_stack_or_excess_experience():
    profile = ResumeProfile(
        current_title="Java Developer", skills=["Java", "SQL"], total_experience_years=1
    )
    job = Job(
        "example",
        "Software Engineer",
        "Employer",
        "https://example.invalid",
        skills="C++, Rust, Kubernetes",
        experience="0-2 years",
    )
    assert not local_match(profile, job, 70)[1]
    job.skills = "Java, SQL"
    job.experience = "5-8 years"
    assert not local_match(profile, job, 70)[1]


def test_engineering_title_in_another_domain_retains_low_score():
    profile = ResumeProfile(
        current_title="Java Developer", skills=["Java", "SQL"], total_experience_years=1
    )
    job = Job(
        "example",
        "Mechanical Engineer",
        "Employer",
        "https://example.invalid",
        skills="Java, SQL, CAD",
        experience="0-2 years",
    )
    score, approved, *_ = local_match(profile, job, 70)
    assert not approved and score < 70
