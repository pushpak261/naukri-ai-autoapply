import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile, writeFile, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

// Exercise the actual browser API module with a mocked deployment environment.
const dir = await mkdtemp(join(tmpdir(), 'naukri-api-test-'));
globalThis.__testEnv = { VITE_API_BASE_URL: 'https://backend.example/api/' };
const saved = new Map();
globalThis.window = {};
globalThis.localStorage = {
  getItem: (key) => saved.get(key) ?? null,
  setItem: (key, value) => saved.set(key, value),
  removeItem: (key) => saved.delete(key),
};
const baseSource = await readFile(new URL('../src/lib/api-base.ts', import.meta.url), 'utf8');
await writeFile(join(dir, 'api-base.ts'), baseSource.replaceAll('import.meta.env', 'globalThis.__testEnv'));
const source = await readFile(new URL('../src/lib/api.ts', import.meta.url), 'utf8');
await writeFile(join(dir, 'api.ts'), source.replace("'./api-base'", "'./api-base.ts'").replaceAll('import.meta.env', 'globalThis.__testEnv'));
const { api, setAuthToken, getAuthToken, downloadExport } = await import(pathToFileURL(join(dir, 'api.ts')));
const { normalizeApiBase } = await import(pathToFileURL(join(dir, 'api-base.ts')));
const json = (body, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json' },
});

test('parallel starts report partial and total failures honestly', async () => {
  const { summarizeAgentStart } = await import('../src/lib/agent-control.ts');
  const partial = summarizeAgentStart({ naukri: { status: 'started' }, linkedin: { status: 'busy', message: 'Capacity busy' } });
  assert.equal(partial.type, 'error');
  assert.match(partial.message, /1 started.*linkedin: Capacity busy/);
  assert.equal(summarizeAgentStart({ naukri: { status: 'already_running' } }).type, 'success');
  assert.equal(summarizeAgentStart({}).type, 'error');
  assert.equal(summarizeAgentStart({ naukri: { status: 'configuration_required' } }).type, 'error');
});

test('agent logs bound both giant lines and very long histories', async () => {
  const { boundAgentLog } = await import('../src/lib/agent-control.ts');
  assert.equal(boundAgentLog('x'.repeat(3_000_000)).length, 2_000_000);
  const history = Array.from({ length: 60_000 }, (_, index) => `line ${index}`).join('\n');
  const bounded = boundAgentLog(history);
  assert.equal(bounded.split('\n').length, 50_000);
  assert.ok(bounded.endsWith('line 59999'));
});

test('normalizes empty, origin, and /api deployment URLs', () => {
  assert.equal(normalizeApiBase(''), '/api');
  assert.equal(normalizeApiBase(' https://backend.example/// '), 'https://backend.example/api');
  assert.equal(normalizeApiBase('https://backend.example/api/'), 'https://backend.example/api');
});

test('concurrent expired requests share refresh and persist the new token', async () => {
  setAuthToken('expired');
  let refreshes = 0;
  globalThis.fetch = async (url, options) => {
    assert.ok(!url.includes('/api/api'));
    if (url.endsWith('/auth/refresh')) {
      refreshes++;
      await new Promise((resolve) => setTimeout(resolve, 20));
      return json({ access_token: 'renewed' });
    }
    return options.headers.Authorization === 'Bearer renewed' ? json({ items: [], total: 0 }) : json({ detail: 'Expired' }, 401);
  };
  await Promise.all([api.jobs(), api.applications()]);
  assert.equal(refreshes, 1);
  assert.equal(getAuthToken(), 'renewed');
  assert.equal(saved.get('naukri_access_token'), 'renewed');
});

test('failed renewal removes the persisted token and surfaces the API error', async () => {
  setAuthToken('expired');
  globalThis.fetch = async (url) => json({ detail: url.endsWith('/auth/refresh') ? 'No session' : 'Unauthorized' }, 401);
  await assert.rejects(api.jobs(), /Unauthorized/);
  assert.equal(saved.has('naukri_access_token'), false);
  assert.equal(getAuthToken(), null);
});

