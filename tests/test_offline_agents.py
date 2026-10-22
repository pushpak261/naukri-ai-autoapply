"""No API key or LLM calls are required for factual application decisions."""

from unittest.mock import AsyncMock
import pytest

from libs.common.screening import evidence_answer
from libs.common.local_matching import local_match
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.models.entities import ResumeProfile, Job


def test_factual_screening_units_ranges_and_unknown_declarations():
    settings = Settings(
        profile={
            "current_ctc": "4.4 LPA",
            "expected_ctc": "6 LPA",
            "notice_period": "Immediate",
            "skill_experience_years": {"Java": 1.5},
            "confirmed_answers": {"Are you willing to relocate to Pune?": "No"},
        }
    )
    profile = ResumeProfile(name="Candidate Example", total_experience_years=1.5)

    def answer(text, **kwargs):
        return evidence_answer({"question": text, **kwargs}, settings, profile)

    assert answer("First name") == "Candidate"
    assert answer("How many years of total work experience?", type="number") == "1.5"
    assert answer("How many months of experience with Java?", type="number") == "18"
    assert answer("How many years of experience with JavaScript?", type="number") == ""
    assert answer("Current CTC in INR per annum", type="number") == "440000"
    assert answer("Expected salary", options=["Below 5", "5-7", "Above 7"]) == "5-7"
    assert answer("Notice period in days", type="number") == "0"
    assert answer("Are you serving notice period?", options=["Yes", "No"]) == ""
    assert answer("Are you willing to relocate to Pune?", options=["Yes", "No"]) == "No"
    assert answer("Are you willing to relocate to Mumbai?", options=["Yes", "No"]) == ""
    assert answer("Are you authorized to work in India?", options=["Yes", "No"]) == ""
    assert (
        answer("Do you have at least 2 years of experience with Java?", options=["Yes", "No"])
        == "No"
    )
    assert answer("Tell us why this company is your dream employer") == ""


def test_local_matching_has_no_empty_requirements_bonus_or_java_javascript_collision():
    profile = ResumeProfile(
        skills=["Java", "SQL"], current_title="Java Developer", total_experience_years=1
    )
    assert local_match(
        profile,
        Job(
            naukri_job_id="1",
            company="Example",
            url="https://example.invalid/1",
            title="Java Developer",
            skills="Java, SQL",
        ),
        70,
    )[1]
    assert not local_match(
        profile,
        Job(
            naukri_job_id="1",
            company="Example",
            url="https://example.invalid/1",
            title="Sales Associate",
            skills="Sales, Communication",
        ),
        70,
    )[1]
    assert (
        local_match(
            profile,
            Job(
                naukri_job_id="1",
                company="Example",
                url="https://example.invalid/1",
                title="Developer",
                description="",
            ),
            70,
        )[0]
        == 0
    )
    assert (
        "java"
        not in local_match(
            profile,
            Job(
                naukri_job_id="1",
                company="Example",
                url="https://example.invalid/1",
                title="JavaScript Developer",
                skills="JavaScript",
            ),
            70,
        )[3]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["naukri", "linkedin"])
async def test_both_agents_match_and_answer_with_no_key_and_never_call_llm(platform, tmp_path):
    if platform == "linkedin":
        from src.linked_agent.config.settings import Settings as PlatformSettings
        from src.linked_agent.models.entities import ResumeProfile as Profile, Job as PlatformJob
        from src.linked_agent.ai.job_matcher import LinkedInJobMatcher as Matcher
        from src.linked_agent.ai.question_answerer import LinkedInQuestionAnswerer as Answerer
    else:
        from src.naukri_agent.config.settings import Settings as PlatformSettings
        from src.naukri_agent.models.entities import ResumeProfile as Profile, Job as PlatformJob
        from src.naukri_agent.ai.job_matcher import JobMatcher as Matcher
        from src.naukri_agent.ai.question_answerer import QuestionAnswerer as Answerer
    settings = PlatformSettings(
        project_root=tmp_path,
        ai={"use_gemini": False, "gemini_api_key": ""},
        profile={"skill_experience_years": {"Java": 1.5}},
    )
    llm = AsyncMock()
    llm.generate_content.side_effect = AssertionError("Offline flow attempted an LLM call")
    profile = Profile(
        name="Candidate Example",
        skills=["Java", "SQL"],
        current_title="Java Developer",
        total_experience_years=1.5,
    )
    job = PlatformJob(
        **{platform + "_job_id": "1"},
        company="Example",
        url="https://example.invalid/1",
        title="Java Developer",
        skills="Java, SQL",
        experience="0-2 years",
    )
    result = await Matcher(llm, settings).match(profile, job)
    assert result.should_apply
    assert "Resume rules" in result.match_reasoning
    answers = await Answerer(llm, settings, profile).answer_questions(
        [
            {
                "id": "skill",
                "question": "How many years of experience with Java?",
                "type": "number",
                "field_type": "number",
            },
            {
                "id": "legal",
                "question": "Do you require visa sponsorship?",
                "options": ["Yes", "No"],
                "type": "radio",
                "field_type": "radio",
            },
        ],
        job,
    )
    assert answers[0]["answer"] == "1.5"
    assert answers[1]["answer"] == ""
    llm.generate_content.assert_not_called()


