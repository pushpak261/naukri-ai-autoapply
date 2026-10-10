/** Accept either a backend origin or its /api endpoint. */
export function normalizeApiBase(value: string): string {
  const base = value.trim().replace(/\/+$/, '');
  return !base ? '/api' : base.endsWith('/api') ? base : `${base}/api`;
}

export const API_BASE_URL = normalizeApiBase(import.meta.env.VITE_API_BASE_URL || '');
