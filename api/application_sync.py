"""Verify application state on Naukri without fabricating recruiter outcomes."""
import asyncio
from datetime import UTC, datetime
from urllib.parse import urlparse

from sqlalchemy import select

from api.deps import state
from src.naukri_agent.models.db_schema import Application, Job, NaukriAccount


async def observe_applications(settings, db_manager, jobs):
    from libs.common.security import decrypt_value
    from src.naukri_agent.bot.factory import DependencyFactory
    from src.naukri_agent.browser.pages.detail import JobDetailPage

    settings = settings.model_copy(deep=True)
    async with db_manager.session_factory() as session:
        active = (await session.execute(select(NaukriAccount).where(NaukriAccount.is_active.is_(True)))).scalars().first()
        if active:
            settings.naukri.email = active.email
            settings.naukri.password = decrypt_value(active.password)
    factory = DependencyFactory(settings, db_manager=db_manager)
    engine = factory.get_browser_engine()
    if active:
        engine.set_session_for_account(active.email)
    try:
        await engine.launch()
        if not await factory.create_login_handler().login():
            raise RuntimeError('Naukri login failed. Restore a valid session before syncing.')
        detail = JobDetailPage(engine=engine, interactions=factory.get_browser_interactions())
        observed = {}
        for job in jobs:
            url = urlparse(job.url)
            if url.scheme != 'https' or url.hostname not in ('www.naukri.com', 'naukri.com'):
                continue
            await detail.navigate(job.url)
            if await detail.is_already_applied():
                observed[job.id] = 'applied'
        return observed
    finally:
        await engine.close()


async def sync_applications():
    state.application_sync_result = {'running': True, 'synced_count': 0, 'message': 'Checking Naukri application pages'}
    try:
        async with state.db_manager.session_factory() as session:
            jobs = (await session.execute(select(Job).join(Application).where(
                Application.status.in_(['applied', 'uncertain']), Job.source == 'naukri'
            ).order_by(Job.id.desc()).distinct().limit(50))).scalars().all()
        if not jobs:
            state.application_sync_result = {'running': False, 'synced_count': 0, 'message': 'No submitted or uncertain Naukri applications to verify'}
            return
        from api.agent_runtime import _shared_lock, ensure_browser_capacity
        from api.tenants import validate_agent_configuration
        async with _shared_lock():
            ensure_browser_capacity()
            await validate_agent_configuration("naukri", require_search=False)
        async with asyncio.timeout(300):
            observed = await observe_applications(state.settings, state.db_manager, jobs)
        now = datetime.now(UTC)
        async with state.db_manager.session_factory() as session, session.begin():
            for job_id, status in observed.items():
                job = await session.get(Job, job_id)
                if job:
                    job.naukri_status = status
                    job.status_last_synced = now
        unconfirmed = len(jobs) - len(observed)
        state.application_sync_result = {
            'running': False, 'synced_count': len(observed),
            'checked_count': len(jobs), 'unconfirmed_count': unconfirmed,
            'message': f'Verified {len(observed)} of {len(jobs)} applications on Naukri; {unconfirmed} remain unconfirmed. No applications were resubmitted.',
            'synced_at': now.isoformat(),
        }
    except asyncio.CancelledError:
        state.application_sync_result = {'running': False, 'synced_count': 0, 'error': 'Status sync cancelled'}
        raise
    except Exception as error:
        state.application_sync_result = {'running': False, 'synced_count': 0, 'error': str(error) or 'Status sync timed out'}
