function historyKey(email: string): string {
  return `resume_versions:${encodeURIComponent(email.trim().toLowerCase())}`;
}

export function loadResumeHistory<T>(email: string | undefined): T[] {
  if (!email) return [];
  try {
    // The old shared key cannot be safely attributed to an account. Never load it.
    const value: unknown = JSON.parse(localStorage.getItem(historyKey(email)) || '[]');
    if (!Array.isArray(value)) return [];
    return value.filter(item => item && typeof item.id === 'number' &&
      typeof item.label === 'string' && typeof item.timestamp === 'string' &&
      item.profile && typeof item.profile === 'object' && !Array.isArray(item.profile)) as T[];
  } catch { return []; }
}

export function saveResumeHistory<T>(email: string | undefined, versions: T[]): boolean {
  if (!email) return false;
  try {
    localStorage.setItem(historyKey(email), JSON.stringify(versions));
    return true;
  } catch { return false; }
}
