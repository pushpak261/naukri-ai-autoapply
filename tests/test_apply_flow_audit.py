"""Submission sequencing, prefilled fields and attachment isolation."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.linked_agent.browser.apply import LinkedInJobApplier
from src.linked_agent.config.settings import Settings
from src.linked_agent.models.entities import Job


def detail():
    page = MagicMock()
    page.wait_for_apply_modal = AsyncMock(return_value=True)
    page.has_submit_success = AsyncMock(side_effect=[False, True])
    page.submit_application = AsyncMock(return_value=True)
    page.unfollow_company = AsyncMock()
    page.fill_answer = AsyncMock(return_value=True)
    page.page.evaluate = AsyncMock(return_value=True)
    return page


@pytest.mark.asyncio
async def test_linkedin_submits_only_once_without_confirmation(tmp_path):
    page = detail()
    page.has_submit_success = AsyncMock(return_value=False)
    applier = LinkedInJobApplier(page, Settings(project_root=tmp_path), MagicMock())
    with patch('src.linked_agent.browser.apply.asyncio.sleep', new=AsyncMock()):
        assert (await applier._submit_once_and_confirm())['status'] == 'uncertain'
        assert (await applier._submit_once_and_confirm())['status'] == 'uncertain'
    page.submit_application.assert_awaited_once()


@pytest.mark.asyncio
async def test_prefilled_answer_is_not_overwritten(tmp_path):
    page = detail()
    page.extract_screening_questions = AsyncMock(return_value=[{'question':'Total experience?', 'field_type':'text', 'current_value':'3', 'is_required':True}])
    qa = MagicMock()
    qa.answer_questions = AsyncMock()
    applier = LinkedInJobApplier(page, Settings(project_root=tmp_path), qa)
    with patch('src.linked_agent.browser.apply.asyncio.sleep', new=AsyncMock()):
        result = await applier._handle_easy_apply_flow(Job('test','Developer','Employer','https://example.invalid/job'))
    assert result['status'] == 'applied'
    qa.answer_questions.assert_not_awaited()
    page.fill_answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_optional_unknown_answer_does_not_block_submission(tmp_path):
    page = detail()
    page.extract_screening_questions = AsyncMock(return_value=[{'question':'Optional additional details', 'field_type':'text', 'current_value':'', 'is_required':False}])
    qa = MagicMock()
    qa.answer_questions = AsyncMock(return_value=[{'answer':''}])
    applier = LinkedInJobApplier(page, Settings(project_root=tmp_path, ai={'use_gemini':True}), qa)
    with patch('src.linked_agent.browser.apply.asyncio.sleep', new=AsyncMock()):
        result = await applier._handle_easy_apply_flow(Job('test','Developer','Employer','https://example.invalid/job'))
    assert result['status'] == 'applied'


@pytest.mark.asyncio
@pytest.mark.parametrize('label', ['Resume', 'Cover letter'])
async def test_failed_resume_or_other_required_attachment_blocks_submit(tmp_path, label):
    (tmp_path/'selected.pdf').write_bytes(b'test-only')
    page = detail()
    page.extract_screening_questions = AsyncMock(return_value=[{'question':label, 'field_type':'file', 'current_value':'', 'is_required':True, 'input_id':'resume-file'}])
    page.upload_resume_file = AsyncMock(return_value=False)
    applier = LinkedInJobApplier(page, Settings(project_root=tmp_path, resume={'path':'selected.pdf'}), MagicMock())
    with patch('src.linked_agent.browser.apply.asyncio.sleep', new=AsyncMock()):
        result = await applier._handle_easy_apply_flow(Job('test','Developer','Employer','https://example.invalid/job'))
    assert result['status'] == 'skipped_screening'
    page.submit_application.assert_not_awaited()
    if label == 'Cover letter':
        page.upload_resume_file.assert_not_awaited()
    else:
        assert page.upload_resume_file.await_args.kwargs['field_id'] == 'resume-file'


@pytest.mark.asyncio
async def test_resume_upload_targets_its_field_not_the_first_file_input(tmp_path):
    from src.linked_agent.browser.pages.detail import LinkedInJobDetailPage
    selected = tmp_path/'resume.pdf'
    selected.write_bytes(b'test-only')
    cover, resume = MagicMock(), MagicMock()
    cover.get_attribute = AsyncMock(return_value='cover')
    resume.get_attribute = AsyncMock(return_value='resume')
    cover.set_input_files, resume.set_input_files = AsyncMock(), AsyncMock()
    engine = MagicMock()
    engine.page.query_selector_all = AsyncMock(return_value=[cover,resume])
    page = LinkedInJobDetailPage(engine, MagicMock())
    with patch('src.linked_agent.browser.pages.detail.asyncio.sleep', new=AsyncMock()):
        assert await page.upload_resume_file(str(selected), field_id='resume')
    cover.set_input_files.assert_not_awaited()
    resume.set_input_files.assert_awaited_once_with(str(selected))


@pytest.mark.asyncio
async def test_naukri_waits_for_confirmation_without_submitting_again(tmp_path):
    from src.naukri_agent.browser.apply import JobApplier
    from src.naukri_agent.config.settings import Settings as NaukriSettings
    from src.naukri_agent.models.entities import Job as NaukriJob
    page = MagicMock()
    page.check_application_failure = AsyncMock(return_value='')
    page.check_application_success = AsyncMock(return_value=False)
    page.is_already_applied = AsyncMock(return_value=False)
    page.detect_screening_questions = AsyncMock(return_value=True)
    page.click_intermediate_save_button = AsyncMock(return_value=False)
    page._trigger_form_validation = AsyncMock()
    page.submit_application = AsyncMock(return_value=True)
    applier = JobApplier(page, NaukriSettings(project_root=tmp_path), MagicMock())
    applier._fill_screening_questions = AsyncMock(return_value=True)
    with patch('src.naukri_agent.browser.apply.asyncio.sleep', new=AsyncMock()):
        result = await applier._handle_apply_flow(NaukriJob('test','Developer','Employer','https://example.invalid/job'))
    assert result['status'] == 'uncertain'
    page.submit_application.assert_awaited_once()


@pytest.mark.asyncio
async def test_real_dom_extraction_preserves_checked_fields_and_rejects_placeholders():
    from playwright.async_api import async_playwright, Error
    from src.linked_agent.browser.pages.detail import LinkedInJobDetailPage
    async with async_playwright() as runtime:
        try:
            browser = await runtime.chromium.launch(headless=True)
        except Error as error:
            if 'Executable doesn\'t exist' in str(error):
                pytest.skip('Chromium must be installed for the local DOM regression')
            raise
        try:
            tab = await browser.new_page()
            await tab.set_content('''<div role="dialog">
              <div class="fb-dash-form-element"><label>Total experience</label><input type="number" value="3" required></div>
              <div class="fb-dash-form-element"><label>Choose location</label><select required><option value="0" selected disabled>Select an option</option><option value="1">Mumbai</option></select></div>
              <div class="fb-dash-form-element"><label>Preferred working arrangement</label><label><input type="radio" name="work" value="remote" checked>Remote</label><label><input type="radio" name="work" value="office">Office</label></div>
              <div class="fb-dash-form-element"><label>Previously selected checkbox</label><label><input type="checkbox" checked>Selected preference</label></div>
            </div>''')
            engine = MagicMock()
            engine.page = tab
            from src.linked_agent.config.constants import JobDetailSelectors
            await tab.evaluate('''() => {
              const hidden = document.createElement('button'); hidden.textContent = 'Easy Apply'; hidden.style.display='none'; document.body.prepend(hidden);
              const filter = document.createElement('button'); filter.textContent = 'Apply filters'; document.body.append(filter);
              const visible = document.createElement('button'); visible.textContent = 'Easy Apply'; visible.id='visible-apply'; document.body.append(visible);
            }''')
            selected = await tab.query_selector(JobDetailSelectors.APPLY_BUTTON)
            assert await selected.get_attribute('id') == 'visible-apply'
            result = await LinkedInJobDetailPage(engine, MagicMock()).extract_screening_questions()
            by_name = {q['question']:q for q in result}
            assert len(result) == 4
            assert by_name['Total experience']['current_value'] == '3'
            assert by_name['Choose location']['current_value'] == ''
            assert by_name['Preferred working arrangement']['current_value'] == 'remote'
            assert by_name['Previously selected checkbox']['current_value']
        finally:
            await browser.close()
