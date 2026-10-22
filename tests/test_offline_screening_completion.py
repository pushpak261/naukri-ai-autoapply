from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from libs.common.offline_screening import offline_answer
from libs.common.screening import evidence_answer
from libs.common.screening_review import ScreeningReviewStore
from src.naukri_agent.ai.question_answerer import QuestionAnswerer
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.models.entities import Job, ResumeProfile
from tests.test_naukri_production_flow import native_page


def job(identifier="123456789012", record_id=7):
    return Job(
        identifier,
        "Java Developer",
        "Example",
        f"https://www.naukri.com/job-java-{identifier}",
        id=record_id,
        description="Java Spring Boot SQL",
        skills="Java, SQL",
    )


def settings(root):
    return Settings(
        project_root=root,
        ai={"use_gemini": False},
        profile={
            "current_ctc": "4.5 LPA",
            "expected_ctc": "8 LPA",
            "notice_period": "30 days",
            "employment_status": "employed",
            "serving_notice": False,
            "skill_experience_years": {"Java": 1, "SQL": 1},
        },
    )


@pytest.mark.parametrize(
    "question,kind,expected",
    [
        ("Are you currently employed?", "text", "Yes"),
        ("Are you serving notice period?", "text", "No"),
        (
            "What is your last working date",
            "contenteditable",
            "Not fixed; currently employed and not serving notice. My notice period is 30 days.",
        ),
        ("What is your last working date", "date", ""),
        ("Current CTC in INR per annum", "number", "450000"),
        ("Expected salary in INR per month", "number", "66666.7"),
        ("Expected CTC in LPA per annum", "number", "8"),
        ("Java and SQL experience in years", "number", "1"),
        ("Have you worked with Java?", "text", "Yes"),
        ("Have you worked with Rust?", "text", ""),
    ],
)
def test_confirmed_facts_and_units_without_guessing_dates(tmp_path, question, kind, expected):
    q = {
        "question": question,
        "type": "date" if "working date" in question else kind,
        "input_type": kind,
    }
    assert evidence_answer(q, settings(tmp_path), ResumeProfile()) == expected


def test_resume_and_technical_answers_never_invent_personal_history(tmp_path):
    candidate = ResumeProfile(
        skills=["Java", "SQL"],
        total_experience_years=1,
        projects=[{"name": "Inventory API", "description": "A Spring Boot inventory service"}],
    )
    s = settings(tmp_path)

    def answer(text):
        return offline_answer({"question": text, "type": "text"}, s, candidate, job())

    assert "1 year of professional experience" in answer("Tell us about yourself")[0]
    assert "Inventory API" in answer("Describe your recent project")[0]
    assert "Java" in answer("Why should we hire you?")[0]
    assert answer("What is dependency injection?")[1] == "technical_knowledge"
    assert answer("Explain how you used dependency injection at your last employer")[0] == ""
    assert answer("Why is our company your dream employer?")[0] == ""


@pytest.mark.asyncio
async def test_unknown_answers_are_collected_once_then_reused_without_llm(tmp_path):
    s = settings(tmp_path)
    provider = AsyncMock()
    provider.generate_content.side_effect = AssertionError("Gemini must never be called")
    questions = [
        {"id": f"q{i}", "question": text, "type": "text", "options": ["Yes", "No"]}
        for i, text in enumerate(["Do you need visa sponsorship?", "Are you willing to travel?"])
    ]
    qa = QuestionAnswerer(provider, s, ResumeProfile())
    missing = await qa.answer_questions(questions, job())
    assert all(answer["confidence"] == "needs_input" for answer in missing)
    store = ScreeningReviewStore(tmp_path)
    assert len(store.pending()) == 2
    await qa.answer_questions(questions, job())
    assert len(store.pending()) == 2
    assert store.save_answers({row["id"]: "No" for row in store.pending()}) == [7]
    fresh = QuestionAnswerer(provider, s, ResumeProfile())
    answers = await fresh.answer_questions(questions, job())
    assert [answer["answer"] for answer in answers] == ["No", "No"]
    assert all(answer["source"] == "confirmed_answer" for answer in answers)
    assert not store.pending()
    provider.generate_content.assert_not_called()


def test_review_is_tenant_and_job_scoped_and_batch_validation_is_atomic(tmp_path):
    store = ScreeningReviewStore(tmp_path / "one")
    q = {"question": "Why are you interested in this company?", "type": "text"}
    first = job()
    second = job("999999999999", 8)
    identifier = store.remember(q, first)
    store.save_answers({identifier: "The published role matches my Java backend interests."})
    assert store.answer_for(q, first)
    assert not store.answer_for(q, second)
    assert not ScreeningReviewStore(tmp_path / "two").answer_for(q, first)
    number = store.remember({"question": "Custom numeric question", "type": "number"}, first)
    date = store.remember({"question": "Confirmed date", "type": "date"}, first)
    with pytest.raises(ValueError):
        store.save_answers({number: "2", date: "not fixed"})
    assert len(store.pending()) == 2
    assert store.save_answers({number: "2"}) == []
    assert store.save_answers({date: "2026-12-01"}) == [7]


