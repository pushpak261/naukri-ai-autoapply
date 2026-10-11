"""Company preferences shared by the Naukri and LinkedIn apply pipelines."""
import json
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from src.naukri_agent.models.db_schema import Application, Job


class CompanyPolicy:
    def __init__(self, settings, platform):
        root = settings.project_root
        self.config = {}
        if isinstance(root, Path):
            # The dashboard owns one configuration shared by both platforms.
            data_dir = settings.data_dir if platform == 'naukri' else root / 'data'
            if isinstance(data_dir, Path):
                path = data_dir / 'autopilot_config.json'
                if path.exists():
                    self.config = json.loads(path.read_text())
        self.blacklist = {x.strip().casefold() for x in self.config.get('company_blacklist', [])}
        self.whitelist = {x.strip().casefold() for x in self.config.get('company_whitelist', [])}

    def priority(self, company):
        return 1.0 if company.strip().casefold() in self.whitelist else 0.0

    async def allowed(self, company, repository, platform):
        name = company.strip().casefold()
        if name in self.blacklist:
            return False, 'Company is blacklisted'
        if not self.config.get('enabled'):
            return True, ''
        manager = getattr(repository, '_db_manager' if platform == 'naukri' else '_naukri_db', None)
        if manager is None:
            return False, 'Company limits require the shared dashboard database'
        tier_map = {k.strip().casefold(): v for k, v in self.config.get('tier_map', {}).items()}
        tier = tier_map.get(name, 'default')
        cap = self.config.get('throttle', {}).get(f'{tier}_daily', 5)
        zone = ZoneInfo(self.config.get('schedule', {}).get('timezone', 'Asia/Kolkata'))
        start = datetime.now(zone).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
        async with manager.session_factory() as session:
            count = (await session.execute(select(func.count(Application.id)).join(Job).where(
                func.lower(func.trim(Job.company)) == name,
                Application.status.in_(['applied', 'applying']),
                Application.applied_at >= start,
            ))).scalar_one()
        return (count < cap, '' if count < cap else f'Company daily limit ({cap}) reached')
