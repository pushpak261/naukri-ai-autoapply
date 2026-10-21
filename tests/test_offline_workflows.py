"""No-key regression coverage for complete discovery and factual decisions."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from libs.common.local_matching import local_match
from libs.common.resume_facts import duration_years, extract_resume_facts
from libs.common.screening import evidence_answer
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.models.entities import Job, ResumeProfile


@pytest.mark.parametrize(
    "value,expected",
    [("18 months", 1.5), ("1 year and 6 months", 1.5), ("2.5", 2.5), ("unknown", None)],
)
def test_stated_experience_units(value, expected):
    assert duration_years(value) == expected


def test_local_resume_extracts_only_supported_skills_and_tenure():
    facts = extract_resume_facts(
        "Test Candidate\nJavaScript Developer\ncandidate@example.invalid\n9876543210\n"
        "18 months of professional experience\nSkills: JavaScript, PostgreSQL, SpringBoot\n"
        "B.Tech in Computer Science, Example University, 2023"
    )
    assert facts["current_title"] == "JavaScript Developer"
    assert facts["phone"] == "9876543210"
    assert facts["total_experience_years"] == 1.5
    assert {"javascript", "postgresql", "spring boot"} <= set(facts["skills"])
    assert "java" not in facts["skills"]
    assert "sql" not in facts["skills"]  # PostgreSQL alone does not prove general SQL tenure.
    assert facts["education"][0]["year"] == "2023"
    assert extract_resume_facts("Candidate\nSkills: Java")["total_experience_years"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["naukri", "linkedin"])
async def test_both_parsers_handle_docx_without_api_or_saved_profile(tmp_path, platform):
    import zipfile

    if platform == "linkedin":
        from src.linked_agent.ai.resume_parser import LinkedInResumeParser as Parser
        from src.linked_agent.config.settings import Settings as PlatformSettings
    else:
        from src.naukri_agent.ai.resume_parser import ResumeParser as Parser

        PlatformSettings = Settings
    source = tmp_path / "candidate.docx"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Candidate Example</w:t></w:r></w:p><w:p><w:r><w:t>Java Backend Developer</w:t></w:r></w:p><w:p><w:r><w:t>Skills: Java, Spring Boot, SQL</w:t></w:r></w:p></w:body></w:document>',
        )
    settings = PlatformSettings(
        project_root=tmp_path, ai={"use_gemini": False, "gemini_api_key": ""}
    )
    provider = AsyncMock()
    provider.generate_content.side_effect = AssertionError("No network allowed")
    repo = AsyncMock()
    repo.get_cached_profile.return_value = None
    result = await Parser(provider, repo, settings).parse(str(source))
    assert result.name == "Candidate Example"
    assert result.current_title == "Java Backend Developer"
    assert {"java", "spring boot", "sql"} <= set(result.skills)
    assert "Java Backend Developer" in result.raw_text
    assert result.total_experience_years == 0
    provider.generate_content.assert_not_called()


def test_local_matching_understands_compound_skill_tags_and_minimum_experience():
    profile = ResumeProfile(
        current_title="Java Developer",
        skills=["Java", "SQL", "Spring Boot"],
        total_experience_years=1.5,
    )
    job = Job(
        "1",
        "Java Backend Developer",
        "Example",
        "https://example.invalid/1",
        skills="Java / SpringBoot / SQL",
        experience="6-24 months",
    )
    assert local_match(profile, job, 70)[1]
    job.experience = "2.5-5 years"
    result = local_match(profile, job, 70)
    assert not result[1]
    assert "Required experience is 2.5" in result[2]


def test_saved_profile_without_title_still_matches_its_evidenced_java_stack():
    profile = ResumeProfile(
        skills=["Java", "Spring Boot", "Microservices"], total_experience_years=1
    )
    job = Job(
        "1",
        "Java Developer",
        "Example",
        "https://example.invalid",
        skills="Java Developer, Java, Spring Boot, Spring, Microservices",
        experience="0-2 years",
    )
    assert local_match(profile, job, 70)[1]


def test_screening_preserves_question_units_and_distinguishes_skill_tenure():
    settings = Settings(
        profile={
            "total_experience": "18 months",
            "skill_experience_years": {"Java": 1.0},
            "confirmed_answers": {"How many months of SQL experience?": "6"},
        }
    )
    candidate = ResumeProfile(
        education=[{"degree": "B.Tech", "institution": "Example University", "year": "2023"}]
    )

    def answer(text):
        return evidence_answer({"question": text, "field_type": "number"}, settings, candidate)

    assert answer("How many years of overall experience?") == "1.5"
    assert answer("How many months of overall experience?") == "18"
    assert answer("Java experience in years") == "1"
    assert answer("Python experience in years") == ""
    assert answer("Java and SQL experience in years") == ""
    assert answer("How many months of SQL experience?") == "6"
    assert answer("Graduation year") == "2023"
    assert (
        evidence_answer({"question": "College name"}, settings, candidate) == "Example University"
    )


@pytest.mark.asyncio
async def test_naukri_searches_every_combination_even_after_fifty_candidates(tmp_path, monkeypatch):
    from src.naukri_agent.browser.search import JobSearcher

    settings = Settings(
        project_root=tmp_path,
        search={"keywords": ["Java", "Backend"], "locations": ["Pune", "Mumbai"]},
        application={"daily_cap": 1},
    )
    searcher = JobSearcher(MagicMock(), MagicMock(), MagicMock(), settings)
    searcher._engine.is_alive.return_value = True
    searched = []

    async def collect(**kwargs):
        searched.append((kwargs["keyword"], kwargs["location"]))
        return [
            Job(f"{len(searched)}-{i}", "Java Developer", "Example", "https://example.invalid")
            for i in range(55)
        ]

    searcher._search_keyword_location = AsyncMock(side_effect=collect)
    monkeypatch.setattr("src.naukri_agent.browser.search.random_delay", AsyncMock())
    result = await searcher.search_all()
    assert searched == [
        ("Java", "Pune"),
        ("Java", "Mumbai"),
        ("Backend", "Pune"),
        ("Backend", "Mumbai"),
    ]
    assert len(result) == 220


@pytest.mark.asyncio
async def test_naukri_query_failure_does_not_lose_remaining_searches(tmp_path, monkeypatch):
    from src.naukri_agent.browser.search import JobSearcher

    settings = Settings(
        project_root=tmp_path, search={"keywords": ["Java"], "locations": ["Pune", "Mumbai"]}
    )
    searcher = JobSearcher(MagicMock(), MagicMock(), MagicMock(), settings)
    searcher._engine.is_alive.return_value = True
    job = Job("later", "Java Developer", "Example", "https://example.invalid")
    searcher._search_keyword_location = AsyncMock(side_effect=[ValueError("query failed"), [job]])
    monkeypatch.setattr("src.naukri_agent.browser.search.random_delay", AsyncMock())
    assert await searcher.search_all() == [job]


@pytest.mark.asyncio
async def test_offline_screening_keeps_order_and_does_not_reuse_ai_cache(tmp_path):
    from src.naukri_agent.ai.question_answerer import QuestionAnswerer

    settings = Settings(project_root=tmp_path, ai={"use_gemini": False})
    answerer = QuestionAnswerer(AsyncMock(), settings, ResumeProfile(name="Candidate Example"))
    answerer._activate_job_context = lambda job: None
    answerer._cache.get = lambda *args, **kwargs: "Yes"
    questions = [{"question": "Do you require visa sponsorship?"}, {"question": "First name"}]
    result = await answerer.answer_questions(
        questions, Job("1", "Developer", "Example", "https://example.invalid")
    )
    assert [a["question"] for a in result] == [q["question"] for q in questions]
    assert [a["answer"] for a in result] == ["", "Candidate"]


def test_linkedin_inherits_compatible_search_targets_and_keeps_platform_filters(tmp_path):
    import yaml
    from libs.common.workspace_config import load_linkedin_workspace_config

    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "search": {
                    "keywords": ["Java"],
                    "locations": ["Pune", "Remote"],
                    "freshness": 7,
                    "experience_max": 2,
                }
            }
        )
    )
    shared = load_linkedin_workspace_config(tmp_path)
    assert shared["search"] == {"keywords": ["Java"], "locations": ["Pune", "Remote"]}
    (tmp_path / "linkedin_config.yaml").write_text(
        yaml.safe_dump({"search": {"locations": ["Mumbai"], "freshness": "past_24h"}})
    )
    specific = load_linkedin_workspace_config(tmp_path)
    assert specific["search"]["keywords"] == ["Java"]
    assert specific["search"]["locations"] == ["Mumbai"]
    assert specific["search"]["freshness"] == "past_24h"


def test_local_matching_enforces_experience_stated_in_description():
    from libs.common.local_matching import local_match

    profile = ResumeProfile(skills=["Java", "Spring Boot"], total_experience_years=1)
    job = Job(
        "1",
        "Java Developer",
        "Employer",
        "https://example.invalid",
        skills="Java, Spring Boot",
        description="Your expertise: 5+ years of experience in backend development.",
    )
    result = local_match(profile, job, 70)
    assert not result[1]
    assert "Required experience is 5 years" in result[2]
    job.description = "The company was founded 30 years ago."
    assert local_match(profile, job, 70)[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["naukri", "linkedin"])
async def test_real_browser_fills_and_submits_local_screening_form_without_llm(tmp_path, platform):
    from playwright.async_api import async_playwright, Error

    if platform == "linkedin":
        from src.linked_agent.browser.pages.detail import LinkedInJobDetailPage as Detail
        from src.linked_agent.ai.question_answerer import LinkedInQuestionAnswerer as Answerer
        from src.linked_agent.config.settings import Settings as PlatformSettings
        from src.linked_agent.models.entities import ResumeProfile as Profile, Job as PlatformJob
    else:
        from src.naukri_agent.browser.pages.detail import JobDetailPage as Detail
        from src.naukri_agent.ai.question_answerer import QuestionAnswerer as Answerer

        PlatformSettings, Profile, PlatformJob = Settings, ResumeProfile, Job
    settings = PlatformSettings(
        project_root=tmp_path,
        ai={"use_gemini": False, "gemini_api_key": ""},
        profile={
            "skill_experience_years": {"Java": 1.5},
            "confirmed_answers": {"Do you require sponsorship?": "No"},
        },
    )
    provider = AsyncMock()
    provider.generate_content.side_effect = AssertionError("No Gemini requests allowed")
    job = PlatformJob(
        **{platform + "_job_id": "local-fixture"},
        title="Java Developer",
        company="Local test",
        url="https://example.invalid/job",
    )
    async with async_playwright() as runtime:
        try:
            browser = await runtime.chromium.launch(headless=True)
        except Error as error:
            if "Executable doesn't exist" in str(error):
                pytest.skip("Chromium is required for the local DOM regression")
            raise
        try:
            page = await browser.new_page()
            await page.set_content(
                """<div role="dialog" class="jobs-easy-apply-modal"><form id="application">
              <div class="fb-dash-form-element"><label for="java-years">How many years of experience with Java?</label><input type="number" id="java-years" required step="0.1"></div>
              <div class="fb-dash-form-element"><label for="sponsor">Do you require sponsorship?</label><select id="sponsor" required><option value="" disabled selected>Select an option</option><option>No</option><option>Yes</option></select></div>
              <button type="submit" aria-label="Submit application">Submit application</button>
            </form></div><script>window.submissions=0;document.querySelector('form').onsubmit=e=>{e.preventDefault();window.submissions++;document.querySelector('[role=dialog]').innerHTML='<div>Application sent</div>';};</script>"""
            )
            engine = MagicMock()
            engine.page = page
            detail = Detail(engine, AsyncMock())
            questions = await detail.extract_screening_questions()
            assert len(questions) == 2, questions
            answers = await Answerer(provider, settings, Profile()).answer_questions(questions, job)
            assert [a["answer"] for a in answers] == ["1.5", "No"], questions
            for question, answer in zip(questions, answers, strict=True):
                fill = (
                    detail.fill_answer if platform == "linkedin" else detail.fill_answer_by_metadata
                )
                assert await fill(question, answer["answer"])
            assert await page.input_value("#java-years") == "1.5"
            assert await page.input_value("#sponsor") == "No"
            assert await detail.submit_application()
            assert await page.evaluate("window.submissions") == 1
            provider.generate_content.assert_not_called()
        finally:
            await browser.close()
