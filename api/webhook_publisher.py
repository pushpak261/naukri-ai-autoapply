"""Publish newly committed browser-agent outcomes from the shared dashboard DB."""
import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from api.deps import state
from src.naukri_agent.models.db_schema import Application, RunLog

logger = logging.getLogger(__name__)


async def publish_since(since, until):
    from api.routes.webhooks import fire_webhook_event

    async with state.db_manager.session_factory() as session:
        applications = (await session.execute(select(Application).where(
            Application.applied_at >= since, Application.applied_at < until,
            Application.status.in_(['applied', 'failed', 'error']),
        ).order_by(Application.applied_at))).scalars().all()
        runs = (await session.execute(select(RunLog).where(
            RunLog.ended_at >= since, RunLog.ended_at < until,
            RunLog.status != 'running',
        ).order_by(RunLog.ended_at))).scalars().all()
    for app in applications:
        event = 'application.created' if app.status == 'applied' else 'application.failed'
        await fire_webhook_event(event, {'id': app.id, 'job_id': app.job_id,
                                        'source': app.source, 'status': app.status,
                                        'match_score': app.match_score})
    for run in runs:
        await fire_webhook_event('run.completed', {'id': run.id, 'status': run.status,
                                                 'jobs_applied': run.jobs_applied,
                                                 'jobs_failed': run.jobs_failed})


async def run_publisher(since):
    # Deliberately do not replay historical/imported outcomes on startup.
    # Delivery is best effort; failed destinations are recorded on each webhook.
    while True:
        await asyncio.sleep(10)
        until = datetime.now(UTC)
        try:
            await publish_since(since, until)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('Webhook publisher failed')
        since = until
