"""Company preferences shared by the Naukri and LinkedIn apply pipelines."""
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from src.naukri_agent.models.db_schema import Application, Job

# Legal and marketing suffixes that differ between a company's jobs board name
# and the name a candidate saved. They are stripped before comparison so
# "Capgemini Technology Services India Limited" still matches "Capgemini".
_COMPANY_SUFFIXES = {
    "ag",
    "bv",
    "co",
    "company",
    "corp",
    "corporation",
    "gmbh",
    "group",
    "inc",
    "incorporated",
    "india",
    "international",
    "limited",
    "llc",
    "llp",
    "ltd",
    "nv",
    "plc",
    "private",
    "pte",
    "pvt",
    "sa",
    "sas",
    "services",
    "software",
    "solutions",
    "systems",
    "tech",
    "technologies",
    "technology",
}


def _company_key(name):
    """Comparable form of a company name, without legal or marketing suffixes."""
    value = str(name or "").casefold().replace("&", " and ")
    words = re.sub(r"[^a-z0-9]+", " ", value).split()
    while words and words[-1] in _COMPANY_SUFFIXES:
        words.pop()
    return " ".join(words)


def _company_matches(company_key, preferred_key):
    """Match a listing's employer to a saved preference or blacklist entry."""
    if not company_key or not preferred_key:
        return False
    if company_key == preferred_key:
        return True
    company_tokens = set(company_key.split())
    preferred_tokens = set(preferred_key.split())
    if preferred_tokens <= company_tokens:
        return True
    company_compact = company_key.replace(" ", "")
    preferred_compact = preferred_key.replace(" ", "")
    # Long names may carry a unit or product suffix, e.g. "jpmorganchase" or
    # "capgemini engineering", and the saved preference may be the longer form.
    # Short names must match exactly so "SAP" never matches "Sapient".
    if len(preferred_compact) >= 5 and company_compact.startswith(preferred_compact):
        return True
    return len(company_compact) >= 5 and preferred_compact.startswith(company_compact)


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
        search = getattr(settings, 'search', None)
        preferred = getattr(search, 'preferred_companies', []) if search else []
        self.blacklist = {
            key
            for key in (_company_key(x) for x in self.config.get('company_blacklist', []))
            if key
        }
        self.whitelist = {
            key
            for key in (
                _company_key(x)
                for x in [*self.config.get('company_whitelist', []), *preferred]
            )
            if key
        }

    def priority(self, company):
        key = _company_key(company)
        if not key:
            return 0.0
        return 1.0 if any(_company_matches(key, preferred) for preferred in self.whitelist) else 0.0

    async def allowed(self, company, repository, platform):
        name = _company_key(company)
        if any(_company_matches(name, blocked) for blocked in self.blacklist):
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
