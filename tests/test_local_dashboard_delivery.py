"""Local dashboard updates retire obsolete offline shells without API caching."""
import httpx
import pytest

from api.local import LocalDashboard


@pytest.mark.asyncio
async def test_local_worker_migration_is_network_only_and_keeps_api_routes(tmp_path):
    from starlette.responses import JSONResponse
    (tmp_path / 'index.html').write_text('<html>Current dashboard</html>')
    async def api(scope, receive, send):
        await JSONResponse({'status': 'ok'})(scope, receive, send)
    app = LocalDashboard(api, tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost') as client:
        worker = await client.get('/sw.js')
        assert worker.status_code == 200
        assert 'application/javascript' in worker.headers['content-type']
        assert worker.headers['cache-control'] == 'no-store'
        assert 'self.registration.unregister()' in worker.text
        assert 'workbox-' in worker.text
        assert (await client.get('/agent-control')).text == '<html>Current dashboard</html>'
        assert (await client.get('/agent-control')).headers['cache-control'] == 'no-store'
        assert (await client.get('/api/health')).json() == {'status': 'ok'}
