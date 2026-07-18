"""
Comprehensive test suite for the fake/job scam detection system.

Covers:
  - All 26+ scam signals (S1-S26)
  - All 4 genuine signals (G1-G4)
  - ConsultancyScamSpecification (threshold = 80)
  - All exclusion specifications (Company, Title, Description, Authenticity)
  - FakeJobDetectionPipeline (all 5 stages)
  - Edge cases: empty fields, None values, boundary conditions
"""

import pytest
from src.naukri_agent.models.entities import Job
from src.naukri_agent.config.settings import ExclusionSettings
from src.naukri_agent.fake_job_detection import (
    ConsultancyScamSpecification,
    CompanyExclusionSpecification,
    TitleExclusionSpecification,
    DescriptionExclusionSpecification,
    AuthenticityExclusionSpecification,
    FakeJobDetectionPipeline,
    compute_scam_score,
    ScamScoreResult,
)


# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture
def spec() -> ConsultancyScamSpecification:
    return ConsultancyScamSpecification()


@pytest.fixture
def genuine_job() -> Job:
    return Job(
        naukri_job_id="1",
        title="Software Engineer - Backend",
        company="Product Inc",
        url="https://example.com",
        description="Great job with Python, Django, and PostgreSQL.",
    )


@pytest.fixture
def pipeline() -> FakeJobDetectionPipeline:
    settings = ExclusionSettings(
        enable_scam_filter=True,
        companies=["Blocked Corp", "TeleInfoTech"],
        fake_company_blocklist=["Fake Company Ltd"],
        max_openings_without_logo=25,
        title_keywords=["support", "data entry"],
        description_keywords=["send your resume", "pay fee"],
    )
    return FakeJobDetectionPipeline(settings)


# ======================================================================
# G1: Genuine — Whitelist Company
# ======================================================================

class TestG1_WhitelistCompany:
    """G1: Known reputed companies get -500, bypassing all scam signals."""

    @pytest.mark.parametrize("company", [
        "Tata Consultancy Services", "TCS", "Wipro", "Infosys",
        "Accenture", "Cognizant", "Capgemini", "IBM",
        "Amazon", "Google", "Microsoft", "Meta",
        "Tech Mahindra", "HCL", "L&T", "Zoho",
    ])
    def test_whitelist_bypasses_all_scam_signals(self, spec, company):
        """Whitelist company (-500) overrides even strong scam signals like BPO + Walk-in (130)."""
        job = Job(
            naukri_job_id="123",
            title="Walk-in for BPO",
            company=company,
            url="https://fake.com",
        )
        assert spec.is_satisfied_by(job) is False

    def test_whitelist_not_triggered_for_non_whitelisted(self, spec):
        """Non-whitelisted company does not get the -500 bonus."""
        job = Job(
            naukri_job_id="123",
            title="Software Developer",
            company="Unknown Startup",
            url="https://fake.com",
        )
        result = compute_scam_score(job)
        assert "Known reputed company" not in " ".join(result.reasons)


# ======================================================================
# G2: Genuine — Company Logo
# ======================================================================

class TestG2_CompanyLogo:
    """G2: Verified company logo gives -30."""

    def test_logo_reduces_score(self):
        """Job with logo should have lower raw_score than identical job without."""
        job_with_logo = Job(
            naukri_job_id="1", title="Developer", company="Some Corp",
            has_company_logo=True, url="", location="", experience="", salary="",
        )
        job_without_logo = Job(
            naukri_job_id="2", title="Developer", company="Some Corp",
            has_company_logo=False, url="", location="", experience="", salary="",
        )
        score_with = compute_scam_score(job_with_logo).raw_score
        score_without = compute_scam_score(job_without_logo).raw_score
        assert score_with == score_without - 30


# ======================================================================
# G3: Genuine — Technical Description
# ======================================================================

class TestG3_TechnicalDescription:
    """G3: Detailed tech description reduces score by -50 (2+ categories, 400+ chars) or -20."""

    def test_detailed_tech_desc_large_reduction(self, spec):
        """400+ chars with 2+ tech categories → -50."""
        job = Job(
            naukri_job_id="1", title="Backend Developer", company="NovaTech Solutions",
            url="https://fake.com",
            description=(
                "Build REST APIs using Python, FastAPI, PostgreSQL, and Redis. "
                "Deploy on AWS ECS with Docker containers. We are looking for a skilled "
                "backend engineer with 3+ years of experience in designing and building "
                "scalable microservices. You will work on our core platform serving millions "
                "of users across multiple regions. The ideal candidate has strong experience "
                "with Python backend development, RESTful API design, and cloud-native "
                "architectures. We offer competitive compensation and a great work culture."
            ),
            has_company_logo=True,
        )
        assert spec.is_satisfied_by(job) is False
        result = compute_scam_score(job)
        assert any("Detailed technical description" in r for r in result.reasons)

    def test_tech_skills_small_reduction(self):
        """Tech skills present but < 2 categories or < 400 chars → -20."""
        job = Job(
            naukri_job_id="1", title="Developer", company="Some Corp",
            url="", location="", experience="", salary="",
            description="We need Python and Django skills.",
        )
        result = compute_scam_score(job)
        assert any("Technical skills in description (-20)" in r for r in result.reasons)


# ======================================================================
# G4: Genuine — Salary Mentioned
# ======================================================================

class TestG4_SalaryMentioned:
    """G4: Salary mentioned in description gives -15."""

    def test_salary_in_description_reduces_score(self):
        job = Job(
            naukri_job_id="1", title="Developer", company="Some Corp",
            url="", location="", experience="", salary="",
            description="Salary: 12 LPA. We need a Python developer.",
        )
        result = compute_scam_score(job)
        assert any("Salary mentioned" in r for r in result.reasons)

    def test_salary_not_triggered_for_missing(self):
        job = Job(
            naukri_job_id="1", title="Developer", company="Some Corp",
            url="", location="", experience="", salary="",
        )
        result = compute_scam_score(job)
        assert not any("Salary mentioned" in r for r in result.reasons)


