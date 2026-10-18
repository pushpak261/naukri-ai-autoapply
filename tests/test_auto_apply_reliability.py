"""Auto-apply must preserve unknown facts and confirm real submissions."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import func, select

from libs.common.screening import evidence_answer
from src.linked_agent.config.settings import Settings as LinkedInSettings
from src.linked_agent.models.entities import Job as LinkedInJob, ResumeProfile


@pytest.mark.parametrize('text', ['Are you authorized to work here?', 'Are you willing to relocate?', 'Gender', 'Date of birth', 'How many years of Java experience?', 'Expected salary'])
def test_missing_personal_facts_are_not_guessed(tmp_path, text):
    settings = LinkedInSettings(project_root=tmp_path)
    assert evidence_answer({'question': text, 'options': ['Yes', 'No']}, settings, ResumeProfile()) == ''


def test_explicit_evidence_and_options_are_respected(tmp_path):
    settings = LinkedInSettings(project_root=tmp_path, profile={'current_location':'Mumbai', 'total_experience':'3'})
    assert evidence_answer({'question':'Current city'}, settings) == 'Mumbai'
    assert evidence_answer({'question':'Current city', 'options':['Pune','Delhi']}, settings) == ''
    assert evidence_answer({'question':'Total experience', 'field_type':'number'}, settings) == '3'
    assert evidence_answer({'question':'Total experience in Java', 'field_type':'number'}, settings) == ''


@pytest.mark.asyncio
async def test_linkedin_required_unknown_stops_before_submit_even_when_matching_disabled(tmp_path):
    from src.linked_agent.browser.apply import LinkedInJobApplier
    settings = LinkedInSettings(project_root=tmp_path, ai={'use_gemini':True, 'enable_matching':False})
    detail = MagicMock()
    detail.wait_for_apply_modal = AsyncMock(return_value=True)
    detail.has_submit_success = AsyncMock(return_value=False)
    detail.extract_screening_questions = AsyncMock(return_value=[{'question':'Work authorization?', 'field_type':'radio', 'required':True, 'options':['Yes','No']}])
    qa = MagicMock()
    qa.answer_questions = AsyncMock(return_value=[{'question':'Work authorization?', 'answer':''}])
    detail.submit_application = AsyncMock()
    applier = LinkedInJobApplier(detail, settings, qa)
    with patch('src.linked_agent.browser.apply.asyncio.sleep', new=AsyncMock()):
        result = await applier._handle_easy_apply_flow(LinkedInJob('id','Developer','Employer','https://example.invalid/job'))
    assert result['status'] == 'skipped_screening'
    qa.answer_questions.assert_awaited_once()
    detail.submit_application.assert_not_awaited()


@pytest.mark.asyncio
async def test_linkedin_modal_disappearance_is_not_submission_confirmation(tmp_path):
    from src.linked_agent.browser.apply import LinkedInJobApplier
    detail = MagicMock()
    detail.wait_for_apply_modal = AsyncMock(side_effect=[True, False])
    detail.has_submit_success = AsyncMock(return_value=False)
    detail.extract_screening_questions = AsyncMock(return_value=[])
    detail.get_modal_text = AsyncMock(return_value='Review application')
    detail.submit_application = AsyncMock(return_value=True)
    detail.page.evaluate = AsyncMock(return_value=True)
    detail.page.screenshot = AsyncMock()
    applier = LinkedInJobApplier(detail, LinkedInSettings(project_root=tmp_path), MagicMock())
    with patch('src.linked_agent.browser.apply.asyncio.sleep', new=AsyncMock()):
        result = await applier._handle_easy_apply_flow(LinkedInJob('id','Developer','Employer','https://example.invalid/job'))
    assert result['status'] == 'uncertain'
    detail.submit_application.assert_awaited_once()


@pytest.mark.asyncio
async def test_naukri_missing_required_answers_prevent_submit(tmp_path):
    from src.naukri_agent.browser.apply import JobApplier
    from src.naukri_agent.config.settings import Settings
    from src.naukri_agent.models.entities import Job
    detail = MagicMock()
    detail.check_application_failure = AsyncMock(return_value='')
    detail.check_application_success = AsyncMock(return_value=False)
    detail.detect_screening_questions = AsyncMock(return_value=True)
    detail.submit_application = AsyncMock()
    applier = JobApplier(detail, Settings(project_root=tmp_path), MagicMock())
    applier._fill_screening_questions = AsyncMock(return_value=False)
    with patch('src.naukri_agent.browser.apply.asyncio.sleep', new=AsyncMock()):
        result = await applier._handle_apply_flow(Job(naukri_job_id='id',title='Developer',company='Employer',url='https://example.invalid/job'))
    assert result['status'] == 'skipped_screening'
    detail.submit_application.assert_not_awaited()


@pytest.mark.asyncio
async def test_linkedin_claim_survives_restart_and_finalizes_one_row(tmp_path):
    from src.linked_agent.models.db_schema import setup_database_manager, Application
    from src.linked_agent.database.repository import SQLAlchemyRepository
    manager = await setup_database_manager(tmp_path/'linkedin.db')
    try:
        repo = SQLAlchemyRepository(manager)
        await repo.initialize()
        job = await repo.save_job('test-id','Developer','Employer','https://example.invalid/job')
        claim = await repo.save_application(job.id, 90, 'applying')
        restarted = SQLAlchemyRepository(manager)
        await restarted.initialize()
        assert restarted.is_already_applied('test-id')
        result = await restarted.save_application(job.id, 90, 'uncertain')
        assert result.id == claim.id
        async with manager.get_session() as session:
            assert (await session.execute(select(func.count(Application.id)))).scalar_one() == 1
        another = SQLAlchemyRepository(manager)
        await another.initialize()
        assert another.is_already_applied('test-id')
    finally:
        await manager.engine.dispose()


@pytest.mark.asyncio
async def test_linkedin_evidenced_answer_and_confirmed_submission(tmp_path):
    from src.linked_agent.browser.apply import LinkedInJobApplier
    detail = MagicMock()
    detail.wait_for_apply_modal = AsyncMock(return_value=True)
    detail.has_submit_success = AsyncMock(side_effect=[False, True])
    question = {'question':'Total work experience?', 'field_type':'text', 'required':True}
    detail.extract_screening_questions = AsyncMock(return_value=[question])
    detail.fill_answer = AsyncMock(return_value=True)
    detail.unfollow_company = AsyncMock()
    detail.submit_application = AsyncMock(return_value=True)
    detail.page.evaluate = AsyncMock(return_value=True)
    qa = MagicMock()
    qa.answer_questions = AsyncMock(return_value=[{'question':question['question'], 'answer':'3'}])
    settings = LinkedInSettings(project_root=tmp_path, ai={'use_gemini':True}, profile={'total_experience':'3'})
    applier = LinkedInJobApplier(detail, settings, qa)
    with patch('src.linked_agent.browser.apply.asyncio.sleep', new=AsyncMock()):
        result = await applier._handle_easy_apply_flow(LinkedInJob('id','Developer','Employer','https://example.invalid/job'))
    assert result['status'] == 'applied'
    detail.fill_answer.assert_awaited_once_with(question, '3')
    detail.submit_application.assert_awaited_once()


def test_invalid_numeric_answers_do_not_invent_defaults(tmp_path):
    from src.linked_agent.ai.question_answerer import LinkedInQuestionAnswerer
    answerer = LinkedInQuestionAnswerer(AsyncMock(), LinkedInSettings(project_root=tmp_path, ai={'use_gemini':True}), ResumeProfile())
    for text in ('Expected salary', 'Current CTC', 'Notice period', 'Weekly hours', 'How many years of experience with Java?'):
        assert answerer._clean_and_validate_answer({'question':text,'field_type':'text'}, 'Unknown') == ''


@pytest.mark.asyncio
async def test_naukri_dry_run_does_not_block_later_real_application(tmp_path):
    from src.naukri_agent.models.db_schema import setup_database_manager
    from src.naukri_agent.database.repository import SQLAlchemyRepository
    manager = await setup_database_manager(tmp_path/'naukri.db')
    try:
        repo = SQLAlchemyRepository(manager)
        await repo.initialize()
        job = await repo.save_job('test-dry-run','Developer','Employer','https://example.invalid/job')
        dry = await repo.save_application(job.id, 90, 'skipped_dry_run')
        assert not repo.is_already_applied('test-dry-run')
        restarted = SQLAlchemyRepository(manager)
        await restarted.initialize()
        assert not restarted.is_already_applied('test-dry-run')
        claim = await restarted.begin_application(job.id, 90)
        assert claim != dry.id
        await restarted.finalize_application(claim, 'applied')
        assert restarted.is_already_applied('test-dry-run')
    finally:
        await manager.engine.dispose()


@pytest.mark.asyncio
async def test_naukri_unmatched_choices_are_not_replaced_by_first_option():
    from src.naukri_agent.browser.pages.detail import JobDetailPage
    page = JobDetailPage(MagicMock(), MagicMock())
    select_element = MagicMock()
    select_element.select_option = AsyncMock()
    options = [{'text':'Yes','value':'yes','selector':'#yes'}, {'text':'No','value':'no','selector':'#no'}]
    assert not await page._select_dropdown_option_by_metadata(select_element, options, 'Unknown')
    select_element.select_option.assert_not_awaited()
    assert not await page._select_choice_option_by_metadata(options, 'Unknown')


@pytest.mark.asyncio
async def test_linkedin_unknown_location_does_not_pick_first_suggestion():
    from src.linked_agent.browser.pages.detail import LinkedInJobDetailPage
    engine = MagicMock()
    engine.page.evaluate = AsyncMock(side_effect=[True, False])
    engine.page.keyboard.press = AsyncMock()
    page = LinkedInJobDetailPage(engine, MagicMock())
    with patch('src.linked_agent.browser.pages.detail.asyncio.sleep', new=AsyncMock()):
        assert not await page._fill_combobox_answer('Current city', 'Mumbai')
    engine.page.keyboard.press.assert_not_awaited()
