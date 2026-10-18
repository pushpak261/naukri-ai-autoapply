"""AI-only parsing must never reuse local results or hide provider failures."""
# ruff: noqa: F811
import json
from unittest.mock import AsyncMock

import pytest

from src.naukri_agent.ai.resume_parser import ResumeParser, ResumeProfileSchema
from src.naukri_agent.config.settings import Settings
from tests.test_dashboard_features import dashboard  # noqa: F401


def ai_profile():
    arrays = {'skills', 'technical_skills', 'soft_skills', 'job_titles_held', 'education', 'work_experience', 'certifications', 'languages', 'key_achievements'}
    data = {key: [] if key in arrays else '' for key in ResumeProfileSchema.model_fields}
    data.update(name='Sample Candidate', total_experience_years=2, skills=['Python'])
    return data


@pytest.mark.asyncio
async def test_agent_reuses_only_verified_ai_profile_for_same_file(tmp_path):
    import hashlib
    source = tmp_path / 'resume.pdf'
    source.write_bytes(b'unchanged uploaded resume')
    saved = ai_profile()
    saved.update(file_hash=hashlib.sha256(source.read_bytes()).hexdigest(), raw_text='Original resume evidence', parsing={'method': 'ai'})
    target = tmp_path / 'resume_profile.json'
    target.write_text(json.dumps(saved), encoding='utf-8')
    provider = AsyncMock()
    repo = AsyncMock()
    settings = Settings(project_root=tmp_path, ai={'use_gemini': True, 'gemini_api_key': 'test-only'})
    result = await ResumeParser(provider, repo, settings).parse(source)
    assert result.name == saved['name']
    assert result.raw_text == saved['raw_text']
    provider.generate_content.assert_not_awaited()
    repo.get_cached_profile.assert_not_awaited()
    assert json.loads(target.read_text()) == saved


@pytest.mark.asyncio
@pytest.mark.parametrize('method,changed_file', [('local', False), ('ai', True)])
async def test_agent_rejects_local_or_wrong_file_cache_and_preserves_profile(tmp_path, monkeypatch, method, changed_file):
    import hashlib
    from src.naukri_agent.utils.exceptions import LLMQuotaExceededError
    source = tmp_path / 'resume.pdf'
    source.write_bytes(b'uploaded resume')
    saved = ai_profile()
    saved.update(file_hash='wrong-hash' if changed_file else hashlib.sha256(source.read_bytes()).hexdigest(), parsing={'method': method})
    target = tmp_path / 'resume_profile.json'
    target.write_text(json.dumps(saved), encoding='utf-8')
    provider = AsyncMock()
    provider.generate_content.side_effect = LLMQuotaExceededError('Quota exhausted', is_daily_quota=True)
    settings = Settings(project_root=tmp_path, ai={'use_gemini': True, 'gemini_api_key': 'test-only'})
    repo = AsyncMock()
    parser = ResumeParser(provider, repo, settings)
    monkeypatch.setattr(parser, '_extract_resume_text', lambda path: 'Resume evidence')
    with pytest.raises(LLMQuotaExceededError):
        await parser.parse(source)
    repo.get_cached_profile.assert_not_awaited()
    assert json.loads(target.read_text()) == saved


@pytest.mark.asyncio
async def test_strict_ai_bypasses_local_cache_and_records_provenance(tmp_path, monkeypatch):
    settings = Settings(project_root=tmp_path, ai={'use_gemini': True, 'gemini_api_key': 'test-only'})
    source = tmp_path / 'resume.pdf'
    source.write_bytes(b'fixture bytes')
    repo = AsyncMock()
    provider = AsyncMock()
    provider._model_name = 'gemini-2.5-flash'
    provider.generate_content.return_value = json.dumps(ai_profile())
    parser = ResumeParser(provider, repo, settings)
    monkeypatch.setattr(parser, '_extract_resume_text', lambda path: 'Sample Candidate Python')
    result = await parser.parse(source, require_ai=True)
    assert result.skills == ['Python']
    repo.get_cached_profile.assert_not_awaited()
    assert json.loads((tmp_path / 'resume_profile.json').read_text())['parsing']['method'] == 'ai'
    repo.save_resume_profile.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('response', ['{}', '{"name":""}'])
async def test_strict_ai_failure_preserves_previous_profile(tmp_path, monkeypatch, response):
    source = tmp_path / 'resume.pdf'
    source.write_bytes(b'fixture')
    saved = tmp_path / 'resume_profile.json'
    saved.write_text('{"name":"Previous profile"}')
    provider = AsyncMock()
    provider.generate_content.return_value = response
    parser = ResumeParser(provider, AsyncMock(), Settings(project_root=tmp_path))
    monkeypatch.setattr(parser, '_extract_resume_text', lambda path: 'Sample Candidate')
    with pytest.raises(ValueError):
        await parser.parse(source, require_ai=True)
    assert json.loads(saved.read_text()) == {'name': 'Previous profile'}