# ======================================================================
# S1: Financial Scam
# ======================================================================

class TestS1_FinancialScam:
    """S1: Financial scam terms (+200) instantly exclude."""

    @pytest.mark.parametrize("scam_desc", [
        "You need to pay a registration fee of 500.",
        "A security deposit is required.",
        "We have laptop charges.",
        "This is a refundable amount.",
        "Pay before joining.",
        "Direct selection without interview.",
        "Consultancy charges apply.",
        "Pay amount of 2000 for processing.",
    ])
    def test_financial_scam_rejected_instantly(self, spec, scam_desc):
        job = Job(
            naukri_job_id="123", title="Software Developer", company="Product Inc",
            url="https://fake.com", description=f"Great job opportunity! {scam_desc}",
        )
        assert spec.is_satisfied_by(job) is True

    def test_financial_scam_raw_score_at_least_200(self):
        job = Job(
            naukri_job_id="1", title="Developer", company="Unknown",
            url="", location="", experience="", salary="",
            description="Pay registration fee of 500.",
        )
        result = compute_scam_score(job)
        assert result.raw_score >= 200


# ======================================================================
# S2: WhatsApp Number
# ======================================================================

class TestS2_WhatsApp:
    """S2: WhatsApp number in description (+120)."""

    def test_whatsapp_number_rejected(self, spec):
        job = Job(
            naukri_job_id="123", title="Software Developer", company="Some Firm",
            url="https://fake.com", description="WhatsApp your resume at 9876543210",
        )
        assert spec.is_satisfied_by(job) is True

    def test_whatsapp_with_country_code_rejected(self, spec):
        job = Job(
            naukri_job_id="123", title="Python Developer", company="Tech Solutions",
            url="https://fake.com", description="Contact us on WhatsApp +91 9876543210 for interview.",
        )
        assert spec.is_satisfied_by(job) is True

    def test_whatsapp_score_at_least_120(self):
        job = Job(
            naukri_job_id="1", title="Developer", company="Some Corp",
            url="", location="", experience="", salary="",
            description="WhatsApp 9876543210",
        )
        result = compute_scam_score(job)
        assert result.raw_score >= 120


# ======================================================================
# S3: Resume Request
# ======================================================================

class TestS3_ResumeRequest:
    """S3: Resume request in description (+80), stacks with short desc (+60) = 140 → excluded."""

    @pytest.mark.parametrize("desc", [
        "Send your resume to us for processing.",
        "Share your CV with our HR team.",
        "Forward your resume at our email.",
        "Email your CV to apply.",
    ])
    def test_resume_request_rejected(self, spec, desc):
        job = Job(
            naukri_job_id="123", title="Software Developer", company="Unknown Corp",
            url="https://fake.com", description=desc,
        )
        assert spec.is_satisfied_by(job) is True


# ======================================================================
# S4: Contact HR
# ======================================================================

class TestS4_ContactHR:
    """S4: Contact HR in description (+60), stacks with short desc (+60) = 120 → excluded."""

    @pytest.mark.parametrize("desc", [
        "Contact HR for more details.",
        "Call us at this number.",
        "Contact recruiter directly.",
        "WhatsApp your resume for quick response.",
    ])
    def test_contact_hr_rejected(self, spec, desc):
        job = Job(
            naukri_job_id="123", title="Java Developer", company="Some Company",
            url="https://fake.com", description=desc,
        )
        assert spec.is_satisfied_by(job) is True


# ======================================================================
# S5: Freshers Advertisement
# ======================================================================

class TestS5_FreshersAd:
    """S5: Freshers ad patterns (+70), stacks with short desc (+60) = 130 → excluded."""

    @pytest.mark.parametrize("desc", [
        "Freshers welcome to apply for this role.",
        "BCA/BSc/BTech freshers can apply.",
        "Hiring for BCA graduates.",
        "Any graduate can apply for this position.",
        "Freshers only need to apply.",
    ])
    def test_freshers_ad_rejected(self, spec, desc):
        job = Job(
            naukri_job_id="123", title="Junior Developer", company="Unknown Firm",
            url="https://fake.com", description=desc,
        )
        assert spec.is_satisfied_by(job) is True


# ======================================================================
# S6: Generic Description
# ======================================================================

class TestS6_GenericDescription:
    """S6: Generic soft-skills-only description (+50), stacks with short desc (+60) = 110 → excluded."""

    def test_generic_description_short_rejected(self, spec):
        job = Job(
            naukri_job_id="123", title="Java Developer", company="Unknown",
            url="https://fake.com", description="Good communication skills required.",
        )
        assert spec.is_satisfied_by(job) is True

    def test_generic_description_scores_50(self):
        job = Job(
            naukri_job_id="1", title="Developer", company="Some Corp",
            url="", location="", experience="", salary="",
            description="Good communication skills. Team player. Quick learner.",
        )
        result = compute_scam_score(job)
        assert any("Generic description" in r for r in result.reasons)


# ======================================================================
# S7: Multi-City Hiring
# ======================================================================

class TestS7_MultiCity:
    """S7: Multi-city hiring (+60), stacks with short desc (+60) = 120 → excluded."""

    @pytest.mark.parametrize("desc", [
        "Location: Bangalore, Pune, Mumbai",
        "Openings in Pune, Mumbai, Hyderabad",
        "Hiring for Bangalore - Pune - Chennai",
    ])
    def test_multi_city_rejected(self, spec, desc):
        job = Job(
            naukri_job_id="123", title="Software Developer", company="Unknown",
            url="https://fake.com", description=desc,
        )
        assert spec.is_satisfied_by(job) is True


