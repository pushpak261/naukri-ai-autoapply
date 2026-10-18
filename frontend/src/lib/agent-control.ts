export function boundAgentLog(text: string): string {
  // Bound characters as well as lines, including a single enormous log line.
  return text.slice(-2_000_000).split('\n').slice(-50_000).join('\n');
}

export function summarizeAgentStart(agents: Record<string, { status: string; message?: string }>) {
  const entries = Object.entries(agents);
  const started = entries.filter(([, result]) => result.status === 'started').length;
  const running = entries.filter(([, result]) => result.status === 'already_running').length;
  const failures = entries.filter(([, result]) => !['started', 'already_running'].includes(result.status));
  return {
    type: failures.length === 0 && entries.length > 0 ? 'success' as const : 'error' as const,
    message: `${started} started, ${running} already running${failures.length ? '. ' + failures.map(([platform, result]) => `${platform}: ${result.message || result.status}`).join('; ') : ''}${entries.length ? '' : '. No platform results returned.'}`,
  };
}
