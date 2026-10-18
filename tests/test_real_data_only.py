"""Client views stay empty until real workspace records exist."""
# ruff: noqa: F811
from pathlib import Path

import pytest

from tests.test_dashboard_features import dashboard  # noqa: F401


def test_fictional_frontend_is_not_shipped():
    root = Path(__file__).resolve().parents[1]
    assert not (root / 'frontend/src/pages/Demo.tsx').exists()
    assert not (root / 'frontend/src/lib/demo-data.ts').exists()
    for name in ('frontend/src/components/AuthFrame.tsx', 'frontend/src/pages/Help.tsx'):
        assert 'to="/demo"' not in (root / name).read_text(encoding='utf-8')


@pytest.mark.asyncio
async def test_new_account_has_no_fabricated_market_records(dashboard):
    for endpoint in ('salary-benchmarks', 'skill-demand', 'competitor-companies'):
        data = (await dashboard.get('/api/market-intel/' + endpoint)).json()
        assert data['items'] == []
    rates = (await dashboard.get('/api/market-intel/win-rate-prediction')).json()['items']
    assert all(row['total'] == 0 and row['applied'] == 0 for row in rates)
    optimization = (await dashboard.get('/api/resume-optimization/analysis')).json()
    assert optimization['resume'] is None or optimization['resume']['exists'] is False
    assert optimization['skills_data'] == []
    assert optimization['ats']['label'] == 'N/A'


@pytest.mark.asyncio
async def test_overview_counts_saved_listings_without_run_logs(dashboard):
    from datetime import UTC, datetime
    response = await dashboard.post('/api/import/full', json={'data': {'jobs': [
        {'id': 1, 'naukri_job_id': 'test-only', 'title': 'Test listing', 'company': 'Test employer',
         'url': 'https://example.invalid/job', 'source': 'naukri', 'scraped_at': datetime.now(UTC).isoformat()}
    ]}})
    assert response.status_code == 200
    assert (await dashboard.get('/api/stats')).json()['total_jobs_found'] == 1
    assert (await dashboard.get('/api/stats?source=linkedin')).json()['total_jobs_found'] == 0
