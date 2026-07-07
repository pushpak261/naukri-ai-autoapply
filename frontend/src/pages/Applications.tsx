import { useState, useEffect, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft, ChevronRight, ExternalLink, RefreshCw, RotateCcw, Loader2, AlertTriangle, CheckCircle } from 'lucide-react';
import StatusBadge from '../components/StatusBadge';
import { api, type ApplicationItem, type StatusInfo } from '../lib/api';

export default function Applications() {
  const [apps, setApps] = useState<ApplicationItem[]>([]);
  const [statuses, setStatuses] = useState<StatusInfo[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryingId, setRetryingId] = useState<number | null>(null);
  const [busy, setBusy] = useState<{ retryAll: boolean; sync: boolean }>({ retryAll: false, sync: false });
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const mountedRef = useRef(true);
  const perPage = 20;

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const loadApps = useCallback(async (currentPage: number, currentFilter: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.applications(currentPage, perPage, currentFilter);
      if (mountedRef.current) {
        setApps(data.items);
        setTotal(data.total);
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : 'Failed to load applications');
      }
    } finally {
      if (mountedRef.current) {
        setLoading(false);
      }
    }
  }, []);

  const loadStatuses = useCallback(async () => {
    try {
      const statusData = await api.applicationStatuses();
      if (mountedRef.current) {
        setStatuses(statusData.statuses);
      }
    } catch {
      // Statuses are static, so failure is non-critical
    }
  }, []);

  useEffect(() => {
    loadApps(page, statusFilter);
    loadStatuses();
  }, [page, statusFilter, loadApps, loadStatuses]);

  useEffect(() => { setPage(1); }, [statusFilter]);

  const handleRetry = async (appId: number) => {
    setRetryingId(appId);
    setMessage(null);
    try {
      const r = await api.applicationsExtra.retry(appId);
      setMessage({ type: 'success', text: `Retry queued for app #${r.app_id} (attempt ${r.retry_count})` });
      await loadApps(page, statusFilter);
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
      await loadApps(page, statusFilter);
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Retry all failed' });
    }
    setBusy(prev => ({ ...prev, retryAll: false }));
  };

  const handleSync = async () => {
    setBusy(prev => ({ ...prev, sync: true }));
    setMessage(null);
    try {
      await api.applicationsExtra.syncStatus();
      await loadApps(page, statusFilter);
      setMessage({ type: 'success', text: 'Applications refreshed' });
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Sync failed' });
    }
    setBusy(prev => ({ ...prev, sync: false }));
  };

  const totalPages = Math.ceil(total / perPage);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Applications</h1>
          <p className="text-[#94a3b8] mt-1">All application attempts ({total} total)</p>
        </div>
        <div className="flex gap-2">
          <button onClick={handleSync} disabled={busy.sync}
            className="flex items-center gap-1.5 px-3 py-2 bg-[#334155] hover:bg-[#475569] text-white rounded-lg text-sm transition-colors disabled:opacity-50">
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
          onClick={() => setStatusFilter('')}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            statusFilter === '' ? 'bg-[#38bdf8]/10 text-[#38bdf8] border border-[#38bdf8]/30' : 'bg-[#1e293b] text-[#94a3b8] border border-[#334155] hover:bg-[#334155]'
          }`}
        >
          All
        </button>
        {statuses.map((s) => (
          <button
            key={s.value}
            onClick={() => setStatusFilter(s.value)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              statusFilter === s.value
                ? 'bg-[#38bdf8]/10 text-[#38bdf8] border border-[#38bdf8]/30'
                : 'bg-[#1e293b] text-[#94a3b8] border border-[#334155] hover:bg-[#334155]'
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      <div className="bg-[#1e293b] rounded-xl border border-[#334155] overflow-hidden">
        {error ? (
          <div className="flex flex-col items-center justify-center h-64 gap-3">
            <AlertTriangle className="w-8 h-8 text-red-400" />
            <p className="text-red-400 text-sm">{error}</p>
            <button onClick={() => loadApps(page, statusFilter)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-[#334155] hover:bg-[#475569] text-white rounded-lg text-xs transition-colors">
              <RefreshCw className="w-3 h-3" />
              Retry
            </button>
          </div>
        ) : loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#38bdf8]" />
          </div>
        ) : apps.length === 0 ? (
          <div className="text-center py-16 text-[#64748b]">No applications found</div>
        ) : (
          <div className="divide-y divide-[#334155]">
            {apps.map((app) => (
              <div key={app.id} className="p-4 hover:bg-[#0f172a]/50 transition-colors">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <Link to={`/jobs/${app.job_id}`} className="text-sm font-semibold text-white hover:text-[#38bdf8] transition-colors">
                      {app.job_title}
                    </Link>
                    <p className="text-xs text-[#94a3b8] mt-0.5">{app.company}{app.location ? ` — ${app.location}` : ''}</p>
                    <div className="flex items-center gap-2 mt-2">
                      <span className={`text-xs font-semibold ${
                        app.match_score >= 80 ? 'text-green-400' : app.match_score >= 50 ? 'text-yellow-400' : 'text-red-400'
                      }`}>
                        Score: {app.match_score.toFixed(0)}
                      </span>
                      <StatusBadge status={app.status} />
                    </div>
                    {app.match_reasoning && (
                      <p className="text-xs text-[#64748b] mt-1.5 line-clamp-2">{app.match_reasoning}</p>
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
                    <span className="text-xs text-[#64748b]">
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
                        className="p-1.5 rounded-lg hover:bg-[#334155] transition-colors"
                      >
                        <ExternalLink className="w-4 h-4 text-[#64748b]" />
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
        <div className="flex items-center justify-between">
          <p className="text-sm text-[#64748b]">
            Showing {(page - 1) * perPage + 1}–{Math.min(page * perPage, total)} of {total}
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="p-2 rounded-lg border border-[#334155] text-[#94a3b8] hover:bg-[#334155] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="text-sm text-[#94a3b8] px-2">{page} / {totalPages}</span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="p-2 rounded-lg border border-[#334155] text-[#94a3b8] hover:bg-[#334155] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