@pytest.mark.asyncio
async def test_optional_unknown_question_blocks_save_until_confirmed(tmp_path):
    s = settings(tmp_path)
    questions = [
        {
            "id": "q1",
            "question": "Expected CTC in LPA",
            "type": "number",
            "value": "",
            "required": True,
        },
        {
            "id": "q2",
            "question": "Do you need visa sponsorship?",
            "type": "text",
            "value": "",
            "required": False,
            "options": ["Yes", "No"],
        },
    ]
    detail = SimpleNamespace(
        extract_screening_questions=AsyncMock(return_value=questions),
        click_intermediate_save_button=AsyncMock(),
        submit_application=AsyncMock(),
        fill_answer_by_metadata=AsyncMock(),
    )
    from src.naukri_agent.browser.apply import JobApplier

    worker = JobApplier(detail, s, QuestionAnswerer(AsyncMock(), s, ResumeProfile()))
    assert not await worker._fill_screening_questions(job())
    detail.fill_answer_by_metadata.assert_not_awaited()
    detail.click_intermediate_save_button.assert_not_awaited()
    detail.submit_application.assert_not_awaited()
    assert worker.unanswered_questions == ["Do you need visa sponsorship?"]


@pytest.mark.asyncio
async def test_native_form_is_completed_after_one_confirmation_without_any_llm(
    native_page, tmp_path
):
    from src.naukri_agent.browser.apply import JobApplier

    detail, page = native_page
    listing = job()
    html = """<button onclick="document.querySelector('.apply-modal').hidden=false;this.remove()">Apply</button>
      <div role="dialog" class="apply-modal" hidden><form>
      <label for="ctc">Current CTC in LPA</label><input id="ctc" type="number" step="0.1" required>
      <label for="notice">Are you currently serving notice period?</label><select id="notice" required><option value="" selected>Select</option><option>Yes</option><option>No</option></select>
      <label for="visa">Do you need visa sponsorship?</label><select id="visa"><option value="" selected>Select</option><option>Yes</option><option>No</option></select>
      <button type="submit">Submit application</button></form></div><script>window.submissions=0;
      document.querySelector('form').onsubmit=e=>{e.preventDefault();window.values=[...document.querySelectorAll('input,select')].map(el=>el.value);window.submissions++;document.querySelector('.apply-modal').innerHTML='<h2>Application submitted successfully</h2>';}</script>"""
    await page.route(listing.url, lambda route: route.fulfill(content_type="text/html", body=html))
    await page.goto(listing.url)
    provider = AsyncMock()
    provider.generate_content.side_effect = AssertionError("No Gemini calls")
    s = settings(tmp_path)
    worker = JobApplier(detail, s, QuestionAnswerer(provider, s, ResumeProfile()))
    with patch("src.naukri_agent.browser.apply.asyncio.sleep", new=AsyncMock()):
        result = await worker.apply_to_job(listing)
        assert result["status"] == "skipped_screening"
        assert await page.evaluate("window.submissions") == 0
        store = ScreeningReviewStore(tmp_path)
        pending = store.pending()
        assert len(pending) == 1 and pending[0]["question"] == "Do you need visa sponsorship?"
        store.save_answers({pending[0]["id"]: "No"})
        await page.goto(listing.url)
        result = await worker.apply_to_job(listing)
    assert result["status"] == "applied"
    assert await page.evaluate("window.values") == ["4.5", "No", "No"]
    assert await page.evaluate("window.submissions") == 1
    provider.generate_content.assert_not_called()


@pytest.mark.asyncio
async def test_not_serving_notice_completes_last_working_date_chatbot(native_page, tmp_path):
    from src.naukri_agent.browser.apply import JobApplier

    detail, page = native_page
    await page.set_content(
        """<div class="chatbot_Drawer chatbot_right"><div class="chatbot_MessageContainer">
      <ul><li class="botItem"><div class="botMsg msg"><span>What is your last working date</span></div></li></ul>
      <div class="footerWrapper"><div class="chatbot_SendMessageContainer"><div class="chatbot_InputContainer">
      <div class="textArea" id="userInput__fixtureInputBox" contenteditable="true" oninput="document.querySelector('.send').classList.remove('disabled')"></div></div></div></div></div>
      <div class="send disabled"><div tabindex="0" onclick="window.answer=document.querySelector('[contenteditable]').innerText;document.querySelector('.chatbot_Drawer').innerHTML='<h2>Application submitted successfully</h2>'">Save</div></div></div>"""
    )
    questions = await detail.extract_screening_questions()
    assert questions[0]["input_type"] == "contenteditable"
    assert await detail.is_chatbot_flow()
    s = settings(tmp_path)
    provider = AsyncMock()
    provider.generate_content.side_effect = AssertionError("No LLM calls")
    worker = JobApplier(detail, s, QuestionAnswerer(provider, s, ResumeProfile()))
    with patch("src.naukri_agent.browser.apply.asyncio.sleep", new=AsyncMock()):
        result = await worker._handle_apply_flow(job())
    assert result["status"] == "applied"
    answer = await page.evaluate("window.answer")
    assert "Not fixed" in answer and "not serving notice" in answer and "30 days" in answer
    provider.generate_content.assert_not_called()
