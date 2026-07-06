import pytest
from src.naukri_agent.models.entities import Job
from src.naukri_agent.models.rules import ConsultancyScamSpecification


@pytest.fixture
def spec() -> ConsultancyScamSpecification:
    return ConsultancyScamSpecification()


class TestConsultancyScamSpecification:
    def test_genuine_company_and_title(self, spec: ConsultancyScamSpecification):
        job = Job(
            naukri_job_id="123",
            title="Software Engineer - Backend",
            company="Product Inc",
            url="https://fake.com",
            description="Great job",
        )
        assert spec.is_satisfied_by(job) is False

    def test_genuine_startup_with_contact_info_passes(self, spec: ConsultancyScamSpecification):
        # 50 points, below threshold of 100
        job = Job(
            naukri_job_id="123",
            title="Python Developer",
            company="Nexus Tech",
            url="https://fake.com",
            description="Call 9876543210",
        )
        assert spec.is_satisfied_by(job) is False

    def test_genuine_walkin_passes(self, spec: ConsultancyScamSpecification):
        # 50 points, below threshold
        job = Job(
            naukri_job_id="123",
            title="Walk-in Drive for Java",
            company="Nexus Tech",
            url="https://fake.com",
        )
        assert spec.is_satisfied_by(job) is False

    def test_fake_hr_walkin_rejected(self, spec: ConsultancyScamSpecification):
        # 30 (HR name) + 40 (Walkin) + 100 (Gmail in title) = 170 points, Rejected!
        job = Job(
            naukri_job_id="123",
            title="Walkin for Freshers hr@gmail.com",
            company="Creative Hands HR",
            url="https://fake.com",
            description="Send resume to hr@gmail.com",
        )
        assert spec.is_satisfied_by(job) is True

    def test_bpo_hr_rejected(self, spec: ConsultancyScamSpecification):
        # 80 (Night shift/voice) + 30 (HR name) = 110 points, Rejected!
        job = Job(
            naukri_job_id="123",
            title="Night shift (International voice), Freshers",
            company="Creative Hands HR",
            url="https://fake.com",
        )
        assert spec.is_satisfied_by(job) is True

    @pytest.mark.parametrize(
        "scam_desc",
        [
            "You need to pay a registration fee of 500.",
            "A security deposit is required.",
            "We have laptop charges.",
            "This is a refundable amount.",
            "Pay before joining.",
            "Direct selection without interview.",
        ],
    )
    def test_financial_scam_rejected_instantly(
        self, spec: ConsultancyScamSpecification, scam_desc: str
    ):
        # 100 points, instant reject
        job = Job(
            naukri_job_id="123",
            title="Software Developer",
            company="Product Inc",
            url="https://fake.com",
            description=f"Great job opportunity! {scam_desc}",
        )
        assert spec.is_satisfied_by(job) is True

    @pytest.mark.parametrize(
        "whitelist_company",
        [
            "Tata Consultancy Services",
            "Wipro",
            "Infosys",
            "Accenture",
            "Cognizant",
            "Capgemini",
        ],
    )
    def test_whitelist_bypasses_scam_detection(
        self, spec: ConsultancyScamSpecification, whitelist_company: str
    ):
        # Even if the title is suspicious (BPO + Walkin = 130 pts), the whitelist (-500 pts) protects it
        job = Job(
            naukri_job_id="123",
            title="Walk-in for BPO",
            company=whitelist_company,
            url="https://fake.com",
        )
        assert spec.is_satisfied_by(job) is False
