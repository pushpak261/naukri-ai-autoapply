"""Per-user data directories, databases, settings and background agent state."""
import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

import yaml

from api.deps import AppState, current_runtime, current_state, root_state
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.database.repository import SQLAlchemyRepository
from src.naukri_agent.models.db_schema import setup_database_manager

runtimes = {}
_runtime_lock = None
CODE_ROOT = Path(__file__).resolve().parent.parent


def load_user_settings(root):
    config = yaml.safe_load((root / 'config.yaml').read_text()) or {}
    config.update(project_root=root, data_dir=root/'data', db_path=root/'data/naukri_agent.db',
                  sessions_dir=root/'data/sessions', resumes_dir=root/'data/resumes')
    settings = Settings(**config)
    settings.ensure_dirs()
    return settings


def reload_current_settings():
    from src.naukri_agent.config.settings import get_settings
    runtime = current_runtime()
    if runtime.user_id:
        runtime.settings = load_user_settings(runtime.settings.project_root)
    else:
        get_settings.cache_clear()
        runtime.settings = get_settings()


def start_background(runtime):
    from api.scheduler import run_scheduler
    from api.agent_runtime import supervise
    from api.webhook_publisher import run_publisher
    token = current_state.set(runtime)
    try:
        runtime.background_tasks = [asyncio.create_task(run_scheduler()),
                                    asyncio.create_task(supervise(runtime.repo)),
                                    asyncio.create_task(run_publisher(datetime.now(UTC)))]
    finally:
        current_state.reset(token)


async def runtime_for(user):
    global _runtime_lock
    if user['is_operator']:
        return root_state
    if _runtime_lock is None:
        _runtime_lock = asyncio.Lock()
    async with _runtime_lock:
        identifier = user['id']
        if identifier in runtimes:
            return runtimes[identifier]
        from api.identity import workspace_base
        root = workspace_base() / 'users' / identifier
        root.mkdir(parents=True, exist_ok=True)
        config_path = root / 'config.yaml'
        if not config_path.exists():
            config_path.write_text(yaml.safe_dump({
                'naukri': {'email': '', 'password': ''}, 'ai': {'use_gemini': False},
                'application': {'dry_run': True, 'enable_project_indexer': False},
                'resume': {'path': ''},
                'exclusions': {'legacy_domain_filter': False, 'enable_scam_filter': True},
            }))
        runtime = AppState()
        runtime.user_id = identifier
        runtime.settings = load_user_settings(root)
        runtime.db_manager = await setup_database_manager(runtime.settings.db_path)
        runtime.repo = SQLAlchemyRepository(runtime.db_manager)
        await runtime.repo.initialize()
        runtimes[identifier] = runtime
        start_background(runtime)
        return runtime


async def shutdown_tenants():
    global _runtime_lock
    from api.agent_runtime import stop_agent_process
    for runtime in list(runtimes.values()):
        tasks = runtime.background_tasks + ([runtime.application_sync_task] if runtime.application_sync_task else [])
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for process in [runtime.agent_process, *runtime.agent_processes.values()]:
            await asyncio.to_thread(stop_agent_process, process)
        await runtime.db_manager.engine.dispose()
    runtimes.clear()
    _runtime_lock = None


def agent_environment():
    runtime = current_runtime()
    env = os.environ.copy()
    if runtime.user_id:
        # Platform and dashboard credentials in the host belong to the operator.
        for name in list(env):
            if name.startswith(('NAUKRI_', 'LINKEDIN_', 'GMAIL_', 'GEMINI_', 'JWT_', 'DASHBOARD_')) or name in ('USE_GEMINI', 'SMTP_USER', 'SMTP_PASSWORD'):
                env.pop(name, None)
        env['AGENT_WORKSPACE'] = str(runtime.settings.project_root)
        env['SESSION_ENCRYPTION_KEY'] = os.environ.get('SESSION_ENCRYPTION_KEY') or f'local-{CODE_ROOT}'
        env['PYTHONPATH'] = str(CODE_ROOT)
    return env


async def validate_agent_configuration(platform):
    from fastapi import HTTPException
    from sqlalchemy import select
    from libs.common.security import decrypt_value
    from src.naukri_agent.models.db_schema import NaukriAccount
    runtime = current_runtime()
    if not runtime.user_id:
        return
    if platform == 'linkedin':
        from src.linked_agent.config.settings import Settings as LinkedInSettings
        root = runtime.settings.project_root
        config = yaml.safe_load((root / 'config.yaml').read_text()) or {}
        path = root / 'linkedin_config.yaml'
        if path.exists():
            for key, value in (yaml.safe_load(path.read_text()) or {}).items():
                config[key] = {**config.get(key, {}), **value} if isinstance(value, dict) else value
        config.update(project_root=root, data_dir=root/'data/linkedin', db_path=root/'data/linkedin/linkedin_agent.db', sessions_dir=root/'data/linkedin/sessions', resumes_dir=root/'data/resumes')
        settings = LinkedInSettings(**config)
    else:
        settings = runtime.settings.model_copy(deep=True)
        async with runtime.db_manager.session_factory() as session:
            active = (await session.execute(select(NaukriAccount).where(NaukriAccount.is_active.is_(True)))).scalars().first()
            if active:
                settings.naukri.email = active.email
                settings.naukri.password = decrypt_value(active.password)
    problems = settings.validate_required()
    if problems:
        raise HTTPException(422, "Complete your platform credentials and resume configuration before starting: " + "; ".join(problems))