test('login reports server rejection without trying to refresh', async () => {
  globalThis.fetch = async (url) => {
    assert.ok(url.endsWith('/api/auth/login'));
    return json({ detail: 'Invalid email or password' }, 401);
  };
  await assert.rejects(api.auth.login('a@example.com', 'wrong'), /Invalid email or password/);
});

test('temporary renewal failures preserve the session for a later retry', async () => {
  for (const unavailable of [() => json({ detail: 'Try again later' }, 503), () => { throw new TypeError('Network unavailable'); }]) {
    setAuthToken('expired-but-recoverable');
    globalThis.fetch = async (url) => url.endsWith('/auth/refresh') ? unavailable() : json({ detail: 'Expired' }, 401);
    await assert.rejects(api.jobs(), /Try again later|Network unavailable/);
    assert.equal(getAuthToken(), 'expired-but-recoverable');
    assert.equal(saved.get('naukri_access_token'), 'expired-but-recoverable');
  }
});

test('exports attach authorization and never download error responses', async () => {
  setAuthToken('valid');
  let downloads = 0;
  globalThis.document = {
    body: { appendChild() {} },
    createElement: () => ({ click: () => downloads++, remove() {} }),
  };
  globalThis.fetch = async (url, options) => {
    assert.equal(url, 'https://backend.example/api/export/full');
    assert.equal(options.headers.Authorization, 'Bearer valid');
    return json({ detail: 'Backend unavailable' }, 503);
  };
  await assert.rejects(downloadExport('/export/full', 'export.json'), /Backend unavailable/);
  assert.equal(downloads, 0);
  globalThis.fetch = async () => json({ jobs: [] });
  await downloadExport('/export/full', 'export.json');
  assert.equal(downloads, 1);
});

test.after(async () => { await rm(dir, { recursive: true, force: true }); });


test('account switches discard cached data and cancel outstanding reads', async () => {
  const { queryClient, clearAccountCache } = await import('../src/lib/query-client.ts');
  queryClient.setQueryData(['autopilot'], { privateCompany: 'First user only' });
  let complete;
  const pending = queryClient.fetchQuery({ queryKey: ['resume'], queryFn: () => new Promise(resolve => { complete = resolve; }) }).catch(() => undefined);
  await clearAccountCache();
  complete({ name: 'Previous account' });
  await pending;
  assert.equal(queryClient.getQueryData(['autopilot']), undefined);
  assert.equal(queryClient.getQueryData(['resume']), undefined);
  assert.equal(queryClient.getQueryCache().getAll().length, 0);
});

test('a refresh completing after logout cannot resurrect authentication', async () => {
  setAuthToken('expired');
  let finish;
  let started;
  const refreshing = new Promise(resolve => { started = resolve; });
  globalThis.fetch = async (url) => {
    if (url.endsWith('/auth/refresh')) {
      started();
      return new Promise(resolve => { finish = resolve; });
    }
    return json({ detail: 'Expired' }, 401);
  };
  const pending = api.jobs();
  await refreshing;
  setAuthToken(null);
  finish(json({ access_token: 'must-not-be-restored' }));
  await assert.rejects(pending, /session changed/);
  assert.equal(getAuthToken(), null);
  assert.equal(saved.get('naukri_access_token'), undefined);
});

test('late 401 uses an already renewed token instead of rotating the cookie twice', async () => {
  setAuthToken('expired');
  let release;
  let refreshes = 0;
  globalThis.fetch = async (url, options) => {
    if (url.endsWith('/auth/refresh')) {
      refreshes++;
      return json({ access_token: 'renewed' });
    }
    if (options.headers.Authorization === 'Bearer renewed') return json({ items: [] });
    if (url.includes('/applications?')) return new Promise(resolve => { release = resolve; });
    return json({ detail: 'Expired' }, 401);
  };
  const slow = api.applications();
  await api.jobs();
  release(json({ detail: 'Expired' }, 401));
  await slow;
  assert.equal(refreshes, 1);
});

