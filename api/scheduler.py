"""Single-process scheduler and durable job queue dispatcher for the API host."""
import asyncio
import json
import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import select

from api.deps import state
from src.naukri_agent.models.db_schema import Application, Job

logger = logging.getLogger(__name__)
DAYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')


def validate_schedule(schedule):
    try:
        if schedule.get('type') not in ('daily', 'weekdays', 'weekly', 'custom'):
            raise ValueError('Unknown schedule type')
        # Store a canonical time: lexicographic comparisons require zero padding.
        schedule['time'] = datetime.strptime(schedule['time'], '%H:%M').strftime('%H:%M')
        ZoneInfo(schedule.get('timezone', 'Asia/Kolkata'))
        days = schedule.get('days', [])
        if not isinstance(days, list) or any(day not in DAYS for day in days):
            raise ValueError('Invalid schedule days')
        if schedule['type'] in ('weekly', 'custom') and not days:
            raise ValueError('Choose at least one schedule day')
    except (ValueError, KeyError, TypeError, ZoneInfoNotFoundError) as error:
        raise HTTPException(422, str(error)) from error


def due_key(config, now):
    if not config.get('enabled'):
        return None
    schedule = config['schedule']
    validate_schedule(schedule)
    local = now.astimezone(ZoneInfo(schedule.get('timezone', 'Asia/Kolkata')))
    kind = schedule['type']
    if kind == 'weekdays' and local.weekday() > 4:
        return None
    if kind in ('weekly', 'custom') and DAYS[local.weekday()] not in schedule['days']:
        return None
    if local.strftime('%H:%M') < schedule['time']:
        return None
    return f"{local.date()}:{schedule['time']}:{schedule.get('timezone', 'Asia/Kolkata')}"


def any_agent_running():
    sync_task = getattr(state, "application_sync_task", None)
    if sync_task is not None and not sync_task.done():
        return True
    return any(p is not None and p.poll() is None for p in [state.agent_process, *state.agent_processes.values()])


async def tick(now=None):
    from api.routes.agent import start_agent
    from api.routes.autopilot import _load_config

    now = now or datetime.now(UTC)
    session_factory = await state.db_manager.get_session_factory()
    # A failed launch/forced stop must not leave a queue that relaunches forever.
    if state.agent_process is None or state.agent_process.poll() is not None:
        ids = getattr(state, 'agent_queued_ids', [])
        if ids:
            async with session_factory() as session, session.begin():
                pending = (await session.execute(select(Application).where(Application.job_id.in_(ids), Application.status == 'pending_retry'))).scalars().all()
                for app in pending:
                    app.status = 'failed'
                    app.error_message = 'Agent exited before processing this queued job. Check Agent Control logs.'
            state.agent_queued_ids = []
    if any_agent_running():
        return
    config = await _load_config()
    async with session_factory() as session:
        rows = (await session.execute(select(Job.id, Job.source, Job.posted_date, Job.company, Application.match_score).join(Application, Application.job_id == Job.id).where(Application.status == 'pending_retry').order_by(Application.applied_at).limit(100))).all()
    if rows:
        from api.priority_rules import priority
        preferred = {company.casefold() for company in config.get('company_whitelist', [])}
        rows.sort(key=lambda row: (priority(config, row.match_score, row.posted_date), row.company.casefold() in preferred), reverse=True)
        platform = rows[0].source
        ids = list(dict.fromkeys(row.id for row in rows if row.source == platform))
        await start_agent(platform=platform, job_ids=ids)
        return
    key = due_key(config, now)
    if key is None:
        return
    path = state.settings.data_dir / 'scheduler_state.json'
    previous = json.loads(path.read_text()) if path.exists() else {}
    if previous.get('last_run') == key:
        return
    result = await start_agent(platform='naukri', job_ids=None)
    if result.get('status') == 'started':
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'last_run': key, 'started_at': now.isoformat()}))
        temporary.replace(path)


async def run_scheduler():
    while True:
        try:
            await tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('Scheduler tick failed')
        await asyncio.sleep(15)
