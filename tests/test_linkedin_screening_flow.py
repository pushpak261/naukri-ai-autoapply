"""Real Easy Apply controls must stay bound to their own screening question."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.linked_agent.browser.pages.detail import LinkedInJobDetailPage
from tests.test_linkedin_modern_search import search_page as search_page


def detail(tab):
    return LinkedInJobDetailPage(SimpleNamespace(page=tab), AsyncMock())


@pytest.mark.asyncio
async def test_contacts_and_unknown_labels_never_fill_another_question(search_page):
    _, tab = search_page
    await tab.set_content(
        """<div role="dialog"><div class="fb-dash-form-element">
      <label for="email">Email address</label><input id="email" type="email" required></div>
      <div class="fb-dash-form-element"><label for="phone">Mobile phone number</label>
      <input id="phone" type="tel" required></div></div>"""
    )
    page = detail(tab)
    questions = await page.extract_screening_questions()
    assert [q["question"] for q in questions] == ["Email address", "Mobile phone number"]
    assert await page.fill_answer(questions[0], "candidate@example.invalid")
    assert await page.fill_answer(questions[1], "9123456789")
    assert not await page.fill_answer({"question": "Current CTC"}, "4.5")
    assert await tab.locator("#email").input_value() == "candidate@example.invalid"
    assert await tab.locator("#phone").input_value() == "9123456789"


@pytest.mark.asyncio
async def test_identical_options_are_scoped_to_their_question(search_page):
    _, tab = search_page
    await tab.set_content(
        """<div role="dialog">
      <fieldset><legend>Currently serving notice?</legend>
        <label><input type="radio" name="notice" value="yes">Yes</label>
        <label><input type="radio" name="notice" value="no" required>No</label></fieldset>
      <fieldset><legend>Currently employed?</legend>
        <label><input type="radio" name="employed" value="yes" required>Yes</label>
        <label><input type="radio" name="employed" value="no">No</label></fieldset></div>"""
    )
    page = detail(tab)
    first, second = await page.extract_screening_questions()
    assert await page.fill_answer(first, "No")
    assert await page.fill_answer(second, "Yes")
    assert await tab.locator("[name=notice]:checked").input_value() == "no"
    assert await tab.locator("[name=employed]:checked").input_value() == "yes"
    assert not await page.fill_answer(first, "Not sure")


@pytest.mark.asyncio
async def test_checkbox_groups_are_complete_and_idempotent(search_page):
    _, tab = search_page
    await tab.set_content(
        """<div role="dialog"><fieldset><legend>Professional skills</legend>
      <input id="java" type="checkbox" style="display:none"><label for="java">Java</label>
      <input id="sql" type="checkbox" style="display:none"><label for="sql">SQL</label>
      </fieldset></div>"""
    )
    page = detail(tab)
    question = (await page.extract_screening_questions())[0]
    assert not await page.fill_answer(question, "Java, Rust")
    assert await tab.locator("input:checked").count() == 0
    assert await page.fill_answer(question, "Java, SQL")
    assert await page.fill_answer(question, "Java, SQL")
    assert await tab.locator("input:checked").count() == 2


@pytest.mark.asyncio
async def test_hidden_modals_and_invalid_required_fields_cannot_submit(search_page):
    _, tab = search_page
    await tab.set_content(
        """<div role="dialog" hidden><label>Hidden question<input required></label></div>
      <div role="dialog"><label>Email<input type="email" required></label>
      <button onclick="document.body.dataset.submits='1'">Submit application</button>
      <button onclick="document.body.dataset.wrong='1'">Upload document</button></div>"""
    )
    page = detail(tab)
    (question,) = await page.extract_screening_questions()
    assert question["question"] == "Email"
    assert not await page.submit_application()
    assert not await page.click_next()
    assert not await page.fill_answer(question, "invalid-email")
    assert not await page.submit_application()
    assert await page.fill_answer(question, "candidate@example.invalid")
    assert await page.submit_application()
    assert await tab.locator("body").get_attribute("data-submits") == "1"
    assert await tab.locator("body").get_attribute("data-wrong") is None


@pytest.mark.asyncio
async def test_offline_multistep_application_answers_dynamic_questions_then_submits_once(
    search_page, tmp_path, monkeypatch
):
    from src.linked_agent.browser.apply import LinkedInJobApplier
    from src.linked_agent.config.settings import Settings
    from src.linked_agent.models.entities import Job, ResumeProfile

    _, tab = search_page
    await tab.set_content(
        """<div role="dialog"><label for="email">Email address</label>
      <input id="email" type="email" required><button onclick="second()">Next</button></div>
      <script>
      window.submissions=0;
      function second(){document.querySelector('[role=dialog]').innerHTML=`
        <label for="java">How many years of professional experience do you have with Java?</label>
        <input id="java" type="number" required oninput="extra()"><div id="conditional"></div>
        <button onclick="review()">Review</button>`;}
      function extra(){document.querySelector('#conditional').innerHTML=`
        <fieldset><legend>Are you currently employed?</legend>
        <label><input type="radio" name="employed" value="yes" required>Yes</label>
        <label><input type="radio" name="employed" value="no">No</label></fieldset>`;}
      function review(){if(!document.querySelector('[name=employed]:checked'))throw Error('Unanswered');
        document.body.dataset.experience=document.querySelector('#java').value;
        document.querySelector('[role=dialog]').innerHTML='<button onclick="done()">Submit application</button>';}
      function done(){window.submissions++;document.querySelector('[role=dialog]').innerHTML='<p>Application sent</p><button>Done</button>';}
      </script>"""
    )
    page = detail(tab)
    settings = Settings(
        project_root=tmp_path,
        ai={"use_gemini": False},
        profile={
            "skill_experience_years": {"Java": 1},
            "confirmed_answers": {"Are you currently employed?": "Yes"},
        },
    )
    candidate = ResumeProfile(
        name="Candidate",
        email="candidate@example.invalid",
        skills=["Java"],
        total_experience_years=1,
    )
    qa = SimpleNamespace(_resume=candidate)
    monkeypatch.setattr("src.linked_agent.browser.apply.asyncio.sleep", AsyncMock())
    result = await LinkedInJobApplier(page, settings, qa)._handle_easy_apply_flow(
        Job("123", "Java Developer", "Example employer", "https://www.linkedin.com/jobs/view/123")
    )
    assert result["status"] == "applied", result
    assert await tab.evaluate("window.submissions") == 1
    assert await tab.locator("body").get_attribute("data-experience") == "1"


@pytest.mark.asyncio
async def test_stale_question_and_wrong_dropdown_option_are_rejected(search_page):
    _, tab = search_page
    await tab.set_content(
        """<div role="dialog"><div class="fb-dash-form-element">
      <label for="answer">Current CTC</label><input id="answer" type="text"></div>
      <label for="work">Work authorization</label><select id="work" required>
      <option disabled selected>Select an option</option><option>Yes</option></select></div>"""
    )
    page = detail(tab)
    salary, work = await page.extract_screening_questions()
    await tab.locator("label[for=answer]").evaluate("el => el.textContent = 'Notice period'")
    assert not await page.fill_answer(salary, "4.5")
    assert await tab.locator("#answer").input_value() == ""
    assert not await page.fill_answer(work, "No")
    assert await tab.locator("#work").input_value() == "Select an option"


@pytest.mark.asyncio
async def test_typeahead_uses_only_its_related_suggestions(search_page):
    _, tab = search_page
    await tab.set_content(
        """<div role="dialog"><label for="city">Current city</label>
      <input id="city" role="combobox" aria-controls="cities"><div role="listbox" id="unrelated">
      <div role="option" onclick="document.body.dataset.wrong='1'">Pune</div></div>
      <div role="listbox" id="cities"><div role="option" onclick="document.querySelector('#city').value=this.textContent;this.parentElement.remove()">Pune, Maharashtra, India</div></div></div>"""
    )
    page = detail(tab)
    (question,) = await page.extract_screening_questions()
    assert await page.fill_answer(question, "Pune")
    assert await tab.locator("#city").input_value() == "Pune, Maharashtra, India"
    assert await tab.locator("body").get_attribute("data-wrong") is None
