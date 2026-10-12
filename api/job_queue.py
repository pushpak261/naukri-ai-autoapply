"""Persistent application queue consumed by the existing browser agents."""
import dataclasses
import json
import os
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select

from src.naukri_agent.models.db_schema import Application, Job


async def enqueue_jobs(session_factory, job_ids):
    ids = list(dict.fromkeys(job_ids))
    if not ids or len(ids) > 100:
        raise HTTPException(422, 'Select between 1 and 100 jobs')
    queued = 0
    async with session_factory() as session, session.begin():
        jobs = (await session.execute(select(Job).where(Job.id.in_(ids)))).scalars().all()
        if len(jobs) != len(ids):
            raise HTTPException(404, 'One or more selected jobs no longer exist')
        for job in jobs:
            if job.source not in ('naukri', 'linkedin'):
                raise HTTPException(422, 'Unsupported job platform')
            applications = (await session.execute(select(Application).where(Application.job_id == job.id).order_by(Application.applied_at.desc()))).scalars().all()
            if any(app.status in ('applied', 'applying', 'pending_retry') for app in applications):
                continue
            app = applications[0] if applications else Application(job_id=job.id, source=job.source)
            if app.id is not None and app.status in ('failed', 'error'):
                if app.retry_count >= app.max_retries:
                    continue
                app.retry_count += 1
                app.last_retry_at = datetime.now(UTC)
            app.status = 'pending_retry'
            app.error_message = ''
            session.add(app)
            queued += 1
    return queued


class SelectedJobSearcher:
    def __init__(self, delegate, jobs):
        self.delegate = delegate
        self.jobs = jobs

    async def search_all(self, *args, **kwargs):
        return self.jobs

    def __getattr__(self, name):
        return getattr(self.delegate, name)


async def run_selected_jobs(agent, db_manager, platform, dry_run=False):
    """Use the normal login/scoring/apply pipeline for explicitly queued jobs."""
    raw = os.environ.get('AGENT_JOB_IDS')
    if not raw:
        await agent.run(dry_run=dry_run)
        return
    ids = json.loads(raw)
    if not isinstance(ids, list) or not ids or not all(isinstance(i, int) and i > 0 for i in ids):
        raise ValueError('Invalid queued job IDs')
    if db_manager is None:
        raise RuntimeError('Shared dashboard database is required for queued jobs')
    if platform == 'linkedin':
        from src.linked_agent.models.entities import Job as DomainJob
    else:
        from src.naukri_agent.models.entities import Job as DomainJob
    fields = {field.name for field in dataclasses.fields(DomainJob)} - {'id'}
    async with db_manager.session_factory() as session:
        rows = (await session.execute(select(Job).where(Job.id.in_(ids), Job.source == platform))).scalars().all()
        by_id = {row.id: row for row in rows}
        jobs = []
        for queue_position, job_id in enumerate(ids):
            row = by_id.get(job_id)
            if row is None:
                continue
            from urllib.parse import urlsplit
            parsed = urlsplit(row.url)
            hosts = ('naukri.com', 'www.naukri.com') if platform == 'naukri' else ('linkedin.com', 'www.linkedin.com')
            if parsed.scheme != 'https' or parsed.hostname not in hosts or parsed.username or parsed.password:
                raise ValueError('Queued jobs must link to the selected job platform over HTTPS')
            values = {name: getattr(row, name) for name in fields if hasattr(row, name)}
            if platform == 'linkedin':
                values['linkedin_job_id'] = row.naukri_job_id.removeprefix('li_')
            job = DomainJob(**values)
            job._queue_priority = len(ids) - queue_position
            jobs.append(job)
    agent._job_searcher = SelectedJobSearcher(agent._job_searcher, jobs)
    failed = False
    try:
        await agent.run(dry_run=dry_run)
        failed = bool(getattr(agent, '_run_error', False))
    except BaseException:
        failed = True
        raise
    finally:
        # Filtered/capped/aborted jobs must not remain queued forever.
        async with db_manager.session_factory() as session, session.begin():
            pending = (await session.execute(select(Application).where(Application.job_id.in_(ids), Application.status == 'pending_retry'))).scalars().all()
            for app in pending:
                app.status = 'failed' if failed else 'skipped_filters'
                app.error_message = 'Agent did not submit this job; review the run log for login, filters, dry-run or daily-cap details.'
