"""Real form boundaries and durable discovery for the Naukri workflow."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from playwright.async_api import Error, async_playwright

from src.naukri_agent.ai.question_answerer import QuestionAnswerer
from src.naukri_agent.browser.apply import JobApplier
from src.naukri_agent.browser.pages.detail import JobDetailPage
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.models.entities import Job, ResumeProfile
from src.naukri_agent.utils.filters import JobFilter


@pytest_asyncio.fixture
async def native_page():
    async with async_playwright() as runtime:
        try:
            browser = await runtime.chromium.launch()
        except Error as error:
            if "Executable doesn't exist" in str(error):
                pytest.skip("Chromium required for Naukri form regressions")
            raise
        try:
            page = await browser.new_page()
            engine = SimpleNamespace(page=page)
            interactions = AsyncMock()
            interactions.element_exists.return_value = False
            yield JobDetailPage(engine, interactions), page
        finally:
            await browser.close()


@pytest.mark.parametrize(
    "experience,allowed",
    [
        ("6 months", True),
        ("18 months", True),
        ("2.5 years", False),
        ("3-5 Yrs", False),
        ("0-4 Yrs", True),
        ("Jan 2023 - Dec 2024", True),
    ],
)
def test_experience_filter_uses_stated_units(experience, allowed):
    assert JobFilter(2, 7)._passes_experience_filter(experience) is allowed


@pytest.mark.asyncio
async def test_descriptions_and_hidden_messages_cannot_confirm_submission(native_page):
    detail, page = native_page
    await page.set_content(
        """<div class="job-description">We have received your application. Already applied.</div><button>Apply</button><div role="alert" hidden>Application submitted</div>"""
    )
    assert not await detail.is_already_applied()
    assert not await detail.check_application_success()
    await page.set_content('<div role="status">Application submitted successfully</div>')
    assert await detail.check_application_success()
    await page.set_content(
        '<div class="styles_jhc__apply-button-container__5Bqnb"><span id="already-applied" class="already-applied">Applied</span></div>'
    )
    assert await detail.is_already_applied()
    assert await detail.check_application_success()


@pytest.mark.asyncio
async def test_uncertain_post_apply_is_confirmed_by_reading_listing_without_reclick(
    native_page, tmp_path
):
    detail, page = native_page
    url = "https://www.naukri.com/job-java-123456789012"
    applied = False

    async def job_page(route):
        await route.fulfill(
            content_type="text/html",
            body=(
                '<span id="already-applied">Applied</span>' if applied else "<button>Apply</button>"
            ),
        )

    async def click_once():
        nonlocal applied
        applied = True
        return True

    await page.route(url, job_page)
    await page.goto(url)
    detail.click_apply_button = AsyncMock(side_effect=click_once)
    worker = JobApplier(detail, Settings(project_root=tmp_path), MagicMock())
    worker._handle_apply_flow = AsyncMock(return_value={"status": "uncertain"})
    with patch("src.naukri_agent.browser.apply.asyncio.sleep", new=AsyncMock()):
        result = await worker.apply_to_job(Job("123456789012", "Java", "Example", url))
    assert await detail.is_already_applied(), await page.content()
    assert result["status"] == "applied"
    detail.click_apply_button.assert_awaited_once()


@pytest.mark.asyncio
async def test_disabled_dropdown_placeholder_remains_unanswered(native_page):
    detail, page = native_page
    await page.set_content(
        """<div class="apply-modal"><label for="visa">Do you require visa sponsorship?</label><select id="visa" required><option value="0" disabled selected>Select an option</option><option>No</option><option>Yes</option></select></div>"""
    )
    questions = await detail.extract_screening_questions()
    assert len(questions) == 1
    assert questions[0]["value"] == ""
    assert questions[0]["required"]


@pytest.mark.asyncio
@pytest.mark.parametrize("known", [True, False])
async def test_native_apply_fills_known_facts_and_submits_only_complete_form(
    native_page, tmp_path, known
):
    detail, page = native_page
    url = "https://www.naukri.com/job-listings-java-example-123456789012"
    question = "Expected CTC in LPA" if known else "Do you require visa sponsorship?"
    html = """<button onclick="document.querySelector('.apply-modal').hidden=false;this.remove()">Apply</button>
    <div class="apply-modal" role="dialog" hidden><form><label for="answer">QUESTION</label><input id="answer" type="TYPE" required><button type="submit">Submit</button></form></div>
    <script>window.submissions=0;document.querySelector('form').onsubmit=e=>{e.preventDefault();window.submissions++;document.querySelector('.apply-modal').innerHTML='<h2>Application submitted</h2>'}</script>""".replace(
        "QUESTION", question
    ).replace(
        "TYPE", "number" if known else "text"
    )
    await page.route(url, lambda route: route.fulfill(body=html))
    await page.goto(url)
    settings = Settings(
        project_root=tmp_path, ai={"use_gemini": False}, profile={"expected_ctc": "8 LPA"}
    )
    provider = AsyncMock()
    provider.generate_content.side_effect = AssertionError("No Gemini calls")
    qa = QuestionAnswerer(provider, settings, ResumeProfile())
    detail.click_intermediate_save_button = AsyncMock(return_value=False)
    with patch("src.naukri_agent.browser.apply.asyncio.sleep", new=AsyncMock()):
        result = await JobApplier(detail, settings, qa).apply_to_job(
            Job("123456789012", "Java Developer", "Example", url)
        )
    assert result["status"] == ("applied" if known else "skipped_screening"), result
    assert await page.evaluate("window.submissions") == int(known)
    provider.generate_content.assert_not_called()


@pytest.mark.asyncio
async def test_wrong_job_redirect_never_clicks_apply(native_page, tmp_path):
    detail, page = native_page
    await page.goto("about:blank")
    detail.click_apply_button = AsyncMock()
    result = await JobApplier(detail, Settings(project_root=tmp_path), MagicMock()).apply_to_job(
        Job(
            "123456789012",
            "Java",
            "Example",
            "https://www.naukri.com/job-listings-java-123456789012",
        )
    )
    assert result["status"] == "error"
    detail.click_apply_button.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("label,accepted", [("Upload resume", True), ("Cover letter", False)])
async def test_selected_resume_is_uploaded_only_to_a_resume_field(
    native_page, tmp_path, label, accepted
):
    detail, page = native_page
    await page.set_content(
        f'<div class="apply-modal"><label for="file">{label}</label><input id="file" type="file" required></div>'
    )
    resume = tmp_path / "data/resumes/selected.pdf"
    resume.parent.mkdir(parents=True)
    resume.write_bytes(b"%PDF-test-fixture")
    settings = Settings(
        project_root=tmp_path, resume={"path": str(resume)}, ai={"use_gemini": False}
    )
    detail.is_chatbot_flow = AsyncMock(return_value=False)
    worker = JobApplier(detail, settings, QuestionAnswerer(AsyncMock(), settings, ResumeProfile()))
    with patch("src.naukri_agent.browser.apply.asyncio.sleep", new=AsyncMock()):
        assert (
            await worker._fill_screening_questions(
                Job("1", "Java", "Example", "https://example.invalid")
            )
            is accepted
        )
    assert await page.locator("#file").evaluate("el => el.files.length") == int(accepted)


@pytest.mark.asyncio
async def test_search_persists_first_page_even_if_later_page_fails(tmp_path):
    from src.naukri_agent.browser.search import JobSearcher
    from src.naukri_agent.models.db_schema import setup_database_manager
    from src.naukri_agent.database.repository import SQLAlchemyRepository
    from sqlalchemy import select, func
    from src.naukri_agent.models.db_schema import Job as DBJob

    manager = await setup_database_manager(tmp_path / "jobs.db")
    try:
        repo = SQLAlchemyRepository(manager)
        search = AsyncMock()
        search.has_no_results.return_value = False
        search.parse_job_cards.side_effect = [
            [
                Job(
                    "123456789012",
                    "Java",
                    "Example",
                    "https://www.naukri.com/job-123456789012",
                    experience="6 months",
                    posted_date="Today",
                )
            ],
            Error("page two failed"),
        ]
        engine = MagicMock()
        engine.page.url = "https://www.naukri.com/java-jobs?k=Java"
        worker = JobSearcher(
            search, AsyncMock(), engine, Settings(project_root=tmp_path), repository=repo
        )
        with patch("src.naukri_agent.browser.search.random_delay", new=AsyncMock()):
            jobs = await worker._search_keyword_location("Java", "Pune", 2)
        assert len(jobs) == worker.total_found == 1
        async with manager.session_factory() as session:
            assert (await session.execute(select(func.count(DBJob.id)))).scalar_one() == 1
    finally:
        await manager.engine.dispose()


@pytest.mark.asyncio
async def test_validation_response_does_not_repeat_submit(tmp_path):
    detail = MagicMock()
    detail.check_application_failure = AsyncMock(
        side_effect=[None, "Please answer all mandatory questions"]
    )
    detail.check_application_success = AsyncMock(return_value=False)
    detail.detect_screening_questions = AsyncMock(return_value=True)
    detail.click_intermediate_save_button = AsyncMock(return_value=False)
    detail._trigger_form_validation = AsyncMock()
    detail.submit_application = AsyncMock(return_value=True)
    applier = JobApplier(detail, Settings(project_root=tmp_path), MagicMock())
    applier._fill_screening_questions = AsyncMock(return_value=True)
    with patch("src.naukri_agent.browser.apply.asyncio.sleep", new=AsyncMock()):
        result = await applier._handle_apply_flow(
            Job("id", "Java", "Example", "https://example.invalid")
        )
    assert result["status"] == "skipped_screening"
    detail.submit_application.assert_awaited_once()