test('changing account cannot retry an old request using the new account token', async () => {
  setAuthToken('account-a');
  let finish;
  globalThis.fetch = () => new Promise(resolve => { finish = resolve; });
  const pending = api.jobs();
  setAuthToken('account-b');
  finish(json({ detail: 'Unauthorized' }, 401));
  await assert.rejects(pending, /session changed/);
  assert.equal(getAuthToken(), 'account-b');
});

test('validation errors show field messages rather than object strings', async () => {
  setAuthToken('valid');
  globalThis.fetch = async () => json({ detail: [{ loc: ['body', 'daily_cap'], msg: 'Must be positive' }] }, 422);
  await assert.rejects(api.updateConfig({ daily_cap: -1 }), error =>
    error.status === 422 && error.message === 'daily_cap: Must be positive');
});

test('public health checks do not attempt session renewal', async () => {
  setAuthToken(null);
  globalThis.fetch = async url => {
    assert.ok(url.endsWith('/health'));
    return json({ status: 'ok' });
  };
  assert.equal((await api.health()).status, 'ok');
});

test('resume history is scoped by account and ignores unattributable legacy data', async () => {
  const { loadResumeHistory, saveResumeHistory } = await import('../src/lib/resume-history.ts');
  const snapshot = { id: 1, label: 'v1', timestamp: '2026-10-17', profile: { name: 'Private sample' } };
  saved.set('resume_versions', JSON.stringify([snapshot]));
  assert.deepEqual(loadResumeHistory('b@example.com'), []);
  assert.equal(saveResumeHistory('A@example.com', [snapshot]), true);
  assert.deepEqual(loadResumeHistory('a@example.com'), [snapshot]);
  assert.deepEqual(loadResumeHistory('b@example.com'), []);
  saved.set('resume_versions:b%40example.com', '{"unexpected":"object"}');
  assert.deepEqual(loadResumeHistory('b@example.com'), []);
});

let authStore;
async function loadAuthStore() {
  if (authStore) return authStore;
  const storeSource = await readFile(new URL('../src/lib/store.ts', import.meta.url), 'utf8');
  await writeFile(join(dir, 'store.ts'), storeSource
    .replace("'@reduxjs/toolkit'", JSON.stringify(import.meta.resolve('@reduxjs/toolkit')))
    .replace("'react-redux'", JSON.stringify(import.meta.resolve('react-redux')))
    .replace("'./api'", "'./api.ts'")
    .replace("'./query-client'", JSON.stringify(new URL('../src/lib/query-client.ts', import.meta.url).href)));
  authStore = await import(pathToFileURL(join(dir, 'store.ts')));
  return authStore;
}

test('a delayed initial session restore cannot sign a user back in after logout', async () => {
  const { store, restoreSession, logoutThunk, setUser } = await loadAuthStore();
  setAuthToken('valid');
  store.dispatch(setUser({ email: 'a@example.com', naukriConfigured: false }));
  let finish;
  globalThis.fetch = async url => url.endsWith('/auth/me')
    ? new Promise(resolve => { finish = resolve; }) : json({ status: 'logged_out' });
  const pending = store.dispatch(restoreSession());
  await store.dispatch(logoutThunk());
  finish(json({ email: 'a@example.com', naukri_configured: false }));
  await pending;
  assert.equal(store.getState().auth.user, null);
  assert.equal(getAuthToken(), null);
  assert.equal(saved.get('naukri_auth_user'), undefined);
});

test('a delayed login response cannot undo logout', async () => {
  const { store, loginThunk, logoutThunk } = await loadAuthStore();
  let started;
  let finish;
  const inFlight = new Promise(resolve => { started = resolve; });
  globalThis.fetch = async url => {
    if (url.endsWith('/auth/login')) {
      started();
      return new Promise(resolve => { finish = resolve; });
    }
    assert.ok(url.endsWith('/auth/logout'));
    return json({ status: 'logged_out' });
  };
  const pending = store.dispatch(loginThunk({ email: 'a@example.com', password: 'example' }));
  await inFlight;
  await store.dispatch(logoutThunk());
  finish(json({ access_token: 'must-not-be-restored' }));
  await pending;
  assert.equal(store.getState().auth.user, null);
  assert.equal(getAuthToken(), null);
});

