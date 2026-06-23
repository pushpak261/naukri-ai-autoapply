import pytest

from src.naukri_agent.core.domain.entities import Job
from src.naukri_agent.core.domain.specifications import (
    AndSpecification,
    CompanyExclusionSpecification,
    DescriptionExclusionSpecification,
    NotSpecification,
    OrSpecification,
    TitleExclusionSpecification,
)


@pytest.fixture
def sample_job():
    return Job(
        naukri_job_id="job_123",
        title="Senior Python Developer",
        company="Awesome Tech Corp",
        url="https://example.com/job",
        location="Pune",
        experience="3-5 years",
        salary="12 LPA",
        description="We are looking for a senior engineer with strong Django and Python skills.",
        skills="Python, Django, AWS",
        posted_date="2 days ago",
    )


def test_company_exclusion_specification(sample_job):
    # Case insensitive exact / partial matches
    spec = CompanyExclusionSpecification(["awesome", "bad corp"])
    assert spec.is_satisfied_by(sample_job) is True

    spec_not_matched = CompanyExclusionSpecification(["Google", "Facebook"])
    assert spec_not_matched.is_satisfied_by(sample_job) is False

    # Empty list
    spec_empty = CompanyExclusionSpecification([])
    assert spec_empty.is_satisfied_by(sample_job) is False


def test_title_exclusion_specification(sample_job):
    spec = TitleExclusionSpecification(["Python", "Java"])
    assert spec.is_satisfied_by(sample_job) is True

    spec_not_matched = TitleExclusionSpecification(["Manager", "Lead"])
    assert spec_not_matched.is_satisfied_by(sample_job) is False

    spec_empty = TitleExclusionSpecification([])
    assert spec_empty.is_satisfied_by(sample_job) is False


def test_description_exclusion_specification(sample_job):
    spec = DescriptionExclusionSpecification(["Django", "Node.js"])
    assert spec.is_satisfied_by(sample_job) is True

    spec_not_matched = DescriptionExclusionSpecification(["Java", "Spring"])
    assert spec_not_matched.is_satisfied_by(sample_job) is False

    spec_empty = DescriptionExclusionSpecification([])
    assert spec_empty.is_satisfied_by(sample_job) is False


def test_and_specification(sample_job):
    spec1 = TitleExclusionSpecification(["Python"])
    spec2 = CompanyExclusionSpecification(["Awesome"])
    spec3 = DescriptionExclusionSpecification(["Java"])  # returns False

    and_spec_success = AndSpecification(spec1, spec2)
    assert and_spec_success.is_satisfied_by(sample_job) is True

    and_spec_failure = AndSpecification(spec1, spec3)
    assert and_spec_failure.is_satisfied_by(sample_job) is False

    # Using & operator
    operator_spec_success = spec1 & spec2
    assert operator_spec_success.is_satisfied_by(sample_job) is True

    operator_spec_failure = spec1 & spec3
    assert operator_spec_failure.is_satisfied_by(sample_job) is False


def test_or_specification(sample_job):
    spec1 = TitleExclusionSpecification(["Python"])
    spec2 = DescriptionExclusionSpecification(["Java"])  # False

    or_spec_success = OrSpecification(spec1, spec2)
    assert or_spec_success.is_satisfied_by(sample_job) is True

    or_spec_failure = OrSpecification(spec2, DescriptionExclusionSpecification(["Spring"]))
    assert or_spec_failure.is_satisfied_by(sample_job) is False

    # Using | operator
    operator_spec_success = spec1 | spec2
    assert operator_spec_success.is_satisfied_by(sample_job) is True


def test_not_specification(sample_job):
    spec = TitleExclusionSpecification(["Java"])  # False
    not_spec = NotSpecification(spec)  # should be True
    assert not_spec.is_satisfied_by(sample_job) is True

    # Using ~ operator
    operator_spec = ~spec
    assert operator_spec.is_satisfied_by(sample_job) is True


def test_complex_composite_specification(sample_job):
    comp_spec = CompanyExclusionSpecification(["Awesome"])
    title_spec = TitleExclusionSpecification(["Java"])
    desc_spec = DescriptionExclusionSpecification(["Django"])

    # (Company matches "Awesome" OR Title matches "Java") AND Description matches "Django"
    # (True OR False) AND True => True
    complex_spec = (comp_spec | title_spec) & desc_spec
    assert complex_spec.is_satisfied_by(sample_job) is True

    # (Company matches "Awesome" AND Title matches "Java") OR NOT Description matches "Django"
    # (True AND False) OR NOT True => False OR False => False
    complex_spec_2 = (comp_spec & title_spec) | ~desc_spec
    assert complex_spec_2.is_satisfied_by(sample_job) is False
