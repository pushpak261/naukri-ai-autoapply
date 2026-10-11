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
                Application.status == 'applied', Job.source == 'naukri'
            ).distinct().limit(50))).scalars().all()
        if not jobs:
            state.application_sync_result = {'running': False, 'synced_count': 0, 'message': 'No Naukri applications to verify'}
            return
        async with asyncio.timeout(300):
            observed = await observe_applications(state.settings, state.db_manager, jobs)
        now = datetime.now(UTC)
        async with state.db_manager.session_factory() as session, session.begin():
            for job_id, status in observed.items():
                job = await session.get(Job, job_id)
                if job:
                    job.naukri_status = status
                    job.status_last_synced = now
        state.application_sync_result = {'running': False, 'synced_count': len(observed), 'message': f'Verified {len(observed)} applications on Naukri', 'synced_at': now.isoformat()}
    except asyncio.CancelledError:
        state.application_sync_result = {'running': False, 'synced_count': 0, 'error': 'Status sync cancelled'}
        raise
    except Exception as error:
        state.application_sync_result = {'running': False, 'synced_count': 0, 'error': str(error) or 'Status sync timed out'}
