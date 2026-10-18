"""Private, resume-grounded opportunity planning; never queues applications."""
import json
from collections import Counter

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from api.deps import state
from libs.common.opportunity import assess_opportunity, skills
from src.naukri_agent.models.db_schema import Application, Job

router = APIRouter(prefix='/api/copilot', tags=['copilot'])
METHOD = 'Resume evidence rules v1 — structured skill coverage, not hiring probability or an AI match score.'


def load_profile():
    path = state.settings.project_root / 'resume_profile.json'
    try:
        profile = json.loads(path.read_text(encoding='utf-8'))
        return profile if isinstance(profile, dict) else {}
    except (OSError, ValueError):
        return {}


async def records():
    factory = await state.db_manager.get_session_factory()
    async with factory() as session:
        # Bounded for inexpensive refreshes on small deployment instances.
        jobs = (await session.execute(select(Job).order_by(Job.scraped_at.desc(), Job.id.desc()).limit(500))).scalars().all()
        applications = (await session.execute(select(Application).where(Application.job_id.in_([job.id for job in jobs])).order_by(Application.applied_at.desc(), Application.id.desc()))).scalars().all() if jobs else []
    statuses = {}
    for app in applications:
        # An earlier submission must still block a duplicate after a failed retry.
        if app.job_id not in statuses or app.status in ('applied', 'applying', 'pending_retry'):
            statuses[app.job_id] = app.status
    return jobs, statuses


def assess(job, profile, status):
    preferences = getattr(state.settings.profile, 'preferred_locations', [])
    return assess_opportunity(job, profile, status, preferences)


@router.get('/opportunities')
async def opportunities(limit: int = Query(30, ge=1, le=100)):
    profile = load_profile()
    ready = bool(skills(profile.get('skills')) or skills(profile.get('technical_skills')))
    jobs, statuses = await records()
    items, gaps = [], Counter()
    for job in jobs:
        evidence = assess(job, profile, statuses.get(job.id))
        if evidence['recommendation'] != 'already_in_progress':
            gaps.update(set(evidence['missing_skills']))
        items.append({'id': job.id, 'title': job.title, 'company': job.company, 'location': job.location,
                      'source': job.source, 'url': job.url, 'application_status': statuses.get(job.id), **evidence})
    items.sort(key=lambda item: (item['recommendation'] == 'already_in_progress', -(item['score'] if item['score'] is not None else -1)))
    actions = []
    if not ready:
        actions.append({'title': 'Give your copilot a foundation', 'detail': 'Upload or edit your resume and add your actual skills.', 'href': '/resume'})
    if not jobs:
        actions.append({'title': 'Discover your first opportunities', 'detail': 'Configure a search and run the agent in dry-run mode to collect listings.', 'href': '/agent-control'})
    available = sum(item['recommendation'] == 'prioritize' for item in items)
    if available:
        actions.append({'title': f'Review {available} strong evidence {"match" if available == 1 else "matches"}', 'detail': 'Check requirements and prepare a real example for each matching skill before applying.', 'href': '/jobs'})
    if gaps and ready:
        skill, count = gaps.most_common(1)[0]
        actions.append({'title': f'Explore {skill}', 'detail': f'{count} reviewed listings mention this skill without evidence in your profile. Add it only if accurate, or plan learning.', 'href': '/resume'})
    if not actions:
        actions.append({'title': 'Review your application progress', 'detail': 'Check current outcomes before sending more applications.', 'href': '/applications'})
    return {'profile_ready': ready, 'total_reviewed': len(jobs), 'method': METHOD, 'actions': actions,
            'opportunities': items[:limit], 'skill_focus': [{'skill': skill, 'jobs': count} for skill, count in gaps.most_common(6)]}


@router.get('/jobs/{job_id}/brief')
async def preparation_brief(job_id: int):
    factory = await state.db_manager.get_session_factory()
    async with factory() as session:
        job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, 'Job not found')
    profile = load_profile()
    evidence = assess(job, profile, None)
    matched = evidence['matching_skills']
    points = [f'Prepare a real example demonstrating {skill}, including your contribution and a verifiable result.' for skill in matched[:5]]
    if not points:
        points = ['Read the full requirements and identify experience you can honestly evidence before drafting your application.']
    draft = f'Hello {job.company} team,\n\nI am interested in the {job.title} opportunity.'
    if matched:
        draft += ' My saved profile includes ' + ', '.join(matched[:4]) + '.'
    draft += '\n\n[Add one accurate, relevant example from your experience.]\n\nCould you share the main priorities for this role?\n\nBest regards,\n[Your name]'
    return {'job': {'id': job.id, 'title': job.title, 'company': job.company, 'source': job.source},
            'matching_skills': matched, 'missing_skills': evidence['missing_skills'], 'talking_points': points,
            'questions': ['What would success look like in the first 90 days?', 'Which skills are essential on day one, and which can be learned?', 'What are the location, working-hours and compensation expectations?'],
            'checklist': ['Verify the listing and employer on the original platform.', 'Check location, experience and salary expectations.', 'Tailor your resume with truthful evidence; do not add unearned skills.', 'Review every placeholder before sending this draft.'],
            'outreach_draft': draft, 'method': METHOD}