# ======================================================================
# S8: Immediate Joining
# ======================================================================

class TestS8_ImmediateJoining:
    """S8: Immediate joining (+50), stacks with short desc (+60) = 110 → excluded."""

    @pytest.mark.parametrize("desc", [
        "Immediate joining required.",
        "Urgent hiring for this position.",
        "Need candidates who can join immediately.",
    ])
    def test_immediate_joining_rejected(self, spec, desc):
        job = Job(
            naukri_job_id="123", title="Python Developer", company="Some Corp",
            url="https://fake.com", description=desc,
        )
        assert spec.is_satisfied_by(job) is True


# ======================================================================
# S9: Short Description Without Tech
# ======================================================================

class TestS9_ShortDescription:
    """S9: Short description (<150 chars, no tech skills) adds +60."""

    def test_short_desc_no_tech_rejected_with_other_signals(self, spec):
        """Short desc (+60) + generic services company (+120) = 180 → excluded."""
        job = Job(
            naukri_job_id="123", title="Java Developer", company="Management Services India",
            url="https://fake.com", description="We are hiring.",
        )
        assert spec.is_satisfied_by(job) is True

    def test_short_desc_with_tech_does_not_trigger(self):
        """Short desc with tech skills should NOT trigger S9."""
        job = Job(
            naukri_job_id="1", title="Developer", company="Some Corp",
            url="", location="", experience="", salary="",
            description="Python developer needed.",  # < 150 chars but has tech skills
        )
        result = compute_scam_score(job)
        # S9 is not triggered because _TECH_SKILLS_RE matches "Python"
        assert not any("Very short description" in r for r in result.reasons)

    def test_short_desc_scores_60(self):
        job = Job(
            naukri_job_id="1", title="Developer", company="Some Corp",
            url="", location="", experience="", salary="",
            description="Hiring now.",  # < 150 chars, no tech skills
        )
        result = compute_scam_score(job)
        assert any("Very short description" in r for r in result.reasons)
        assert result.raw_score >= 60


# ======================================================================
# S10: Phone in Title/Company
# ======================================================================

class TestS10_PhoneInTitleOrCompany:
    """S10: Phone number in title or company (+100) → excluded alone."""

    def test_phone_in_company_rejected(self, spec):
        job = Job(
            naukri_job_id="123", title="Software Developer", company="Call 9876543210",
            url="https://fake.com",
        )
        assert spec.is_satisfied_by(job) is True

    def test_phone_in_title_rejected(self, spec):
        job = Job(
            naukri_job_id="123", title="Developer Call 9876543210", company="Some Corp",
            url="https://fake.com",
        )
        assert spec.is_satisfied_by(job) is True

    def test_phone_score_at_least_100(self):
        job = Job(
            naukri_job_id="1", title="Developer 9876543210", company="Unknown",
            url="", location="", experience="", salary="",
        )
        result = compute_scam_score(job)
        assert result.raw_score >= 100


# ======================================================================
# S11: Personal Email in Title/Company
# ======================================================================

class TestS11_EmailInTitleOrCompany:
    """S11: Personal email in title or company (+100) → excluded alone."""

    def test_email_in_title_rejected(self, spec):
        job = Job(
            naukri_job_id="123", title="Java Developer hr@gmail.com", company="Some Corp",
            url="https://fake.com",
        )
        assert spec.is_satisfied_by(job) is True

    def test_email_in_company_rejected(self, spec):
        job = Job(
            naukri_job_id="123", title="Developer", company="hr@gmail.com",
            url="https://fake.com",
        )
        assert spec.is_satisfied_by(job) is True


# ======================================================================
# S12: Agency Keywords
# ======================================================================

class TestS12_AgencyKeywords:
    """S12a: Agency in company (+200), S12b: Agency in title (+100)."""

    @pytest.mark.parametrize("company", [
        "ABC Placement Services",
        "XYZ Staffing Solutions",
        "Manpower Services India",
        "Recruitment Agency Mumbai",
        "Talent Acquisition Hub",
        "HR Consultancy Pvt Ltd",
    ])
    def test_agency_in_company_rejected(self, spec, company):
        """"Agency in company (+200) exceeds threshold even with logo + tech desc."""
        job = Job(
            naukri_job_id="123", title="Software Developer", company=company,
            url="https://fake.com",
            description="We need a Python developer with Django and SQL skills for our client.",
            has_company_logo=True,
        )
        assert spec.is_satisfied_by(job) is True

    def test_agency_in_title_only_rejected(self, spec):
        """Agency in title (+100) + short desc (+60) = 160 → excluded."""
        job = Job(
            naukri_job_id="123", title="Placement Coordinator", company="Some Corp",
            url="https://fake.com", description="Hiring freshers.",
        )
        assert spec.is_satisfied_by(job) is True

    def test_agency_with_good_desc_still_rejected(self, spec):
        """Agency in company (+200) overwhelms all genuine signals except whitelist."""
        job = Job(
            naukri_job_id="123", title="Senior Python Developer", company="ABC Staffing Solutions",
            url="https://fake.com",
            description=(
                "We are hiring for one of our MNC clients. Position: Senior Python Developer "
                "with 5+ years experience in Django, FastAPI, PostgreSQL, Redis, Docker, "
                "Kubernetes, AWS. Must have strong system design skills."
            ),
            has_company_logo=True,
        )
        # 200 (agency) - 30 (logo) - 50 (tech desc) = 120 >= 80 → excluded
        assert spec.is_satisfied_by(job) is True


# ======================================================================
# S13: Education/Training Company
# ======================================================================

