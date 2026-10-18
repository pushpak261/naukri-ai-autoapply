import { useState, useEffect, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ChevronLeft, ChevronRight, ExternalLink, RefreshCw, RotateCcw, Loader2, AlertTriangle, CheckCircle } from 'lucide-react';
import StatusBadge from '../components/StatusBadge';
import { api } from '../lib/api';

export default function Applications() {
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [retryingId, setRetryingId] = useState<number | null>(null);
  const [busy, setBusy] = useState<{ retryAll: boolean; sync: boolean }>({ retryAll: false, sync: false });
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const mountedRef = useRef(true);
  const perPage = 20;
  const queryClient = useQueryClient();
  const result = useQuery({
    queryKey: ['applications', page, statusFilter, sourceFilter],
    queryFn: () => api.applications(page, perPage, statusFilter, 'newest', sourceFilter),
  });
  const statusResult = useQuery({ queryKey: ['application-statuses'], queryFn: api.applicationStatuses });
  const apps = result.data?.items ?? [];
  const total = result.data?.total ?? 0;
  const statuses = statusResult.data?.statuses ?? [];
  const loading = result.isPending;
  const error = result.error?.message;
  const loadApps = async () => {
    await queryClient.invalidateQueries({ queryKey: ['applications'] });
    await queryClient.invalidateQueries({ queryKey: ['stats'] });
  };

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const handleRetry = async (appId: number) => {
    setRetryingId(appId);
    setMessage(null);
    try {
      const r = await api.applicationsExtra.retry(appId);
      setMessage({ type: 'success', text: `Retry queued for app #${r.app_id} (attempt ${r.retry_count})` });
      await loadApps();
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Retry failed' });
    }
    setRetryingId(null);
  };

  const handleRetryAll = async () => {
    if (!confirm('Retry all failed applications?')) return;
    setBusy(prev => ({ ...prev, retryAll: true }));
    setMessage(null);
    try {
      const r = await api.applicationsExtra.retryAllFailed();
      setMessage({ type: 'success', text: `Retrying ${r.count} failed applications` });
      await loadApps();
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Retry all failed' });
    }
    setBusy(prev => ({ ...prev, retryAll: false }));
  };

  const handleSync = async () => {
    setBusy(prev => ({ ...prev, sync: true }));
    setMessage(null);
    try {
      const result = await api.applicationsExtra.syncStatus();
      setMessage({ type: 'success', text: result.message });
      let finished = false;
      while (mountedRef.current && !finished) {
        await new Promise(resolve => setTimeout(resolve, 2000));
        if (!mountedRef.current) return;
        const progress = await api.applicationsExtra.getSyncStatus();
        finished = !progress.running;
        setMessage({ type: progress.error ? 'error' : 'success', text: progress.error || progress.message || 'Checking applications…' });
      }
      await loadApps();
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Sync failed' });
    }
    setBusy(prev => ({ ...prev, sync: false }));
  };

  const totalPages = Math.ceil(total / perPage);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[var(--color-text)]">Applications</h1>
          <p className="text-[var(--color-text-secondary)] mt-1">All application attempts ({total} total)</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={handleSync} disabled={busy.sync}
            className="flex items-center gap-1.5 px-3 py-2 bg-[var(--color-surface-hover)] hover:bg-[var(--color-border)] text-[var(--color-text)] rounded-lg text-sm transition-colors disabled:opacity-50">
            {busy.sync ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            Sync Status
          </button>
          <button onClick={handleRetryAll} disabled={busy.retryAll}
            className="flex items-center gap-1.5 px-3 py-2 bg-yellow-500/10 text-yellow-400 hover:bg-yellow-500/20 rounded-lg text-sm transition-colors disabled:opacity-50">
            {busy.retryAll ? <Loader2 className="w-4 h-4 animate-spin" /> : <RotateCcw className="w-4 h-4" />}
            Retry All Failed
          </button>
        </div>
      </div>

      {message && (
        <div className={`flex items-center gap-2 p-3 rounded-lg text-sm ${
          message.type === 'success' ? 'bg-green-500/10 text-green-400 border border-green-500/30' : 'bg-red-500/10 text-red-400 border border-red-500/30'
        }`}>
          {message.type === 'success' ? <CheckCircle className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
          {message.text}
        </div>
      )}

      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => { setPage(1); setStatusFilter(''); }}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            statusFilter === '' ? 'bg-[#38bdf8]/10 text-[var(--color-primary)] border border-[var(--color-primary)]/30' : 'bg-[var(--color-surface)] text-[var(--color-text-secondary)] border border-[var(--color-border)] hover:bg-[var(--color-surface-hover)]'
          }`}
        >
          All
        </button>
        {statuses.map((s) => (
          <button
            key={s.value}
            onClick={() => { setPage(1); setStatusFilter(s.value); }}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              statusFilter === s.value
                ? 'bg-[#38bdf8]/10 text-[var(--color-primary)] border border-[var(--color-primary)]/30'
                : 'bg-[var(--color-surface)] text-[var(--color-text-secondary)] border border-[var(--color-border)] hover:bg-[var(--color-surface-hover)]'
            }`}
          >
            {s.label}
          </button>
        ))}
        <span className="self-center text-[var(--color-text-muted)] text-xs mx-1">|</span>
        <button
          onClick={() => setSourceFilter('')}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            sourceFilter === '' ? 'bg-[#38bdf8]/10 text-[var(--color-primary)] border border-[var(--color-primary)]/30' : 'bg-[var(--color-surface)] text-[var(--color-text-secondary)] border border-[var(--color-border)] hover:bg-[var(--color-surface-hover)]'
          }`}
        >
          All Platforms
        </button>
        <button
          onClick={() => setSourceFilter('naukri')}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            sourceFilter === 'naukri'
              ? 'bg-[#38bdf8]/10 text-[var(--color-primary)] border border-[var(--color-primary)]/30'
              : 'bg-[var(--color-surface)] text-[var(--color-text-secondary)] border border-[var(--color-border)] hover:bg-[var(--color-surface-hover)]'
          }`}
        >
          Naukri
        </button>
        <button
          onClick={() => setSourceFilter('linkedin')}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            sourceFilter === 'linkedin'
              ? 'bg-[#0077b5]/10 text-[#0077b5] border border-[#0077b5]/30'
              : 'bg-[var(--color-surface)] text-[var(--color-text-secondary)] border border-[var(--color-border)] hover:bg-[var(--color-surface-hover)]'
          }`}
        >
          LinkedIn
        </button>
      </div>

      <div className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] overflow-hidden">
        {error ? (
          <div className="flex flex-col items-center justify-center h-64 gap-3">
            <AlertTriangle className="w-8 h-8 text-red-400" />
            <p className="text-red-400 text-sm">{error}</p>
            <button onClick={() => loadApps()}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-[var(--color-surface-hover)] hover:bg-[var(--color-border)] text-[var(--color-text)] rounded-lg text-xs transition-colors">
              <RefreshCw className="w-3 h-3" />
              Retry
            </button>
          </div>
        ) : loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[var(--color-primary)]" />
          </div>
        ) : apps.length === 0 ? (
          <div className="text-center py-16 text-[var(--color-text-muted)]">No applications found</div>
        ) : (
          <div className="divide-y divide-[#334155]">
            {apps.map((app) => (
              <div key={app.id} className="p-4 hover:bg-[var(--color-bg)]/50 transition-colors">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <Link to={`/jobs/${app.job_id}`} className="block truncate text-sm font-semibold text-[var(--color-text)] hover:text-[var(--color-primary)] transition-colors">
                       {app.job_title}
                     </Link>
                    <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">{app.company}{app.location ? ` — ${app.location}` : ''}</p>
                    <div className="flex items-center gap-2 mt-2">
                      <span className={`text-xs font-semibold ${
                        app.match_score >= 80 ? 'text-green-400' : app.match_score >= 50 ? 'text-yellow-400' : 'text-red-400'
                      }`}>
                        Score: {app.match_score.toFixed(0)}
                      </span>
                      <StatusBadge status={app.status} />
                      {app.source && (
                        <span className={`px-2 py-0.5 text-[10px] rounded-full font-medium ${
                          app.source === 'linkedin'
                            ? 'bg-[#0077b5]/10 text-[#0077b5] border border-[#0077b5]/20'
                            : 'bg-[#38bdf8]/10 text-[var(--color-primary)] border border-[var(--color-primary)]/20'
                        }`}>
                          {app.source === 'linkedin' ? 'LinkedIn' : 'Naukri'}
                        </span>
                      )}
                    </div>
                    {app.match_reasoning && (
                      <p className="text-xs text-[var(--color-text-muted)] mt-1.5 line-clamp-2">{app.match_reasoning}</p>
                    )}
                    {app.matching_skills && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {app.matching_skills.split(',').slice(0, 4).map((s) => (
                          <span key={s} className="px-1.5 py-0.5 text-[10px] bg-green-500/10 text-green-400 rounded-full">
                            {s.trim()}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col items-end gap-2 shrink-0">
                    <span className="text-xs text-[var(--color-text-muted)]">
                      {app.applied_at.slice(0, 10)}
                    </span>
                    <div className="flex items-center gap-1">
                      {app.status === 'failed' && (
                        <button
                          onClick={() => handleRetry(app.id)}
                          disabled={retryingId === app.id}
                          className="p-1.5 rounded-lg hover:bg-yellow-500/10 text-yellow-400 transition-colors disabled:opacity-50"
                          title="Retry"
                        >
                          {retryingId === app.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
                        </button>
                      )}
                      <a
                        href={app.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="p-1.5 rounded-lg hover:bg-[var(--color-surface-hover)] transition-colors"
                      >
                        <ExternalLink className="w-4 h-4 text-[var(--color-text-muted)]" />
                      </a>
                    </div>
                  </div>
                </div>
                {app.error_message && (
                  <div className="mt-2 p-2 bg-red-500/10 border border-red-500/30 rounded text-xs text-red-300">
                    {app.error_message}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {totalPages > 1 && (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-[var(--color-text-muted)]">
            Showing {(page - 1) * perPage + 1}–{Math.min(page * perPage, total)} of {total}
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="p-2 rounded-lg border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="text-sm text-[var(--color-text-secondary)] px-2">{page} / {totalPages}</span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="p-2 rounded-lg border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
