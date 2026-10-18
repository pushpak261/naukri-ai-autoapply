"""Evidence ranking and private preparation briefs use real saved data only."""
# ruff: noqa: F811
import json
from types import SimpleNamespace

import pytest

from libs.common.opportunity import assess_opportunity, evidence_priority, skills
from tests.test_dashboard_features import dashboard  # noqa: F401
from tests.test_dashboard_users import register_client


def test_skill_evidence_handles_aliases_without_substring_matches():
    result = assess_opportunity({'skills': 'Java, JS, C++, SQL'}, {'skills': ['JavaScript', 'C++', 'PostgreSQL']})
    assert result['matching_skills'] == ['JS', 'C++']
    assert result['missing_skills'] == ['Java', 'SQL']
    assert result['score'] == 50
    assert skills('["Python", null, 2, "python"]') == ['Python']


@pytest.mark.parametrize('job,profile', [({'skills': ''}, {'skills': ['Python']}), ({'skills': 'Python'}, {}), ({}, None)])
def test_missing_evidence_is_unknown_instead_of_fake_score(job, profile):
    result = assess_opportunity(job, profile)
    assert result['score'] is None
    assert result['confidence'] == 'low'
    assert evidence_priority(job, profile) == 0


def test_boost_is_bounded_and_submitted_jobs_are_not_recommended_again():
    job = SimpleNamespace(skills='Python, SQL')
    profile = SimpleNamespace(skills=['Python', 'SQL'], technical_skills=[])
    assert evidence_priority(job, profile) == 0.15
    assert assess_opportunity(job, profile, 'applied')['recommendation'] == 'already_in_progress'
    assert assess_opportunity({'skills': 'Python', 'location': 'Nottingham'}, {'skills': ['Python']}, preferred_locations=['No'])['cautions']


def test_eligibility_cautions_override_high_skill_coverage_without_inventing_experience():
    job = {'skills': 'Python', 'experience': '3-5 Yrs'}
    result = assess_opportunity(job, {'skills': ['Python'], 'total_experience_years': 1})
    assert result['score'] == 100
    assert result['recommendation'] == 'review'
    assert any('at least 3 years' in caution for caution in result['cautions'])
    result = assess_opportunity(job, {'skills': ['Python']})
    assert not any('years' in caution for caution in result['cautions'])


@pytest.mark.asyncio
async def test_copilot_shortlist_and_brief_are_private_and_do_not_queue(dashboard):
    from api import identity
    from api.tenants import runtime_for
    from src.naukri_agent.models.db_schema import Application, Job
    from sqlalchemy import func, select

    async with register_client('copilot-a@example.invalid') as alice, register_client('copilot-b@example.invalid') as bob:
        runtime = await runtime_for(identity.find_user('copilot-a@example.invalid'))
        (runtime.settings.project_root / 'resume_profile.json').write_text(json.dumps({'skills': ['Python', 'SQL']}))
        factory = await runtime.db_manager.get_session_factory()
        async with factory() as session, session.begin():
            job = Job(naukri_job_id='copilot1', title='Python Engineer', company='Example', skills='Python, SQL, Rust', url='https://www.naukri.com/job/copilot1', source='naukri')
            session.add(job)
            await session.flush()
            job_id = job.id
        response = await alice.get('/api/copilot/opportunities')
        assert response.status_code == 200
        result = response.json()
        assert result['profile_ready']
        assert result['opportunities'][0]['score'] == 67
        assert result['opportunities'][0]['missing_skills'] == ['Rust']
        brief = (await alice.get(f'/api/copilot/jobs/{job_id}/brief')).json()
        assert brief['matching_skills'] == ['Python', 'SQL']
        assert 'My saved profile includes Python, SQL' in brief['outreach_draft']
        assert '[Add one accurate' in brief['outreach_draft']
        assert (await bob.get(f'/api/copilot/jobs/{job_id}/brief')).status_code == 404
        assert (await bob.get('/api/copilot/opportunities')).json()['opportunities'] == []
        async with factory() as session:
            assert (await session.execute(select(func.count(Application.id)))).scalar_one() == 0
        alice.headers.pop('Authorization')
        assert (await alice.get('/api/copilot/opportunities')).status_code == 401