class TestS13_EducationTraining:
    """S13: Education/training company (+120), stacks with short desc (+60) = 180 → excluded."""

    @pytest.mark.parametrize("company", [
        "Education Foundation India",
        "Skill Development Academy",
        "Career Solution Centre",
        "Training Institute for IT",
    ])
    def test_education_training_rejected(self, spec, company):
        job = Job(
            naukri_job_id="123", title="Software Developer", company=company,
            url="https://fake.com", description="Call us for more details.",
        )
        assert spec.is_satisfied_by(job) is True


# ======================================================================
# S14: Generic Services Company
# ======================================================================

class TestS14_GenericServices:
    """S14: Generic services company (+120), stacks with short desc (+60) = 180 → excluded."""

    @pytest.mark.parametrize("company", [
        "Management Services India",
        "Global Business Services",
        "Enterprise Corporate Services",
    ])
    def test_generic_services_rejected(self, spec, company):
        job = Job(
            naukri_job_id="123", title="Java Developer", company=company,
            url="https://fake.com", description="We are hiring.",
        )
        assert spec.is_satisfied_by(job) is True


# ======================================================================
# S15: BPO/Staffing Keywords
# ======================================================================

class TestS15_BPOKeywords:
    """S15: BPO/staffing keywords (+100) → excluded with any other signal."""

    def test_bpo_hr_rejected(self, spec):
        """BPO in title (100) + HR agency in company (200) = 300 → excluded."""
        job = Job(
            naukri_job_id="123", title="Night shift (International voice), Freshers",
            company="Creative Hands HR",
            url="https://fake.com",
        )
        assert spec.is_satisfied_by(job) is True

    def test_bpo_alone_not_quite_threshold(self):
        """BPO alone (+100) needs at least one more signal for threshold 80."""
        # Wait, 100 >= 80, so even BPO alone should be excluded!
        # Let me verify: _BPO_RE searches combined_text (title + company)
        job = Job(
            naukri_job_id="1", title="BPO Executive", company="Some Corp",
            url="", location="", experience="", salary="",
        )
        result = compute_scam_score(job)
        assert result.raw_score >= 80


# ======================================================================
# S16: Walk-in Hiring
# ======================================================================

class TestS16_Walkin:
    """S16: Walk-in keywords in title (+80) reaches threshold alone."""

    def test_walkin_drive_rejected(self, spec):
        """Walk-in in title (+80) = 80 >= 80 → excluded."""
        job = Job(
            naukri_job_id="123", title="Walk-in Drive for Java", company="Nexus Tech",
            url="https://fake.com",
        )
        assert spec.is_satisfied_by(job) is True

    def test_walkin_with_email_rejected(self, spec):
        """Walkin (+80) + email in title (+100) + freshers (+70) + agency in company (+200) = 450 → excluded."""
        job = Job(
            naukri_job_id="123", title="Walkin for Freshers hr@gmail.com",
            company="Creative Hands HR",
            url="https://fake.com", description="Send resume to hr@gmail.com",
        )
        assert spec.is_satisfied_by(job) is True


# ======================================================================
# S17: Hidden Company Name
# ======================================================================

class TestS17_HiddenCompany:
    """S17: Hidden/generic company name (+100) → excluded alone."""

    @pytest.mark.parametrize("company", [
        "MNC", "Confidential", "Leading IT Company", "Top IT Client",
        "Startup", "Leading Client", "Undisclosed",
    ])
    def test_hidden_company_rejected(self, spec, company):
        job = Job(
            naukri_job_id="123", title="Software Developer", company=company,
            url="https://fake.com",
        )
        assert spec.is_satisfied_by(job) is True

    def test_hidden_company_not_false_positive(self):
        """Company name containing 'startup' as part of larger name should not trigger."""
        job = Job(
            naukri_job_id="1", title="Developer", company="StartupHub Technologies",
            url="", location="", experience="", salary="",
        )
        result = compute_scam_score(job)
        # "StartupHub" does not match ^startup$ pattern
        assert not any("Hidden/generic company" in r for r in result.reasons)


# ======================================================================
# S18: Suspicious Company Suffix
# ======================================================================

class TestS18_CompanySuffix:
    """S18: Suspicious company name suffix (+40)."""

    @pytest.mark.parametrize("company", [
        "Tech Associates", "Global Enterprises", "Digital Ventures",
        "HR Synergies", "Manpower Solutions", "Best Recruiters",
    ])
    def test_company_suffix_adds_points(self, company):
        job = Job(
            naukri_job_id="1", title="Developer", company=company,
            url="", location="", experience="", salary="",
        )
        result = compute_scam_score(job)
        assert any("Suspicious company suffix" in r for r in result.reasons)
        assert result.raw_score >= 40


# ======================================================================
# S19: Year Number in Company Name
# ======================================================================

class TestS19_YearInCompany:
    """S19: Year number in company name (+50), stacks with short desc (+60) = 110 → excluded."""

    def test_year_in_company_rejected(self, spec):
        job = Job(
            naukri_job_id="123", title="Software Developer", company="Placement 2025",
            url="https://fake.com", description="Great opportunity.",
        )
        assert spec.is_satisfied_by(job) is True

    def test_year_in_company_adds_50(self):
        job = Job(
            naukri_job_id="1", title="Developer", company="Tech 2024",
            url="", location="", experience="", salary="",
        )
        result = compute_scam_score(job)
        assert any("Year number in company name" in r for r in result.reasons)


# ======================================================================
# S20: No Logo + High Openings
# ======================================================================

