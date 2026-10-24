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
@pytest.mark.parametrize("native_dialog", [False, True])
async def test_offline_multistep_application_answers_dynamic_questions_then_submits_once(
    search_page, tmp_path, monkeypatch, native_dialog
):
    from src.linked_agent.browser.apply import LinkedInJobApplier
    from src.linked_agent.config.settings import Settings
    from src.linked_agent.models.entities import Job, ResumeProfile

    _, tab = search_page
    markup = """<div role="dialog"><label for="email">Email address</label>
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
    if native_dialog:
        markup = markup.replace('<div role="dialog">', "<dialog open>", 1).replace(
            "</div>", "</dialog>", 1
        )
        markup = markup.replace(
            "querySelector('[role=dialog]')", "querySelector('dialog, [role=dialog]')"
        )
    await tab.set_content(markup)
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


@pytest.mark.asyncio
async def test_employer_apply_anchor_is_not_clicked_as_native_or_in_recommendations(search_page):
    _, tab = search_page
    await tab.set_content(
        """<aside><button onclick="document.body.dataset.wrong='1'">Easy Apply</button></aside>
      <section aria-label="Primary content"><button aria-label="Apply filter">Filter</button>
      <a href="https://www.linkedin.com/safety/go/?url=https%3A%2F%2Femployer.example.invalid" aria-label="Apply on company website"
        onclick="event.preventDefault();document.body.dataset.external='1'">Apply</a></section>"""
    )
    page = detail(tab)
    assert not await page.has_easy_apply()
    assert not await page.click_easy_apply()
    assert await tab.locator("body").get_attribute("data-external") is None
    assert await page.click_any_apply_button()
    assert await tab.locator("body").get_attribute("data-external") == "1"
    assert await tab.locator("body").get_attribute("data-wrong") is None


@pytest.mark.asyncio
async def test_native_apply_link_opens_the_modal(search_page):
    _, tab = search_page
    await tab.set_content(
        """<main><a href="#application" onclick="event.preventDefault();document.body.insertAdjacentHTML('beforeend','<div role=dialog>Contact info</div>')">Easy Apply</a></main>"""
    )
    page = detail(tab)
    assert await page.has_easy_apply()
    assert await page.click_easy_apply()
    assert await tab.locator("[role=dialog]").inner_text() == "Contact info"


@pytest.mark.parametrize(
    "title,levels,excluded",
    [
        ("Java Senior Engineer, Vice President", ["1", "2"], True),
        ("Java Lead_ Vice President- Software Engineer", ["2"], True),
        ("Software Engineer I - Java", ["1", "2"], False),
        ("Senior Java Developer", ["4"], False),
        ("Vice President Java Engineer", ["2", "3"], True),
        ("Associate Software Engineer", ["2", "3"], False),
    ],
)
def test_entry_search_rejects_explicit_senior_titles(title, levels, excluded):
    from src.linked_agent.bot.agent import LinkedInAgent
    from src.linked_agent.config.settings import Settings
    from src.linked_agent.models.entities import Job

    agent = object.__new__(LinkedInAgent)
    agent._settings = Settings(search={"experience_level": levels})
    agent._exclusion_spec = None
    assert (
        agent._is_excluded(Job("1", title, "Company", "https://www.linkedin.com/jobs/view/1"))
        is excluded
    )


def test_entry_search_rejects_explicit_leadership_in_generic_title():
    from src.linked_agent.bot.agent import LinkedInAgent
    from src.linked_agent.config.settings import Settings
    from src.linked_agent.models.entities import Job

    agent = object.__new__(LinkedInAgent)
    agent._settings = Settings(search={"experience_level": ["2"]})
    agent._exclusion_spec = None
    job = Job("1", "Java Developer", "Company", "https://www.linkedin.com/jobs/view/1")
    job.description = "Own complex changes and act as a technical lead for solution design."
    assert agent._is_excluded(job)
    job.description = "Develop APIs under guidance from senior engineers."
    assert not agent._is_excluded(job)


@pytest.mark.asyncio
async def test_job_error_page_does_not_count_as_loaded_listing(search_page):
    from src.linked_agent.bot.agent import LinkedInAgent
    from playwright.async_api import TimeoutError

    _, tab = search_page
    agent = object.__new__(LinkedInAgent)
    await tab.set_content("<main>This site cannot be reached</main>")
    original = tab.wait_for_function

    async def bounded_wait(script, **kwargs):
        return await original(script, timeout=100)

    wrapped = SimpleNamespace(wait_for_function=bounded_wait)
    with pytest.raises(TimeoutError):
        await agent._wait_for_listing_content(wrapped)
    await tab.set_content(
        '<div componentkey="JobDetails_AboutTheJob_123">Java and Spring Boot development role.</div>'
    )
    await agent._wait_for_listing_content(wrapped)


@pytest.mark.asyncio
async def test_modern_city_wrapper_and_equivalent_suggestions(search_page):
    _, tab = search_page
    await tab.set_content(
        """<dialog open><div componentkey="easyApplyFieldFocus_ea.q::1::UNKNOWN::value.validation">
      <p>Location (city)*</p><div><input aria-autocomplete="list" aria-owns="cities" placeholder="Enter city or location"></div></div>
      <div role="listbox" id="cities">
      <div role="option">Pune District, Maharashtra, India</div>
      <div role="option" onclick="document.querySelector('input').value=this.textContent;this.parentElement.remove()">Pune City, Maharashtra, India</div>
      <div role="option">Pune City, Maharashtra, India</div></div><button>Next</button></dialog>"""
    )
    page = detail(tab)
    assert await page.wait_for_apply_modal()
    (question,) = await page.extract_screening_questions()
    assert question["question"] == "Location (city)*"
    assert question["is_required"]
    assert await page.fill_answer(question, "Pune")
    assert await tab.locator("input").input_value() == "Pune City, Maharashtra, India"


@pytest.mark.parametrize(
    "title,types,excluded",
    [
        ("Software Engineer Intern", ["F"], True),
        ("Java Internship", ["F"], True),
        ("Associate Software Engineer", ["F"], False),
        ("Java Intern", ["F", "I"], False),
    ],
)
def test_full_time_search_excludes_internship_titles(title, types, excluded):
    from src.linked_agent.bot.agent import LinkedInAgent
    from src.linked_agent.config.settings import Settings
    from src.linked_agent.models.entities import Job

    agent = object.__new__(LinkedInAgent)
    agent._settings = Settings(search={"job_type": types})
    agent._exclusion_spec = None
    assert (
        agent._is_excluded(Job("1", title, "Company", "https://www.linkedin.com/jobs/view/1"))
        is excluded
    )


@pytest.mark.asyncio
async def test_modern_radio_group_uses_outer_question_heading(search_page):
    _, tab = search_page
    await tab.set_content(
        """<dialog open>
      <div componentkey="easyApplyFieldFocus_employment"><p>Are you currently employed?*</p>
        <div role="radiogroup"><label><input id="employed-yes" name="radio-group-1" type="radio">Yes</label>
          <label><input id="employed-no" name="radio-group-1" type="radio">No</label></div></div>
      <div componentkey="easyApplyFieldFocus_notice"><p>Are you serving notice?*</p>
        <div role="radiogroup"><label><input id="notice-yes" name="radio-group-2" type="radio">Yes</label>
          <label><input id="notice-no" name="radio-group-2" type="radio">No</label></div></div>
      </dialog>"""
    )
    page = detail(tab)
    employment, notice = await page.extract_screening_questions()
    assert employment["question"] == "Are you currently employed?*"
    assert notice["question"] == "Are you serving notice?*"
    assert employment["is_required"]
    assert notice["is_required"]
    assert await page.fill_answer(employment, "Yes")
    assert await page.fill_answer(notice, "No")
    assert await tab.locator("#employed-yes").is_checked()
    assert await tab.locator("#notice-no").is_checked()
    assert not await tab.locator("#employed-no").is_checked()
