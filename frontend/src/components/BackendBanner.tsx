import { useEffect, useState } from 'react';

const rawBase = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '');
const HEALTH_URL = rawBase ? `${rawBase}/api/health` : '/api/health';

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
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 5000);
    fetch(HEALTH_URL, { signal: ctrl.signal, cache: 'no-store' })
      .then((res) => {
        if (active) setDown(!res.ok);
      })
      .catch(() => {
        if (active) setDown(true);
      })
      .finally(() => clearTimeout(timer));
    return () => {
      active = false;
      clearTimeout(timer);
      ctrl.abort();
    };
  }, []);

  if (!down) return null;

  return (
    <div
      role="alert"
      className="fixed inset-x-0 top-0 z-[100] bg-red-600 px-4 py-2 text-center text-sm font-medium text-white shadow-lg"
    >
      Backend API unreachable{rawBase ? ` at ${rawBase}` : ' (same-origin /api)'}. The
      dashboard cannot load data — make sure the backend is running and that its CORS
      policy allows this origin.
    </div>
  );
}