class TestS20_NoLogoHighOpenings:
    """S20: No logo + high openings (+60)."""

    def test_no_logo_high_openings_adds_60(self):
        job = Job(
            naukri_job_id="1", title="Developer", company="Unknown",
            has_company_logo=False, openings=30,
            url="", location="", experience="", salary="",
        )
        result = compute_scam_score(job)
        assert any("No logo with high openings" in r for r in result.reasons)

    def test_logo_present_no_penalty(self):
        """Job with logo should not trigger S20 even with high openings."""
        job = Job(
            naukri_job_id="1", title="Developer", company="Known Corp",
            has_company_logo=True, openings=50,
            url="", location="", experience="", salary="",
        )
        result = compute_scam_score(job)
        assert not any("No logo with high openings" in r for r in result.reasons)

    def test_low_openings_no_penalty(self):
        """Job without logo but few openings should not trigger S20."""
        job = Job(
            naukri_job_id="1", title="Developer", company="Small Co",
            has_company_logo=False, openings=5,
            url="", location="", experience="", salary="",
        )
        result = compute_scam_score(job)
        assert not any("No logo with high openings" in r for r in result.reasons)


# ======================================================================
# S21: Phone Numbers in Description
# ======================================================================

class TestS21_PhonesInDescription:
    """S21a: 3+ phones (+120), S21b: 1-2 phones (+40)."""

    def test_single_phone_in_desc_adds_40(self):
        job = Job(
            naukri_job_id="1", title="Developer", company="Some Corp",
            url="", location="", experience="", salary="",
            description="Contact: 9876543210",
        )
        result = compute_scam_score(job)
        assert any("Phone number(s) in description" in r for r in result.reasons)
        assert result.raw_score >= 40

    def test_multiple_phones_adds_120(self):
        """3+ phone numbers should add +120."""
        job = Job(
            naukri_job_id="1", title="Developer", company="Some Corp",
            url="", location="", experience="", salary="",
            description="Contact: 9876543210, 9876543211, 9876543212",
        )
        result = compute_scam_score(job)
        assert any("Multiple phone numbers" in r for r in result.reasons)
        assert result.raw_score >= 120

    def test_no_phones_in_desc_no_penalty(self):
        job = Job(
            naukri_job_id="1", title="Developer", company="Some Corp",
            url="", location="", experience="", salary="",
            description="Python developer with Django experience.",
        )
        result = compute_scam_score(job)
        assert not any("Phone number" in r for r in result.reasons)


# ======================================================================
# S22: Overseas Recruiter
# ======================================================================

class TestS22_OverseasRecruiter:
    """S22a: Overseas in company/title (+200), S22b: Overseas in description (+80)."""

    @pytest.mark.parametrize("company", [
        "Germany Jobs Guide",
        "Abroad Work Opportunity",
        "Visa Consultant Services",
        "Immigration Help Desk",
    ])
    def test_overseas_in_company_rejected(self, spec, company):
        job = Job(
            naukri_job_id="123", title="Software Developer", company=company,
            url="https://fake.com",
        )
        assert spec.is_satisfied_by(job) is True

    def test_overseas_in_desc_adds_80(self):
        job = Job(
            naukri_job_id="1", title="Developer", company="Some Corp",
            url="", location="", experience="", salary="",
            description="Work in Germany opportunity.",
        )
        result = compute_scam_score(job)
        assert any("Overseas" in r for r in result.reasons)


# ======================================================================
# S23: Agency Solutions Pattern
# ======================================================================

class TestS23_AgencySolutionsPattern:
    """S23: Agency naming pattern (+80)."""

    @pytest.mark.parametrize("company", [
        "GIST Management Solutions",
        "Prime Career Solutions",
        "Global HR Solutions",
        "Best Talent Solutions",
    ])
    def test_solutions_pattern_adds_80(self, company):
        job = Job(
            naukri_job_id="1", title="Developer", company=company,
            url="", location="", experience="", salary="",
        )
        result = compute_scam_score(job)
        assert any("agency solutions pattern" in r for r in result.reasons)
        assert result.raw_score >= 80


# ======================================================================
# S25: Social Media Handle
# ======================================================================

class TestS25_SocialMedia:
    """S25: Social media handle in description (+80)."""

    @pytest.mark.parametrize("desc", [
        "Join our Telegram group @jobs",
        "Contact us on Instagram @company",
        "Apply at t.me/jobchannel",
        "Join our WhatsApp channel",
    ])
    def test_social_media_adds_80(self, desc):
        job = Job(
            naukri_job_id="1", title="Developer", company="Some Corp",
            url="", location="", experience="", salary="",
            description=desc,
        )
        result = compute_scam_score(job)
        assert any("Social media handle" in r for r in result.reasons)


# ======================================================================
# Composite: Multiple signals stacking
# ======================================================================

