"""Real browser lifecycle and delayed Easy Apply failures from the live run."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.linked_agent.browser.apply import LinkedInJobApplier
from src.linked_agent.browser.engine import LinkedInPlaywrightEngine
from src.linked_agent.config.settings import Settings
from src.linked_agent.models.entities import Job
from tests.test_linkedin_modern_search import search_page as search_page
from tests.test_linkedin_screening_flow import detail


@pytest.mark.asyncio
async def test_employer_context_does_not_disconnect_linkedin_browser(tmp_path):
    engine = LinkedInPlaywrightEngine(Settings(project_root=tmp_path), headless_override=True)
    try:
        source = await engine.launch()
        await source.set_content("<h1>LinkedIn source listing</h1>")
        employer = await source.context.browser.new_context()
        page = await employer.new_page()
        await page.set_content("<h1>Employer application</h1>")
        await employer.close()
        assert engine.is_alive()
        assert await source.locator("h1").inner_text() == "LinkedIn source listing"
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_delayed_application_body_loads_before_form_actions(
    search_page, tmp_path, monkeypatch
):
    _, tab = search_page
    await tab.set_content(
        """<dialog open><h2>Apply to Example</h2><div role="progressbar"></div></dialog>
      <script>window.submissions=0;setTimeout(()=>{
        document.querySelector('dialog').innerHTML=`<div role="progressbar" aria-valuenow="90" aria-label="Application progress"></div><label>Current city<input value="Pune" required></label>
        <button onclick="window.submissions++;document.querySelector('dialog').innerHTML='Application sent'">Submit application</button>`;
      },800);</script>"""
    )
    monkeypatch.setattr("src.linked_agent.browser.apply.asyncio.sleep", AsyncMock())
    worker = LinkedInJobApplier(detail(tab), Settings(project_root=tmp_path), SimpleNamespace())
    result = await worker._handle_easy_apply_flow(
        Job("1", "Java Developer", "Example", "https://www.linkedin.com/jobs/view/1")
    )
    assert result["status"] == "applied", result
    assert await tab.evaluate("window.submissions") == 1


@pytest.mark.asyncio
async def test_unloaded_form_before_submit_is_retryable_not_uncertain(
    search_page, tmp_path, monkeypatch
):
    _, tab = search_page
    await tab.set_content(
        '<dialog open><h2>Apply to Example</h2><div role="progressbar"></div></dialog>'
    )
    page = detail(tab)
    page.wait_for_apply_step = AsyncMock(return_value=False)
    page.submit_application = AsyncMock(return_value=True)
    monkeypatch.setattr("src.linked_agent.browser.apply.asyncio.sleep", AsyncMock())
    worker = LinkedInJobApplier(page, Settings(project_root=tmp_path), SimpleNamespace())
    result = await worker._handle_easy_apply_flow(
        Job("1", "Java Developer", "Example", "https://www.linkedin.com/jobs/view/1")
    )
    assert result["status"] == "failed", result
    assert "No submission was attempted" in result["error_message"]
    page.submit_application.assert_not_awaited()


@pytest.mark.asyncio
async def test_network_change_retries_same_listing_without_consuming_another_job(monkeypatch):
    from playwright.async_api import Error
    from src.linked_agent.browser.navigation import navigate

    pause = AsyncMock()
    monkeypatch.setattr("src.linked_agent.browser.navigation.asyncio.sleep", pause)
    page = SimpleNamespace(
        goto=AsyncMock(side_effect=[Error("net::ERR_NETWORK_CHANGED"), "loaded"])
    )
    url = "https://www.linkedin.com/jobs/view/1"
    assert await navigate(page, url) == "loaded"
    assert [c.args for c in page.goto.await_args_list] == [(url,), (url,)]
    pause.assert_awaited_once_with(5)


@pytest.mark.asyncio
async def test_persistent_offline_state_stops_with_network_error_not_job_rejection(monkeypatch):
    from playwright.async_api import Error
    from src.linked_agent.browser.navigation import NetworkUnavailableError, navigate

    monkeypatch.setattr("src.linked_agent.browser.navigation.asyncio.sleep", AsyncMock())
    page = SimpleNamespace(goto=AsyncMock(side_effect=Error("net::ERR_NAME_NOT_RESOLVED")))
    with pytest.raises(NetworkUnavailableError, match="remaining jobs have not been rejected"):
        await navigate(page, "https://www.linkedin.com/jobs/view/1")
    assert page.goto.await_count == 4


@pytest.mark.asyncio
async def test_non_network_navigation_errors_are_not_retried(monkeypatch):
    from playwright.async_api import Error
    from src.linked_agent.browser.navigation import navigate

    pause = AsyncMock()
    monkeypatch.setattr("src.linked_agent.browser.navigation.asyncio.sleep", pause)
    page = SimpleNamespace(goto=AsyncMock(side_effect=Error("Target page has been closed")))
    with pytest.raises(Error, match="Target page has been closed"):
        await navigate(page, "https://www.linkedin.com/jobs/view/1")
    page.goto.assert_awaited_once()
    pause.assert_not_awaited()


@pytest.mark.asyncio
async def test_sidebar_does_not_swallow_a_persistent_network_outage(monkeypatch):
    from src.linked_agent.bot.agent import LinkedInAgent
    from src.linked_agent.browser.navigation import NetworkUnavailableError

    navigate = AsyncMock(side_effect=NetworkUnavailableError("offline"))
    monkeypatch.setattr("src.linked_agent.bot.agent.navigate", navigate)
    agent = object.__new__(LinkedInAgent)
    agent._engine = SimpleNamespace(page=SimpleNamespace())
    with pytest.raises(NetworkUnavailableError, match="offline"):
        await agent._navigate_to_job_sidebar(
            Job("1", "Java Developer", "Example", "https://www.linkedin.com/jobs/view/1")
        )
    navigate.assert_awaited_once()


@pytest.mark.asyncio
async def test_disabled_email_notifications_keep_local_report_without_sending(
    tmp_path, monkeypatch
):
    from unittest.mock import MagicMock
    from src.linked_agent.bot.agent import LinkedInAgent

    send = AsyncMock()
    monkeypatch.setattr("src.linked_agent.bot.agent.send_external_jobs_email", send)
    monkeypatch.setattr("src.linked_agent.bot.agent.MetricsTracker", MagicMock())
    agent = object.__new__(LinkedInAgent)
    agent._settings = Settings(
        project_root=tmp_path, application={"email_notifications_enabled": False}
    )
    agent._external_jobs = [object()]
    agent._save_local_report = MagicMock()
    agent._print_summary = MagicMock()
    agent._repo = agent._engine = None
    agent._jobs_applied = agent._jobs_failed = 0
    await agent._cleanup()
    agent._save_local_report.assert_called_once()
    send.assert_not_called()


@pytest.mark.asyncio
async def test_discovery_does_not_report_persistent_outage_as_empty_results(tmp_path):
    from src.linked_agent.browser.navigation import NetworkUnavailableError
    from src.linked_agent.browser.search import LinkedInJobSearcher

    search = SimpleNamespace(
        navigate_to_search=AsyncMock(side_effect=NetworkUnavailableError("offline"))
    )
    worker = LinkedInJobSearcher(search, None, None, Settings(project_root=tmp_path))
    with pytest.raises(NetworkUnavailableError, match="offline"):
        await worker._search_keyword("Java", "Pune")


@pytest.mark.asyncio
async def test_inert_search_dialog_cannot_hide_or_replace_application(
    search_page, tmp_path, monkeypatch
):
    _, tab = search_page
    await tab.set_content(
        """<dialog open><label>Email<input type="email" required value="candidate@example.invalid"></label>
      <button onclick="document.body.dataset.sent='1';this.closest('dialog').innerHTML='Application sent'">Submit application</button></dialog>
      <div role="dialog" data-testid="popover-floating" inert style="position:fixed;opacity:0;inset:10px">
        <label>Search<input></label><button onclick="document.body.dataset.wrong='1'">Submit</button></div>"""
    )
    monkeypatch.setattr("src.linked_agent.browser.apply.asyncio.sleep", AsyncMock())
    page = detail(tab)
    questions = await page.extract_screening_questions()
    assert [q["question"] for q in questions] == ["Email"]
    assert (await page.get_modal_text()).startswith("Email")
    worker = LinkedInJobApplier(page, Settings(project_root=tmp_path), SimpleNamespace())
    result = await worker._handle_easy_apply_flow(
        Job("1", "Java Developer", "Example", "https://www.linkedin.com/jobs/view/1")
    )
    assert result["status"] == "applied", result
    assert await tab.locator("body").get_attribute("data-sent") == "1"
    assert await tab.locator("body").get_attribute("data-wrong") is None


@pytest.mark.asyncio
async def test_native_dialog_upload_targets_the_resume_not_cover_letter(
    search_page, tmp_path, monkeypatch
):
    _, tab = search_page
    await tab.set_content(
        '<dialog open><label>Cover letter<input id="cover" type="file"></label><label>Resume<input id="resume" type="file"></label></dialog>'
    )
    selected = tmp_path / "resume.pdf"
    selected.write_bytes(b"%PDF-1.4 test fixture")
    monkeypatch.setattr("src.linked_agent.browser.pages.detail.asyncio.sleep", AsyncMock())
    assert await detail(tab).upload_resume_file(str(selected), field_id="resume")
    assert await tab.locator("#cover").evaluate("el => el.files.length") == 0
    assert await tab.locator("#resume").evaluate("el => el.files[0].name") == "resume.pdf"


@pytest.mark.parametrize("mirrored", [True, False])
def test_screening_retry_uses_shared_job_id_instead_of_private_linkedin_id(tmp_path, mirrored):
    import sqlite3
    from libs.common.screening_review import ScreeningReviewStore

    data = tmp_path / "data"
    data.mkdir()
    with sqlite3.connect(data / "naukri_agent.db") as connection:
        connection.execute(
            "CREATE TABLE jobs(id INTEGER PRIMARY KEY,naukri_job_id TEXT,source TEXT)"
        )
        connection.execute("INSERT INTO jobs VALUES(17,'unrelated-naukri-job','naukri')")
        if mirrored:
            connection.execute("INSERT INTO jobs VALUES(601,'li_123','linkedin')")
    store = ScreeningReviewStore(tmp_path)
    job = Job("123", "Java Developer", "Example", "https://www.linkedin.com/jobs/view/123", id=17)
    identifier = store.remember({"question": "Confirmed candidate fact", "type": "text"}, job)
    assert store.save_answers({identifier: "Confirmed answer"}) == ([601] if mirrored else [])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question,answer,expected",
    [
        ("Current CTC per annum", "4.5 LPA", "450000"),
        ("Expected CTC per annum", "8 LPA", "800000"),
        ("What is your Notice period duration", "30 days", "30"),
        ("Date of birth as per legal document", "03/07/2000", "03072000"),
    ],
)
async def test_numeric_only_text_fields_keep_the_confirmed_fact_and_units(
    search_page, question, answer, expected
):
    _, tab = search_page
    await tab.set_content(
        """<dialog open><label id="label" for="quantity"></label>
      <input id="quantity" required aria-describedby="quantity-info" oninput="document.querySelector('#quantity-info').textContent=/^[0-9]+(?:\\.[0-9]+)?$/.test(this.value)?'':'Invalid input'">
      <div id="quantity-info"></div><button>Review</button></dialog>"""
    )
    await tab.locator("#label").evaluate("(el, text) => el.textContent=text", question)
    page = detail(tab)
    (field,) = await page.extract_screening_questions()
    assert await page.fill_answer(field, answer)
    assert await tab.locator("#quantity").input_value() == expected
    assert await page.click_review()


@pytest.mark.asyncio
async def test_custom_error_cannot_advance_or_rewrite_an_unknown_fact(search_page):
    _, tab = search_page
    await tab.set_content(
        """<dialog open><label for="answer">Required employer fact</label>
      <input id="answer" required value="Unsupported" aria-describedby="answer-info">
      <div id="answer-info">Invalid input</div><button onclick="document.body.dataset.clicked='1'">Review</button></dialog>"""
    )
    page = detail(tab)
    (field,) = await page.extract_screening_questions()
    assert field["validation_error"]
    assert not await page.fill_answer(field, "Unsupported")
    assert not await page.click_review()
    assert await tab.locator("body").get_attribute("data-clicked") is None
