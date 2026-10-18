import { useEffect, useState } from 'react';

import { API_BASE_URL } from '../lib/api-base';
const HEALTH_URL = `${API_BASE_URL}/health`;

/**
 * Surfaces a clear, app-wide banner when the backend API cannot be reached.
 *
 * Previously a disabled/unreachable backend produced a cryptic CORS +
 * 504 error in the console and silently bounced users to the login screen.
 * This pings /api/health on load and, if it fails, tells the user exactly
 * which backend URL is unreachable so the deployment issue is obvious.
 */
export function BackendBanner() {
  const [down, setDown] = useState(false);

  useEffect(() => {
    let active = true;
    let ctrl: AbortController | null = null;
    let retry: ReturnType<typeof setTimeout>;
    const check = async () => {
      ctrl = new AbortController();
      const timeout = setTimeout(() => ctrl?.abort(), 15000);
      try {
        const res = await fetch(HEALTH_URL, { signal: ctrl.signal, cache: 'no-store' });
        const health = res.ok ? await res.json().catch(() => null) : null;
        if (active) setDown(!health || !['ok', 'healthy'].includes(health.status));
      } catch {
        if (active) setDown(true);
      } finally {
        clearTimeout(timeout);
        if (active) retry = setTimeout(check, 10000);
      }
    };
    void check();
    return () => { active = false; clearTimeout(retry); ctrl?.abort(); };
  }, []);

  if (!down) return null;

  return (
    <div
      role="alert"
      className="fixed inset-x-0 top-0 z-[100] bg-red-600 px-4 py-2 text-center text-sm font-medium text-white shadow-lg"
    >
      The application backend is unavailable. Reconnecting automatically. For local use, keep start-local.cmd running.
    </div>
  );
}