class TestCompositeSignals:
    """Multiple weak signals should stack to exceed threshold."""

    def test_multiple_weak_signals_stack_to_reject(self, spec):
        job = Job(
            naukri_job_id="123", title="Urgent Requirement for Fresher",
            company="HR Management Services",
            url="https://fake.com",
            description=(
                "Good communication skills required. "
                "Immediate joining. Freshers can apply. Multiple positions available."
            ),
        )
        # Generic services company (+120) + Freshers ad (+70)
        # + Generic desc (+50) + Immediate joining (+50) + Short desc (+60)
        # Total >= 100 → rejected
        assert spec.is_satisfied_by(job) is True

    def test_genuine_startup_with_contact_info_passes(self, spec):
        """Real startup with tech description + phone number should pass."""
        job = Job(
            naukri_job_id="123", title="Python Developer", company="Nexus Tech",
            url="https://fake.com",
            description=(
                "We are looking for a Python Developer with 1-3 years of experience in "
                "Django, FastAPI, PostgreSQL, and REST APIs. You will build backend services "
                "for our SaaS platform. Experience with Docker and AWS is a plus. "
                "Contact: 9876543210"
            ),
        )
        assert spec.is_satisfied_by(job) is False

    def test_genuine_jobs_with_services_in_name_pass(self, spec):
        """IT services companies that are genuine should pass scam filter."""
        test_cases = [
            ("Senior Full Stack Developer", "Persistent Systems",
             "We are looking for a Senior Full Stack Developer with 3+ years of experience in Python, Django, React, PostgreSQL, Docker, and AWS."),
            ("Java Spring Boot Developer", "Happiest Minds Technologies",
             "Hiring a Java Developer with strong Spring Boot, Microservices, Hibernate, and MySQL skills."),
            ("Software Engineer", "Oracle Financial Services",
             "Software Engineer position. You will work on core banking platform using Java, Spring, React, and Oracle DB."),
            ("Associate Software Developer", "Tech Mahindra",
             "Associate Software Developer needed for our Pune office. Tech stack: Angular, Node.js, MongoDB, AWS."),
        ]
        for title, company, desc in test_cases:
            job = Job(
                naukri_job_id="123", title=title, company=company,
                url="https://fake.com", description=desc, has_company_logo=True,
            )
            assert spec.is_satisfied_by(job) is False, (
                f"Genuine job '{title} @ {company}' should pass scam filter"
            )

    def test_genuine_job_with_empty_desc_with_logo_passes(self, spec):
        """Job with logo but no description should pass (no description to penalize)."""
        job = Job(
            naukri_job_id="123", title="Software Engineer", company="Genuine Product Co",
            url="https://fake.com", has_company_logo=True,
        )
        assert spec.is_satisfied_by(job) is False


# ======================================================================
# ScamScoreResult: Level Classification
# ======================================================================

class TestScamScoreResultLevels:
    """Verify level thresholds: safe (<30), moderate (30-79), suspicious (80+)."""

    def test_safe_level(self):
        job = Job(
            naukri_job_id="1", title="Developer", company="TCS",
            url="", location="", experience="", salary="",
        )
        result = compute_scam_score(job)
        assert result.level == "safe"
        assert result.score == 0

    def test_moderate_level(self):
        """A job with some generic language but long enough to avoid S9."""
        job = Job(
            naukri_job_id="1", title="Developer", company="Some Corp",
            url="", location="", experience="", salary="",
            description=(
                "We are looking for a developer with good communication skills "
                "and basic programming knowledge. The ideal candidate should be "
                "a quick learner and team player with a positive attitude. "
                "This is a great opportunity to work with experienced professionals "
                "and grow your career in a supportive environment."
            ),
        )
        result = compute_scam_score(job)
        assert result.level == "moderate"

    def test_suspicious_level(self):
        """A job with agency keywords should be suspicious."""
        job = Job(
            naukri_job_id="1", title="Developer", company="ABC Placement Services",
            url="", location="", experience="", salary="",
        )
        result = compute_scam_score(job)
        assert result.level == "suspicious"
        assert result.raw_score >= 80


# ======================================================================
# Exclusion Specifications
# ======================================================================

class TestCompanyExclusionSpecification:
    """CompanyExclusionSpecification: exact/partial match against blocklist."""

    def test_matches_blocked_company(self):
        spec = CompanyExclusionSpecification(["Blocked Corp", "Bad Company"])
        job = Job(naukri_job_id="1", title="Dev", company="Blocked Corp", url="")
        assert spec.is_satisfied_by(job) is True

    def test_no_match(self):
        spec = CompanyExclusionSpecification(["Blocked Corp"])
        job = Job(naukri_job_id="1", title="Dev", company="Good Company", url="")
        assert spec.is_satisfied_by(job) is False

    def test_empty_blocklist(self):
        spec = CompanyExclusionSpecification([])
        job = Job(naukri_job_id="1", title="Dev", company="Any Corp", url="")
        assert spec.is_satisfied_by(job) is False

    def test_case_insensitive(self):
        spec = CompanyExclusionSpecification(["blocked"])
        job = Job(naukri_job_id="1", title="Dev", company="BLOCKED Corp", url="")
        assert spec.is_satisfied_by(job) is True


class TestTitleExclusionSpecification:
    """TitleExclusionSpecification: keyword match with word boundaries."""

    def test_matches_keyword(self):
        spec = TitleExclusionSpecification(["support", "data entry"])
        job = Job(naukri_job_id="1", title="Technical Support Engineer", company="Co", url="")
        assert spec.is_satisfied_by(job) is True

    def test_no_false_positive_substring(self):
        """'sales' should NOT match 'Salesforce' due to word boundary."""
        spec = TitleExclusionSpecification(["sales"])
        job = Job(naukri_job_id="1", title="Salesforce Developer", company="Co", url="")
        assert spec.is_satisfied_by(job) is False

    def test_no_match(self):
        spec = TitleExclusionSpecification(["manager"])
        job = Job(naukri_job_id="1", title="Developer", company="Co", url="")
        assert spec.is_satisfied_by(job) is False

    def test_empty_keywords(self):
        spec = TitleExclusionSpecification([])
        job = Job(naukri_job_id="1", title="Developer", company="Co", url="")
        assert spec.is_satisfied_by(job) is False


class TestDescriptionExclusionSpecification:
    """DescriptionExclusionSpecification: keyword match in description."""

    def test_matches_keyword(self):
        spec = DescriptionExclusionSpecification(["send your resume"])
        job = Job(naukri_job_id="1", title="Dev", company="Co", url="", description="Please send your resume to apply.")
        assert spec.is_satisfied_by(job) is True

    def test_no_match(self):
        spec = DescriptionExclusionSpecification(["pay fee"])
        job = Job(naukri_job_id="1", title="Dev", company="Co", url="", description="Great job opportunity.")
        assert spec.is_satisfied_by(job) is False

    def test_empty_keywords(self):
        spec = DescriptionExclusionSpecification([])
        job = Job(naukri_job_id="1", title="Dev", company="Co", url="", description="Anything.")
        assert spec.is_satisfied_by(job) is False