@pytest.mark.parametrize("platform", ["naukri", "linkedin"])
def test_no_key_factory_uses_no_network_provider(platform):
    from libs.common.offline_provider import OfflineProvider

    if platform == "linkedin":
        from src.linked_agent.config.settings import Settings as PlatformSettings
        from src.linked_agent.bot.factory import LinkedInDependencyFactory as Factory
    else:
        from src.naukri_agent.config.settings import Settings as PlatformSettings
        from src.naukri_agent.bot.factory import DependencyFactory as Factory
    assert isinstance(
        Factory(
            PlatformSettings(ai={"use_gemini": False, "gemini_api_key": ""})
        ).get_llm_provider(),
        OfflineProvider,
    )


@pytest.mark.asyncio
async def test_offline_naukri_answerer_fills_required_field_without_provider(tmp_path):
    from unittest.mock import MagicMock, patch
    from src.naukri_agent.ai.question_answerer import QuestionAnswerer
    from src.naukri_agent.browser.apply import JobApplier

    settings = Settings(
        project_root=tmp_path,
        ai={"use_gemini": False},
        profile={"skill_experience_years": {"Java": 1.5}},
    )
    provider = AsyncMock()
    qa = QuestionAnswerer(provider, settings, ResumeProfile())
    question = {
        "id": "java",
        "question": "How many years of experience with Java?",
        "type": "number",
        "required": True,
        "value": "",
    }
    page = MagicMock()
    page.extract_screening_questions = AsyncMock(side_effect=lambda: [question])

    async def fill(q, value):
        question["value"] = value
        return True

    page.fill_answer_by_metadata = AsyncMock(side_effect=fill)
    page.is_chatbot_flow = AsyncMock(return_value=False)
    page.click_intermediate_save_button = AsyncMock(return_value=False)
    page.action_delay = AsyncMock()
    with patch("src.naukri_agent.browser.apply.asyncio.sleep", new=AsyncMock()):
        assert await JobApplier(page, settings, qa)._fill_screening_questions(
            Job("1", "Java Developer", "Example", "https://example.invalid/1")
        )
    assert question["value"] == "1.5"
    provider.generate_content.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("known", [True, False])
async def test_offline_linkedin_fills_and_submits_only_when_required_answers_are_known(
    tmp_path, known
):
    from unittest.mock import patch
    from tests.test_apply_flow_audit import detail
    from src.linked_agent.browser.apply import LinkedInJobApplier
    from src.linked_agent.config.settings import Settings as LinkedInSettings
    from src.linked_agent.models.entities import ResumeProfile as Profile, Job as LinkedInJob
    from src.linked_agent.ai.question_answerer import LinkedInQuestionAnswerer

    settings = LinkedInSettings(
        project_root=tmp_path,
        ai={"use_gemini": False},
        profile={"skill_experience_years": {"Java": 1.5}},
    )
    provider = AsyncMock()
    qa = LinkedInQuestionAnswerer(provider, settings, Profile())
    page = detail()
    question = (
        "How many years of experience with Java?" if known else "Do you require visa sponsorship?"
    )
    page.extract_screening_questions = AsyncMock(
        return_value=[
            {"question": question, "field_type": "text", "current_value": "", "is_required": True}
        ]
    )
    with patch("src.linked_agent.browser.apply.asyncio.sleep", new=AsyncMock()):
        result = await LinkedInJobApplier(page, settings, qa)._handle_easy_apply_flow(
            LinkedInJob("1", "Java Developer", "Example", "https://example.invalid/1")
        )
    assert result["status"] == ("applied" if known else "skipped_screening")
    if known:
        page.submit_application.assert_awaited_once()
    else:
        page.submit_application.assert_not_awaited()
    provider.generate_content.assert_not_called()


@pytest.mark.asyncio
async def test_reviewed_resume_is_not_overwritten_by_legacy_cache_offline(tmp_path):
    import hashlib, json
    from src.naukri_agent.ai.resume_parser import ResumeParser

    pdf = tmp_path / "resume.pdf"
    pdf.write_bytes(b"local test document")
    fingerprint = hashlib.sha256(pdf.read_bytes()).hexdigest()
    reviewed = {
        "file_hash": fingerprint,
        "name": "Reviewed Candidate",
        "current_title": "Java Developer",
        "skills": ["Java"],
        "parsing": {"method": "ai"},
    }
    source = tmp_path / "resume_profile.json"
    source.write_text(json.dumps(reviewed), encoding="utf-8")
    repository = AsyncMock()
    repository.get_cached_profile.return_value = ResumeProfile(name="Old cached profile")
    provider = AsyncMock()
    result = await ResumeParser(
        provider, repository, Settings(project_root=tmp_path, ai={"use_gemini": False})
    ).parse(pdf)
    assert result.name == "Reviewed Candidate"
    assert json.loads(source.read_text(encoding="utf-8")) == reviewed
    repository.get_cached_profile.assert_not_called()
    provider.generate_content.assert_not_called()


def test_vague_listing_tags_do_not_hide_the_description_stack():
    profile = ResumeProfile(skills=["Java", "Spring Boot", "SQL"], current_title="Java Developer", total_experience_years=1)
    job = Job("1", "Junior Java Developer", "Example", "https://example.invalid",
              skills="Coding, Core, Architecture, Application, Application development",
              description="1-3 years Java development experience. Build APIs using Java, Spring Boot and SQL.")
    score, approved, _, matching, _ = local_match(profile, job, 70)
    assert approved and score >= 70
    assert {"java", "spring boot", "sql"} <= set(matching)
    job.skills = "Java, SQL, UnlistedFrameworkA, UnlistedFrameworkB, UnlistedFrameworkC, UnlistedFrameworkD"
    assert not local_match(profile, job, 70)[1]