test('a transient connection failure during restoration does not erase a saved session', async () => {
  const { store, restoreSession, setUser } = await loadAuthStore();
  const user = { email: 'a@example.com', naukriConfigured: false };
  store.dispatch(setUser(user));
  setAuthToken('still-valid');
  globalThis.fetch = async () => { throw new TypeError('Offline'); };
  await store.dispatch(restoreSession());
  assert.deepEqual(store.getState().auth.user, user);
  assert.equal(store.getState().auth.loading, false);
  assert.equal(getAuthToken(), 'still-valid');
});


test('authentication forms preserve errors serialized by Redux unwrap', async () => {
  const { authErrorMessage } = await import('../src/lib/auth-error.ts');
  assert.equal(authErrorMessage({ name: 'APIError', message: 'Invalid email or password' }, 'Login failed'), 'Invalid email or password');
  assert.equal(authErrorMessage({ name: 'APIError', message: 'Too many attempts. Try again shortly.' }, 'Login failed'), 'Too many attempts. Try again shortly.');
  assert.equal(authErrorMessage(new Error('Network unavailable'), 'Login failed'), 'Network unavailable');
  assert.match(authErrorMessage({ name: 'TimeoutError', message: 'aborted' }, 'Login failed'), /took too long/);
  assert.equal(authErrorMessage(null, 'Login failed'), 'Login failed');
  assert.equal(authErrorMessage({ message: '' }, 'Registration failed'), 'Registration failed');
});


test('rejected sign-in exposes the backend message after real thunk serialization', async () => {
  const { store, loginThunk } = await loadAuthStore();
  const { authErrorMessage } = await import('../src/lib/auth-error.ts');
  globalThis.fetch = async url => {
    assert.ok(url.endsWith('/auth/login'));
    return json({ detail: 'Invalid email or password' }, 401);
  };
  await assert.rejects(
    store.dispatch(loginThunk({ email: 'a@example.com', password: 'incorrect' })).unwrap(),
    error => !(error instanceof Error) && authErrorMessage(error, 'Login failed') === 'Invalid email or password',
  );
  assert.equal(store.getState().auth.user, null);
  assert.equal(store.getState().auth.loading, false);
  assert.equal(getAuthToken(), null);
});

test('answer memory uses authenticated search, correction and forget without queuing applications', async () => {
  setAuthToken('memory-session');
  const requests = [];
  globalThis.fetch = async (url, options) => {
    requests.push({url, options});
    assert.equal(options.headers.Authorization, 'Bearer memory-session');
    return json({items: [], total: 0, forgotten: true, saved: 1, queued: 0});
  };
  await api.screening.memory('C++ & years');
  assert.ok(requests[0].url.endsWith('/screening/memory?search=C%2B%2B%20%26%20years'));
  await api.screening.save({saved: 'Corrected answer'});
  assert.deepEqual(JSON.parse(requests[1].options.body), {answers: {saved: 'Corrected answer'}, queue_jobs: false});
  await api.screening.forget('saved');
  assert.equal(requests[2].options.method, 'DELETE');
  assert.ok(requests[2].url.endsWith('/screening/memory/saved'));
});

test('a 100-application run is an explicit start option', async () => {
  const requests = [];
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options });
    return json({ status: 'started' });
  };
  await api.agent.start('naukri', 100);
  await api.agent.start('naukri');
  assert.ok(requests[0].url.endsWith('/agent/start?platform=naukri&target=100'));
  assert.ok(requests[1].url.endsWith('/agent/start?platform=naukri'));
  assert.equal(requests[0].options.method, 'POST');
});