class TestAuthenticityExclusionSpecification:
    """AuthenticityExclusionSpecification: 3 checks — blocklist, hidden name, no-logo+high openings."""

    def test_blocked_company(self):
        spec = AuthenticityExclusionSpecification(["Fake Company Ltd"], max_openings_without_logo=25)
        job = Job(naukri_job_id="1", title="Dev", company="Fake Company Ltd", url="")
        assert spec.is_satisfied_by(job) is True

    def test_hidden_company_name(self):
        spec = AuthenticityExclusionSpecification([], max_openings_without_logo=25)
        job = Job(naukri_job_id="1", title="Dev", company="MNC", url="")
        assert spec.is_satisfied_by(job) is True

    def test_no_logo_high_openings(self):
        spec = AuthenticityExclusionSpecification([], max_openings_without_logo=25)
        job = Job(
            naukri_job_id="1", title="Dev", company="Some Co", url="",
            has_company_logo=False, openings=30,
        )
        assert spec.is_satisfied_by(job) is True

    def test_no_logo_low_openings_passes(self):
        spec = AuthenticityExclusionSpecification([], max_openings_without_logo=25)
        job = Job(
            naukri_job_id="1", title="Dev", company="Some Co", url="",
            has_company_logo=False, openings=5,
        )
        assert spec.is_satisfied_by(job) is False

    def test_logo_present_high_openings_passes(self):
        spec = AuthenticityExclusionSpecification([], max_openings_without_logo=25)
        job = Job(
            naukri_job_id="1", title="Dev", company="Some Co", url="",
            has_company_logo=True, openings=50,
        )
        assert spec.is_satisfied_by(job) is False

    def test_all_checks_pass(self):
        """Job that passes all authenticity checks."""
        spec = AuthenticityExclusionSpecification([], max_openings_without_logo=25)
        job = Job(
            naukri_job_id="1", title="Dev", company="Genuine Co",
            url="", has_company_logo=True, openings=10,
        )
        assert spec.is_satisfied_by(job) is False


# ======================================================================
# FakeJobDetectionPipeline
# ======================================================================

class TestPipeline_Stage1_EarlyScamFilter:
    """Stage 1: Early scam pass using title/company only."""

    def test_early_filter_removes_scam_jobs(self, pipeline):
        jobs = [
            Job(naukri_job_id="1", title="Developer", company="TCS", url=""),
            Job(naukri_job_id="2", title="Walk-in Drive", company="Unknown", url=""),
            Job(naukri_job_id="3", title="Developer", company="ABC Placement Services", url=""),
        ]
        clean, scam = pipeline.early_scam_filter(jobs)
        # Walk-in Drive (score 80) passes Stage 1 (threshold 200), caught by deep check later
        assert len(clean) == 2
        assert len(scam) == 1
        assert clean[0].company == "TCS"
        assert clean[1].company == "Unknown"

    def test_early_filter_disabled_returns_all(self):
        settings = ExclusionSettings(enable_scam_filter=False)
        p = FakeJobDetectionPipeline(settings)
        jobs = [
            Job(naukri_job_id="1", title="Developer", company="Placement Agency", url=""),
        ]
        clean, scam = p.early_scam_filter(jobs)
        assert len(clean) == 1
        assert len(scam) == 0

    def test_early_filter_empty_input(self, pipeline):
        clean, scam = pipeline.early_scam_filter([])
        assert clean == []
        assert scam == []


