import { useQuery } from '@tanstack/react-query';
import { Clock, Play, CheckCircle, AlertTriangle } from 'lucide-react';
import StatusBadge from '../components/StatusBadge';
import { api } from '../lib/api';

export default function RunLogs() {
  const result = useQuery({ queryKey: ['run-logs', 50], queryFn: () => api.runLogs(50) });
  const logs = result.data?.items ?? [];
  const loading = result.isPending;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--color-text)]">Run Logs</h1>
        <p className="text-[var(--color-text-secondary)] mt-1">History of all agent execution runs</p>
      </div>

      <div className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] overflow-hidden">
        {result.isError ? <div role="alert" className="notice-error"><p>{result.error.message}</p><button className="secondary-button" onClick={() => result.refetch()}>Retry run history</button></div> : loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[var(--color-primary)]" />
          </div>
        ) : logs.length === 0 ? (
          <div className="text-center py-16 text-[var(--color-text-muted)]">No runs recorded yet</div>
        ) : (
          <div className="divide-y divide-[#334155]">
            {logs.map((log) => (
              <div key={log.id} className="p-5 hover:bg-[var(--color-bg)]/50 transition-colors">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      {log.status === 'running' ? (
                        <Play className="w-4 h-4 text-blue-400" />
                      ) : log.status === 'completed' ? (
                        <CheckCircle className="w-4 h-4 text-green-400" />
                      ) : (
                        <AlertTriangle className="w-4 h-4 text-yellow-400" />
                      )}
                      <span className="text-sm font-medium text-[var(--color-text)]">
                        Run #{log.id}
                      </span>
                      <StatusBadge status={log.status} />
                    </div>
                    <p className="text-xs text-[var(--color-text-secondary)] mt-1">
                      <Clock className="w-3 h-3 inline mr-1" />
                      {log.started_at.slice(0, 19).replace('T', ' ')}
                      {log.ended_at ? ` — ${log.ended_at.slice(0, 19).replace('T', ' ')}` : ''}
                    </p>
                    <p className="text-xs text-[var(--color-text-muted)] mt-1">
                      Keywords: {log.keywords}
                    </p>
                  </div>
                  <div className="grid grid-cols-3 gap-4 text-center sm:shrink-0">
                    <div>
                      <p className="text-lg font-bold text-[var(--color-primary)]">{log.found}</p>
                      <p className="text-[10px] text-[var(--color-text-muted)]">Found</p>
                    </div>
                    <div>
                      <p className="text-lg font-bold text-green-400">{log.applied}</p>
                      <p className="text-[10px] text-[var(--color-text-muted)]">Applied</p>
                    </div>
                    <div>
                      <p className="text-lg font-bold text-yellow-400">{log.skipped}</p>
                      <p className="text-[10px] text-[var(--color-text-muted)]">Skipped</p>
                    </div>
                  </div>
                </div>
                <div className="flex gap-4 mt-3 text-xs text-[var(--color-text-muted)]">
                  <span>Failed: {log.failed}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