@pytest.mark.asyncio
async def test_ai_setup_status_and_upload_preflight(dashboard, monkeypatch):
    status = await dashboard.get('/api/ai/status')
    assert not status.json()['configured']
    upload = await dashboard.post('/api/resume/upload?mode=ai', files={'file': ('resume.pdf', b'fixture', 'application/pdf')})
    assert upload.status_code == 422
    assert 'API key' in upload.json()['detail']
    assert (await dashboard.post('/api/ai/test')).status_code == 422
    updated = await dashboard.put('/api/config', json={'gemini_api_key': 'test-only-secret', 'use_gemini': True, 'ai_model': 'gemini-2.5-flash'})
    assert updated.status_code == 200
    assert 'test-only-secret' not in (await dashboard.get('/api/ai/status')).text
    assert (await dashboard.get('/api/config/linkedin')).json()['ai']['use_gemini']
    from src.naukri_agent.ai.llm_provider import GeminiProvider
    mocked = AsyncMock(return_value='OK')
    monkeypatch.setattr(GeminiProvider, 'generate_content', mocked)
    response = await dashboard.post('/api/ai/test')
    assert response.status_code == 200
    assert 'connectivity test' in mocked.await_args.args[0]


def test_ai_does_not_override_negative_or_unknown_screening_answers(tmp_path):
    from src.linked_agent.ai.question_answerer import LinkedInQuestionAnswerer
    from src.linked_agent.config.settings import Settings as LinkedInSettings
    from src.linked_agent.models.entities import ResumeProfile
    answerer = LinkedInQuestionAnswerer(AsyncMock(), LinkedInSettings(project_root=tmp_path), ResumeProfile())
    question = {'question': 'Are you authorized to work here?', 'field_type': 'radio', 'options': ['Yes', 'No']}
    assert answerer._clean_and_validate_answer(question, 'No') == 'No'
    assert answerer._parse_response('[]', [question])[0]['answer'] == ''


def test_unknown_candidate_details_and_legacy_guesses_are_not_reused(tmp_path):
    from src.naukri_agent.ai.question_answerer import QuestionAnswerer
    from src.naukri_agent.models.entities import ResumeProfile
    old_cache = tmp_path / 'data' / 'qa_cache.json'
    old_cache.parent.mkdir()
    old_cache.write_text('{"authorized to work": "Yes"}')
    answerer = QuestionAnswerer(AsyncMock(), Settings(project_root=tmp_path), ResumeProfile())
    assert answerer._direct_answers['gender'] == ''
    assert answerer._direct_answers['qualification'] == ''
    assert answerer._direct_answers['current_location'] == ''
    assert answerer._try_direct_answer('total experience', 'text') is None
    assert answerer._cache.get('authorized to work') is None
    assert old_cache.read_text() == '{"authorized to work": "Yes"}'


@pytest.mark.asyncio
async def test_ai_reparse_upgrades_local_profile_and_preserves_it_on_failure(dashboard, monkeypatch):
    from api.deps import state
    from src.naukri_agent.ai.llm_provider import GeminiProvider
    source = state.settings.resumes_dir / 'existing.pdf'
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b'fixture resume')
    saved = state.settings.project_root / 'resume_profile.json'
    previous = {'name': 'Existing profile', 'uploaded_file_path': str(source), 'summary': 'Parsed locally without AI.'}
    saved.write_text(json.dumps(previous))
    assert (await dashboard.post('/api/resume/reparse')).status_code == 422
    await dashboard.put('/api/config', json={'gemini_api_key': 'test-only', 'use_gemini': True})
    monkeypatch.setattr(ResumeParser, '_extract_resume_text', lambda self, path: 'Sample Candidate Python')
    generator = AsyncMock(return_value='{}')
    monkeypatch.setattr(GeminiProvider, 'generate_content', generator)
    assert (await dashboard.post('/api/resume/reparse')).status_code == 503
    assert json.loads(saved.read_text()) == previous
    generator.return_value = json.dumps(ai_profile())
    response = await dashboard.post('/api/resume/reparse')
    assert response.status_code == 200, response.text
    assert response.json()['profile']['parsing']['method'] == 'ai'
    assert response.json()['profile']['skills'] == ['Python']
    assert response.json()['profile']['raw_text'] == 'Sample Candidate Python'