class TestPipeline_Stage2_3_ExclusionSpec:
    """Stages 2, 3: Exclusion specification composition."""

    def test_build_exclusion_spec(self, pipeline):
        spec = pipeline.build_exclusion_spec()
        assert spec is not None
        assert pipeline.exclusion_spec is not None

    def test_is_excluded_blocked_company(self, pipeline):
        pipeline.build_exclusion_spec()
        job = Job(naukri_job_id="1", title="Developer", company="Blocked Corp", url="")
        assert pipeline.is_excluded(job) is True

    def test_is_excluded_title_keyword(self, pipeline):
        pipeline.build_exclusion_spec()
        job = Job(naukri_job_id="1", title="Technical Support Engineer", company="Good Co", url="")
        assert pipeline.is_excluded(job) is True

    def test_is_excluded_description_keyword(self, pipeline):
        pipeline.build_exclusion_spec()
        job = Job(
            naukri_job_id="1", title="Developer", company="Good Co", url="",
            description="Please send your resume to apply.",
        )
        assert pipeline.is_excluded(job) is True

    def test_is_excluded_authenticity_blocked(self, pipeline):
        pipeline.build_exclusion_spec()
        job = Job(naukri_job_id="1", title="Dev", company="Fake Company Ltd", url="")
        assert pipeline.is_excluded(job) is True

    def test_is_excluded_authenticity_hidden(self, pipeline):
        pipeline.build_exclusion_spec()
        job = Job(naukri_job_id="1", title="Dev", company="MNC", url="")
        assert pipeline.is_excluded(job) is True

    def test_is_excluded_authenticity_no_logo_high_openings(self, pipeline):
        pipeline.build_exclusion_spec()
        job = Job(
            naukri_job_id="1", title="Dev", company="Unknown Co", url="",
            has_company_logo=False, openings=30,
        )
        assert pipeline.is_excluded(job) is True

    def test_deep_scam_check_catches_agency_job(self, pipeline):
        job = Job(
            naukri_job_id="1", title="Developer", company="ABC Placement Services",
            url="", description="Hiring freshers",
        )
        assert pipeline.deep_scam_check(job) is True

    def test_deep_scam_check_passes_genuine_job(self, pipeline):
        job = Job(
            naukri_job_id="1", title="Senior Python Developer", company="TCS",
            url="", description="Python, Django, React, PostgreSQL skills needed.",
            has_company_logo=True,
        )
        assert pipeline.deep_scam_check(job) is False

    def test_genuine_job_not_excluded(self, pipeline):
        pipeline.build_exclusion_spec()
        job = Job(
            naukri_job_id="1", title="Senior Python Developer", company="TCS",
            url="", description="Python, Django, React, PostgreSQL skills needed.",
            has_company_logo=True,
        )
        assert pipeline.is_excluded(job) is False

    def test_is_excluded_without_build_returns_false(self, pipeline):
        job = Job(naukri_job_id="1", title="Dev", company="Any", url="")
        assert pipeline.is_excluded(job) is False

    def test_is_excluded_scam_filter_disabled(self):
        settings = ExclusionSettings(enable_scam_filter=False)
        p = FakeJobDetectionPipeline(settings)
        p.build_exclusion_spec()
        # is_excluded only checks config blocklists, not consultancy scoring
        # Agency job without config blocklist match passes is_excluded
        job = Job(naukri_job_id="1", title="Developer", company="ABC Placement Services", url="")
        assert p.is_excluded(job) is False

    def test_is_excluded_dynamic_heuristic_bypasses_title(self, pipeline):
        pipeline.build_exclusion_spec()
        # This job title "Technical Support Engineer" matches title_keyword "support"
        # With heuristic_score=0.25 (above MIN_HEURISTIC_THRESHOLD=0.20),
        # title keyword exclusion should be bypassed, but company/authenticity/desc still apply
        job = Job(naukri_job_id="1", title="Technical Support Engineer", company="Good Co", url="")
        assert pipeline.is_excluded(job, heuristic_score=0.25) is False

    def test_is_excluded_dynamic_low_heuristic_still_blocks(self, pipeline):
        pipeline.build_exclusion_spec()
        # With low heuristic score (0.05, below 0.10 threshold), title exclusion should still apply
        job = Job(naukri_job_id="1", title="Technical Support Engineer", company="Good Co", url="")
        assert pipeline.is_excluded(job, heuristic_score=0.05) is True

    def test_is_excluded_dynamic_none_still_blocks(self, pipeline):
        pipeline.build_exclusion_spec()
        # No heuristic score = full spec used, title exclusion applies
        job = Job(naukri_job_id="1", title="Technical Support Engineer", company="Good Co", url="")
        assert pipeline.is_excluded(job) is True

    def test_is_excluded_dynamic_non_title_exclusions_always_apply(self, pipeline):
        pipeline.build_exclusion_spec()
        # Company blocklist should always apply regardless of heuristic score
        job = Job(naukri_job_id="1", title="Developer", company="Blocked Corp", url="")
        assert pipeline.is_excluded(job, heuristic_score=0.5) is True
        # Authenticity hidden company should always apply
        job2 = Job(naukri_job_id="1", title="Dev", company="MNC", url="")
        assert pipeline.is_excluded(job2, heuristic_score=0.5) is True
        # Description keyword should always apply
        job3 = Job(naukri_job_id="1", title="Developer", company="Good Co", url="",
                   description="Please send your resume to apply.")
        assert pipeline.is_excluded(job3, heuristic_score=0.5) is True


class TestPipeline_Stage4_Similarity:
    """Stage 4: TF-IDF similarity filter."""

    def test_check_similarity_no_text(self):
        passed, score = FakeJobDetectionPipeline.check_similarity("", None)
        assert passed is False
        assert score == 0.0


class TestPipeline_Properties:
    """Pipeline property accessors."""

    def test_is_scam_filter_enabled(self, pipeline):
        assert pipeline.is_scam_filter_enabled is True

    def test_is_scam_filter_disabled(self):
        p = FakeJobDetectionPipeline(ExclusionSettings(enable_scam_filter=False))
        assert p.is_scam_filter_enabled is False

    def test_exclusion_spec_before_build(self, pipeline):
        assert pipeline.exclusion_spec is None

    def test_exclusion_spec_after_build(self, pipeline):
        pipeline.build_exclusion_spec()
        assert pipeline.exclusion_spec is not None


# ======================================================================
# Edge Cases
# ======================================================================

class TestEdgeCases:
    """Edge cases: empty fields, None values, boundary conditions."""

    def test_empty_title_and_company(self):
        job = Job(
            naukri_job_id="1", title="", company="",
            url="", location="", experience="", salary="",
        )
        result = compute_scam_score(job)
        assert result.level == "safe"

    def test_none_description(self):
        job = Job(
            naukri_job_id="1", title="Developer", company="Some Corp",
            url="", location="", experience="", salary="",
            description=None,
        )
        result = compute_scam_score(job)
        assert result.score >= 0  # Should not crash

    def test_negative_raw_score_clamps_to_zero(self):
        job = Job(
            naukri_job_id="1", title="Developer", company="TCS",
            has_company_logo=True, url="", location="", experience="", salary="",
            description="Python, Django, React, PostgreSQL, Docker, AWS. " * 20,
        )
        result = compute_scam_score(job)
        assert result.score == 0  # Clamped to 0
        assert result.level == "safe"

    def test_raw_score_above_100_clamps(self):
        job = Job(
            naukri_job_id="1", title="Developer", company="ABC Placement Services",
            url="", location="", experience="", salary="",
            description="Pay registration fee of 500.",
        )
        result = compute_scam_score(job)
        assert result.score == 100  # Clamped to 100
        assert result.level == "suspicious"

    def test_pipeline_with_none_settings(self):
        with pytest.raises(ValueError):
            FakeJobDetectionPipeline(None)  # type: ignore
