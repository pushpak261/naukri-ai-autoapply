"""Regression cases from the native Naukri screening logs; no live submissions."""

from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

from playwright.async_api import Error as PlaywrightError

import pytest

from src.naukri_agent.ai.question_answerer import QuestionAnswerer
from src.naukri_agent.browser.apply import JobApplier
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.models.entities import Job, ResumeProfile
from tests.test_naukri_production_flow import native_page as native_page


def worker(detail, root):
    settings = Settings(
        project_root=root,
        ai={"use_gemini": False},
        profile={
            "expected_ctc": "8 LPA",
            "current_ctc": "4.5 LPA",
            "serving_notice": False,
        },
    )
    provider = AsyncMock()
    provider.generate_content.side_effect = AssertionError("Gemini must remain disabled")
    return JobApplier(detail, settings, QuestionAnswerer(provider, settings, ResumeProfile()))


def job():
    return Job(
        "123456789012", "Java Developer", "Example", "https://www.naukri.com/job-java-123456789012"
    )


@pytest.mark.asyncio
async def test_prefilled_answer_is_saved_once_and_followup_is_filled(native_page, tmp_path):
    detail, page = native_page
    await page.set_content(
        """<div class="chatbot_Drawer"><div class="chatbot_MessageContainer">
      <div class="botMsg">Current CTC in LPA</div><input id="answer" type="number" step="0.1" value="4.5" required>
      <button id="save">Save</button></div></div><script>window.answers=[];
      document.querySelector('#save').onclick=()=>{
        window.answers.push(document.querySelector('#answer').value);
        if(window.answers.length===1){document.querySelector('.botMsg').textContent='Expected CTC in LPA';document.querySelector('#answer').value='';}
        else{document.querySelector('.chatbot_Drawer').innerHTML='<h2>Application submitted successfully</h2>';}
      };</script>"""
    )
    with patch("src.naukri_agent.browser.apply.asyncio.sleep", new=AsyncMock()):
        result = await worker(detail, tmp_path)._handle_apply_flow(job())
    assert result["status"] == "applied", result
    assert await page.evaluate("window.answers") == ["4.5", "8"]


@pytest.mark.asyncio
async def test_autoadvancing_choice_never_saves_the_blank_followup(native_page, tmp_path):
    detail, page = native_page
    await page.set_content(
        """<div class="chatbot_Drawer"><div class="chatbot_MessageContainer">
      <div class="botMsg">Are you serving notice period?</div>
      <label><input type="radio" name="notice" value="Yes">Yes</label>
      <label><input type="radio" id="no" name="notice" value="No">No</label></div></div>
      <script>window.answers=[];window.saves=0;
      document.querySelector('#no').onchange=()=>{document.querySelector('.chatbot_MessageContainer').innerHTML=
        '<div class="botMsg">Expected CTC in LPA</div><input id="ctc" type="number" required><button id="save">Save</button>';
        document.querySelector('#save').onclick=()=>{window.saves++;window.answers.push(document.querySelector('#ctc').value);
          document.querySelector('.chatbot_Drawer').innerHTML='<h2>Application submitted successfully</h2>';};};</script>"""
    )
    with patch("src.naukri_agent.browser.apply.asyncio.sleep", new=AsyncMock()):
        result = await worker(detail, tmp_path)._handle_apply_flow(job())
    assert result["status"] == "applied", result
    assert await page.evaluate("window.answers") == ["8"]
    assert await page.evaluate("window.saves") == 1


@pytest.mark.asyncio
async def test_stalled_save_is_uncertain_and_never_clicked_again(native_page, tmp_path):
    detail, page = native_page
    await page.set_content(
        """<div class="chatbot_Drawer"><div class="chatbot_MessageContainer">
      <label for="ctc">Expected CTC in LPA</label><input id="ctc" value="8" required>
      <button onclick="window.saves++">Save</button></div></div><script>window.saves=0</script>"""
    )
    with patch("src.naukri_agent.browser.apply.asyncio.sleep", new=AsyncMock()):
        result = await worker(detail, tmp_path)._handle_apply_flow(job())
    assert result["status"] == "uncertain", result
    assert await page.evaluate("window.saves") == 1


@pytest.mark.asyncio
async def test_filling_contenteditable_does_not_save_or_submit(native_page):
    detail, page = native_page
    await page.set_content(
        """<div class="chatbot_Drawer"><div class="chatbot_MessageContainer">
      <div class="botMsg">Expected CTC in LPA</div><div contenteditable="true"></div>
      <button onclick="window.saves++">Save</button></div></div><script>window.saves=0</script>"""
    )
    questions = await detail.extract_screening_questions()
    assert await detail.fill_answer_by_metadata(questions[0], "8")
    assert await page.locator("[contenteditable]").inner_text() == "8"
    assert await page.evaluate("window.saves") == 0


@pytest.mark.asyncio
async def test_unlocatable_no_option_never_clicks_yes(native_page):
    detail, page = native_page
    await page.set_content(
        """<div class="apply-modal"><label><input id="yes" type="radio" name="q">Yes</label>
      <label><input id="no" type="radio" name="q">No</label></div>"""
    )
    question = {
        "question": "Are you serving notice?",
        "type": "radio",
        "options": [
            {"text": "Yes", "selector": "#yes", "stableSelector": "#yes"},
            {"text": "No", "selector": "#missing-no", "stableSelector": "#missing-no"},
        ],
    }
    assert not await detail.fill_answer_by_metadata(question, "No")
    assert not await page.locator("#yes").is_checked()
    assert not await page.locator("#no").is_checked()


