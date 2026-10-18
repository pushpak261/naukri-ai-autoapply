import dataclasses
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from libs.common.agent_reasoning import decision_fingerprint, eligibility_concern
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.models.entities import Job, ResumeProfile


@pytest.mark.parametrize('requirement,blocked', [('3-5 years', True), ('0-4 Yrs', False), ('2+ yrs', True), ('6 months', False), ('24 Mar', False), ('Not disclosed', False)])
def test_explicit_eligibility(requirement, blocked):
    candidate = ResumeProfile(total_experience_years=1)
    job = Job('real-id', 'Developer', 'Employer', 'https://example.invalid/job', experience=requirement)
    assert bool(eligibility_concern(candidate, job)) is blocked


def test_semantic_cache_ignores_scrape_timestamp_but_tracks_requirements(tmp_path):
    profile = ResumeProfile(name='Test candidate', total_experience_years=1)
    job = Job('job-id', 'Developer', 'Employer', 'https://example.invalid/job', experience='0-2 Yrs')
    ai = Settings(project_root=tmp_path).ai
    original = decision_fingerprint(profile, job, ai, 70)
    refreshed = dataclasses.replace(job, scraped_at=datetime.now(UTC) + timedelta(days=1), id=900)
    assert decision_fingerprint(profile, refreshed, ai, 70) == original
    refreshed.description = 'Changed mandatory requirements'
    assert decision_fingerprint(profile, refreshed, ai, 70) != original
    assert decision_fingerprint(profile, job, ai, 80) != original


@pytest.mark.asyncio
@pytest.mark.parametrize('platform', ['naukri', 'linkedin'])
async def test_experience_veto_runs_before_api_and_positive_cache(tmp_path, platform):
    if platform == 'linkedin':
        from src.linked_agent.ai.job_matcher import LinkedInJobMatcher as Matcher
        from src.linked_agent.config.settings import Settings as Config
        from src.linked_agent.models.entities import Job as Listing, ResumeProfile as Candidate
    else:
        from src.naukri_agent.ai.job_matcher import JobMatcher as Matcher
        Config, Listing, Candidate = Settings, Job, ResumeProfile
    provider = AsyncMock()
    matcher = Matcher(provider, Config(project_root=tmp_path))
    result = await matcher.match(Candidate(total_experience_years=1), Listing('job-id', 'Engineer', 'Employer', 'https://example.invalid/job', experience='5-8 years'))
    assert not result.should_apply
    assert 'at least 5' in result.match_reasoning
    provider.generate_content.assert_not_awaited()


def test_linkedin_ambiguous_shortened_questions_never_share_answers(tmp_path):
    from src.linked_agent.ai.question_answerer import LinkedInQuestionAnswerer
    from src.linked_agent.config.settings import Settings as Config
    from src.linked_agent.models.entities import ResumeProfile as Candidate
    answerer = LinkedInQuestionAnswerer(AsyncMock(), Config(project_root=tmp_path), Candidate())
    questions = [{'question': 'How many years of experience with Java?', 'field_type': 'text'}, {'question': 'How many years of experience with Python?', 'field_type': 'text'}]
    results = answerer._parse_response(json.dumps([{'question': 'How many years of experience', 'answer': '5'}]), questions)
    assert [item['answer'] for item in results] == ['', '']


def test_naukri_screening_cache_is_scoped_to_employer_and_requirements(tmp_path):
    from src.naukri_agent.ai.question_answerer import QuestionAnswerer
    answerer = QuestionAnswerer(AsyncMock(), Settings(project_root=tmp_path), ResumeProfile())
    first = Job('one', 'Engineer', 'First employer', 'https://example.invalid/one')
    second = Job('two', 'Engineer', 'Second employer', 'https://example.invalid/two')
    answerer._activate_job_context(first)
    answerer._cache.set('Why this company?', 'First employer evidence')
    answerer._cache.save()
    answerer._activate_job_context(second)
    assert answerer._cache.get('Why this company?') is None
    answerer._activate_job_context(first)
    assert answerer._cache.get('Why this company?') == 'First employer evidence'


def test_similar_skill_questions_do_not_reuse_each_others_answers(tmp_path):
    from src.naukri_agent.ai.question_answerer import QACache
    cache = QACache(tmp_path / 'answers.json')
    cache.set('How many years of experience with Java?', '2')
    assert cache.get('How many years of experience with JavaScript?', exact_only=True) is None
    cache.set('How many years of experience with C++?', '3')
    assert cache.get('How many years of experience with C?', exact_only=True) is None
    assert cache.get('How many years of experience with C#?', exact_only=True) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('platform', ['naukri', 'linkedin'])
async def test_rescraped_unchanged_job_reuses_assessment_without_api_call(tmp_path, platform):
    if platform == 'linkedin':
        from src.linked_agent.ai.job_matcher import LinkedInJobMatcher as Matcher
        from src.linked_agent.config.settings import Settings as Config
        from src.linked_agent.models.entities import Job as Listing, ResumeProfile as Candidate
        assessment = {'match_score': 85, 'should_apply': True, 'match_reasoning': 'Java experience matches', 'matching_skills': ['Java'], 'missing_skills': []}
    else:
        from src.naukri_agent.ai.job_matcher import JobMatcher as Matcher
        Config, Listing, Candidate = Settings, Job, ResumeProfile
        assessment = {'score': 85, 'should_apply': True, 'reasoning': 'Java experience matches', 'matching_skills': ['Java'], 'missing_skills': [], 'experience_fit': 'strong', 'location_fit': 'match', 'strengths': [], 'concerns': []}
    provider = AsyncMock()
    provider.generate_content.return_value = json.dumps(assessment)
    matcher = Matcher(provider, Config(project_root=tmp_path, ai={'gemini_api_key': 'test-only'}))
    profile = Candidate(name='Test candidate', total_experience_years=2, skills=['Java'], file_hash='resume-hash')
    job = Listing('job-id', 'Java Engineer', 'Employer', 'https://example.invalid/job', experience='0-2 years')
    first = await matcher.match(profile, job)
    second = await matcher.match(profile, dataclasses.replace(job, scraped_at=datetime.now(UTC) + timedelta(days=1), id=100))
    assert first.should_apply and second.should_apply
    provider.generate_content.assert_awaited_once()
