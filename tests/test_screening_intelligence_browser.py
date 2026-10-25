"""Complete different local employer forms without sending real applications."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from libs.common.screening_review import ScreeningReviewStore
from src.linked_agent.browser.apply import LinkedInJobApplier
from src.linked_agent.config.settings import Settings
from src.linked_agent.models.entities import Job, ResumeProfile
from tests.test_external_applications import employer as employer, run
from tests.test_linkedin_modern_search import search_page as search_page
from tests.test_linkedin_screening_flow import detail


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["role-fit", "motivation"])
async def test_different_linkedin_forms_are_fully_filled_before_one_submission(
    search_page, tmp_path, monkeypatch, variant
):
    _, tab = search_page
    settings = Settings(project_root=tmp_path, ai={"use_gemini": False})
    candidate = ResumeProfile(
        current_title="Software Engineer", total_experience_years=1, skills=["Java"]
    )
    first = Job(
        "123456", "Java Developer", "First employer", "https://www.linkedin.com/jobs/view/123456"
    )
    store = ScreeningReviewStore(tmp_path)
    identifier = store.remember({"question": "Are you willing to relocate?"}, first)
    store.save_answers({identifier: "No"})
    wording = (
        "Describe your relevant experience"
        if variant == "role-fit"
        else "What motivates you to apply for this role?"
    )
    await tab.set_content(
        f"""<dialog open><form>
      <label for="prose">{wording}</label><textarea id="prose" required maxlength="350"></textarea>
      <label for="relocation">Are you open to relocation?</label><select id="relocation" required>
      <option value="" selected>Select an option</option><option>Yes</option><option>No</option></select>
      <button type="submit">Submit application</button></form></dialog><script>
      window.submissions=0; document.querySelector('form').onsubmit=e=>{{e.preventDefault();
        window.answers=[document.querySelector('#prose').value,document.querySelector('#relocation').value];
        window.submissions++;document.querySelector('dialog').innerHTML='Application sent';}};</script>"""
    )
    monkeypatch.setattr("src.linked_agent.browser.apply.asyncio.sleep", AsyncMock())
    result = await LinkedInJobApplier(
        detail(tab), settings, SimpleNamespace(_resume=candidate)
    )._handle_easy_apply_flow(first)
    assert result["status"] == "applied", result
    values = await tab.evaluate("window.answers")
    assert all(values) and "Java" in values[0] and "1 year" in values[0]
    assert len(values[0]) <= 350 and values[1] == "No"
    assert await tab.evaluate("window.submissions") == 1
    assert not store.pending()


@pytest.mark.asyncio
async def test_external_employer_form_reuses_paraphrased_fact_and_writes_motivation(employer):
    worker, page, job = employer
    identifier = worker.review.remember({"question": "Are you willing to relocate?"}, job)
    worker.review.save_answers({identifier: "No"})
    await page.set_content(
        """<label>Save job Java Developer<input type="checkbox"></label><form><label>Why do you want to join our company?
      <textarea required maxlength="350"></textarea></label>
      <label>Are you open to relocation?<select required><option value="">Choose</option><option>Yes</option><option>No</option></select></label>
      <button type="submit">Submit</button></form><script>window.submissions=0;
      document.querySelector('form').onsubmit=e=>{e.preventDefault();
        window.answers=[document.querySelector('textarea').value,document.querySelector('select').value];
        window.submissions++;document.body.innerHTML='<h1>Application received.</h1>';};</script>"""
    )
    result = await run(worker, page, job)
    assert result["status"] == "applied", result
    values = await page.evaluate("window.answers")
    assert all(values) and "Java" in values[0] and values[1] == "No"
    assert len(values[0]) <= 350
    assert await page.evaluate("window.submissions") == 1
    worker.provider.generate_content.assert_not_called()


@pytest.mark.asyncio
async def test_radio_group_labels_do_not_replace_the_actual_boolean_choices(search_page):
    _, tab = search_page
    await tab.set_content(
        """<dialog open><fieldset><legend id="prompt">Are you currently employed?</legend>
      <input type="radio" name="employment" aria-labelledby="prompt" value="true">
      <input type="radio" name="employment" aria-labelledby="prompt" value="false"></fieldset></dialog>"""
    )
    page = detail(tab)
    (question,) = await page.extract_screening_questions()
    assert question["question"] == "Are you currently employed?"
    assert question["options"] == ["Yes", "No"]
    assert await page.fill_answer(question, "No")
    assert await tab.locator('[name="employment"]:checked').input_value() == "false"
