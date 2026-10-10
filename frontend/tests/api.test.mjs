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