@pytest.mark.asyncio
async def test_checkbox_fill_is_idempotent(native_page):
    detail, page = native_page
    await page.set_content(
        '<div class="apply-modal"><label><input id="choice" type="checkbox">Remote</label></div>'
    )
    questions = await detail.extract_screening_questions()
    assert await detail.fill_answer_by_metadata(questions[0], "Remote")
    assert await detail.fill_answer_by_metadata(questions[0], "Remote")
    assert await page.locator("#choice").is_checked()


@pytest.mark.asyncio
async def test_postapply_url_and_hidden_chatbot_are_not_screening_forms(native_page):
    detail, page = native_page
    await page.route(
        "https://www.naukri.com/myapply/postapply",
        lambda route: route.fulfill(
            body='<h1>More jobs for you</h1><div class="chatbot_Drawer" hidden><input><button>Save</button></div>'
        ),
    )
    await page.goto("https://www.naukri.com/myapply/postapply")
    assert not await detail.is_chatbot_flow()
    assert not await detail.detect_screening_questions()


@pytest.mark.asyncio
async def test_missing_checkbox_option_never_silently_submits_partial_answer(native_page):
    detail, page = native_page
    await page.set_content(
        '<div class="apply-modal"><label><input id="java" type="checkbox">Java</label></div>'
    )
    question = {
        "question": "Which skills?",
        "type": "checkbox",
        "options": [
            {"text": "Java", "value": "java", "selector": "#java"},
        ],
    }
    assert not await detail.fill_answer_by_metadata(question, "Java, SQL")
    assert not await page.locator("#java").is_checked()


@pytest.mark.asyncio
async def test_search_ignores_hidden_cards_and_recommendation_panels(native_page):
    from src.naukri_agent.browser.pages.search import SearchPage

    _, page = native_page
    card = '<article class="jobTuple"><a class="title" href="https://www.naukri.com/job-java-ID">TITLE</a><span class="exp-wrap">0-2 Yrs</span><span class="job-post-day">Today</span></article>'
    await page.set_content(
        "<main>"
        + card.replace("ID", "123456789001").replace("TITLE", "Java Developer")
        + "</main>"
        + "<aside>"
        + card.replace("ID", "123456789002").replace("TITLE", "Sales Manager")
        + "</aside>"
        + "<div hidden>"
        + card.replace("ID", "123456789003").replace("TITLE", "Unrendered template")
        + "</div>"
    )
    search = SearchPage(SimpleNamespace(page=page), AsyncMock())
    assert [job.naukri_job_id for job in await search.parse_job_cards()] == ["123456789001"]


@pytest.mark.asyncio
@pytest.mark.parametrize("valid", [True, False])
async def test_chatbot_final_submit_respects_native_validation(native_page, tmp_path, valid):
    detail, page = native_page
    await page.set_content(
        """<div class="chatbot_Drawer"><div class="chatbot_MessageContainer">
      <label for="ctc">Expected CTC in LPA</label><input id="ctc" type="number" min="MINIMUM" value="8" required>
      <button onclick="window.submissions++;document.querySelector('.chatbot_Drawer').innerHTML='<h2>Application submitted successfully</h2>'">Submit application</button>
      </div></div><script>window.submissions=0</script>""".replace(
            "MINIMUM", "0" if valid else "10"
        )
    )
    with patch("src.naukri_agent.browser.apply.asyncio.sleep", new=AsyncMock()):
        result = await worker(detail, tmp_path)._handle_apply_flow(job())
    assert result["status"] == ("applied" if valid else "skipped_screening"), result
    assert await page.evaluate("window.submissions") == int(valid)


@pytest.mark.asyncio
async def test_lost_connection_during_save_is_uncertain_without_retry(native_page, tmp_path):
    detail, page = native_page
    await page.set_content(
        '<div class="chatbot_Drawer"><label for="ctc">Expected CTC in LPA</label><input id="ctc" value="8"><button>Save</button></div>'
    )
    detail.click_chatbot_save_button = AsyncMock(
        side_effect=PlaywrightError("Connection lost after clicking")
    )
    with patch("src.naukri_agent.browser.apply.asyncio.sleep", new=AsyncMock()):
        result = await worker(detail, tmp_path)._handle_apply_flow(job())
    assert result["status"] == "uncertain"
    detail.click_chatbot_save_button.assert_awaited_once()


@pytest.mark.asyncio
async def test_unlocatable_checkbox_does_not_report_the_group_complete(native_page):
    detail, page = native_page
    await page.set_content(
        '<div class="apply-modal"><label><input id="java" type="checkbox">Java</label></div>'
    )
    question = {
        "question": "Which skills?",
        "type": "checkbox",
        "options": [
            {"text": "Java", "selector": "#java", "stableSelector": "#java"},
            {"text": "SQL", "selector": "#missing", "stableSelector": "#missing"},
        ],
    }
    assert not await detail.fill_answer_by_metadata(question, "Java, SQL")
    assert await page.locator("#java").is_checked()
