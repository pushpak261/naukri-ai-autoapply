import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  ChevronLeft, ChevronRight, ExternalLink, RefreshCw, RotateCcw, Loader2,
  AlertTriangle, CheckCircle, Search, SlidersHorizontal, X,
} from 'lucide-react';
import StatusBadge from '../components/StatusBadge';
import { useDebounce } from '../hooks/useDebounce';
import {
  api,
  type ApplicationItem,
  type ApplicationSort,
  type StatusInfo,
} from '../lib/api';
import {
  type ApplicationFilters,
  countActiveFilters,
  filterApplications,
  paginateApplications,
  sortApplications,
} from '../utils/applicationFilters';

const SORT_OPTIONS: { value: ApplicationSort; label: string }[] = [
  { value: 'newest', label: 'Newest first' },
  { value: 'oldest', label: 'Oldest first' },
  { value: 'score_desc', label: 'Highest score' },
  { value: 'score_asc', label: 'Lowest score' },
  { value: 'company_asc', label: 'Company A–Z' },
  { value: 'company_desc', label: 'Company Z–A' },
  { value: 'title_asc', label: 'Role A–Z' },
  { value: 'title_desc', label: 'Role Z–A' },
];

const SCORE_PRESETS = [
  { label: 'All scores', min: 0, max: 100 },
  { label: '80+', min: 80, max: 100 },
  { label: '50–79', min: 50, max: 79 },
  { label: 'Below 50', min: 0, max: 49 },
];

const DEFAULT_FILTERS: ApplicationFilters = {
  status: '',
  sort: 'newest',
  company: '',
  minScore: 0,
  maxScore: 100,
  dateFrom: '',
  dateTo: '',
  retryable: false,
};

const SEARCH_DEBOUNCE_MS = 300;
const PER_PAGE = 20;

export default function Applications() {
  const [allApps, setAllApps] = useState<ApplicationItem[]>([]);
  const [statuses, setStatuses] = useState<StatusInfo[]>([]);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<ApplicationFilters>(DEFAULT_FILTERS);
  const [searchInput, setSearchInput] = useState('');
  const debouncedSearch = useDebounce(searchInput, SEARCH_DEBOUNCE_MS);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryingId, setRetryingId] = useState<number | null>(null);
  const [busy, setBusy] = useState<{ retryAll: boolean; sync: boolean }>({ retryAll: false, sync: false });
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const mountedRef = useRef(true);
  const wasRunningRef = useRef(false);

  const activeFilterCount = countActiveFilters(filters, searchInput);
  const isSearchPending = searchInput !== debouncedSearch;

  const filteredApps = useMemo(() => {
    const filtered = filterApplications(allApps, filters, debouncedSearch);
    return sortApplications(filtered, filters.sort);
  }, [allApps, filters, debouncedSearch]);

  const visibleApps = useMemo(
    () => paginateApplications(filteredApps, page, PER_PAGE),
    [filteredApps, page],
  );

  const totalFiltered = filteredApps.length;
  const totalPages = Math.ceil(totalFiltered / PER_PAGE);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const loadAllApps = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const items = await api.applicationsAll();
      if (mountedRef.current) {
        setAllApps(items);
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
    loadAllApps();
    loadStatuses();
  }, [loadAllApps, loadStatuses]);

  useEffect(() => {
    setPage(1);
  }, [
    debouncedSearch,
    filters.status,
    filters.sort,
    filters.company,
    filters.minScore,
    filters.maxScore,
    filters.dateFrom,
    filters.dateTo,
    filters.retryable,
  ]);

  useEffect(() => {
    if (page > totalPages && totalPages > 0) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  useEffect(() => {
    const poll = async () => {
      try {
        const agentStatus = await api.agent.status();
        if (wasRunningRef.current && !agentStatus.running) {
          await loadAllApps();
        }
        wasRunningRef.current = agentStatus.running;
      } catch {
        // Non-critical: page still works with manual refresh.
      }
    };

    poll();
    const interval = setInterval(poll, 5000);
    return () => clearInterval(interval);
  }, [loadAllApps]);

  const updateFilter = <K extends keyof ApplicationFilters>(key: K, value: ApplicationFilters[K]) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  const clearFilters = () => {
    setFilters(DEFAULT_FILTERS);
    setSearchInput('');
  };

  const handleRetry = async (appId: number) => {
    setRetryingId(appId);
    setMessage(null);
    try {
      const r = await api.applicationsExtra.retry(appId);
      setMessage({ type: 'success', text: `Retry queued for app #${r.app_id} (attempt ${r.retry_count})` });
      await loadAllApps();
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
      await loadAllApps();
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
      await loadAllApps();
      setMessage({ type: 'success', text: 'Applications refreshed' });
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Sync failed' });
    }
    setBusy(prev => ({ ...prev, sync: false }));
  };

  const scorePreset =
    SCORE_PRESETS.find((p) => p.min === filters.minScore && p.max === filters.maxScore)?.label ?? 'Custom';

  const summaryText = activeFilterCount > 0
    ? `${totalFiltered} matching of ${allApps.length} total`
    : `${allApps.length} total`;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text">Applications</h1>
          <p className="text-secondary mt-1">All application attempts ({summaryText})</p>
        </div>
        <div className="flex gap-2">
          <button onClick={handleSync} disabled={busy.sync}
            className="flex items-center gap-1.5 px-3 py-2 bg-surface-hover hover:bg-surface-hover text-text rounded-lg text-sm transition-colors disabled:opacity-50">
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

      <div className="bg-surface rounded-xl border border-border p-4 space-y-4">
        <div className="flex flex-col lg:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
            <input
              type="text"
              placeholder="Search by job title..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className="w-full bg-bg border border-border rounded-lg pl-10 pr-10 py-2.5 text-sm text-text placeholder:text-muted focus:outline-none focus:border-primary transition-colors"
            />
            {isSearchPending && (
              <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted animate-spin" />
            )}
          </div>
          <select
            value={filters.sort}
            onChange={(e) => updateFilter('sort', e.target.value as ApplicationSort)}
            className="bg-bg border border-border rounded-lg px-4 py-2.5 text-sm text-secondary focus:outline-none focus:border-primary transition-colors"
          >
            {SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <select
            value={scorePreset}
            onChange={(e) => {
              const preset = SCORE_PRESETS.find((p) => p.label === e.target.value);
              if (preset) {
                setFilters((prev) => ({ ...prev, minScore: preset.min, maxScore: preset.max }));
              }
            }}
            className="bg-bg border border-border rounded-lg px-4 py-2.5 text-sm text-secondary focus:outline-none focus:border-primary transition-colors"
          >
            {SCORE_PRESETS.map((preset) => (
              <option key={preset.label} value={preset.label}>{preset.label}</option>
            ))}
          </select>
          <button
            onClick={() => setShowAdvanced((v) => !v)}
            className={`flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-lg text-sm border transition-colors ${
              showAdvanced || activeFilterCount > 0
                ? 'bg-primary/10 text-primary border-primary/30'
                : 'bg-bg text-secondary border-border hover:bg-surface-hover'
            }`}
          >
            <SlidersHorizontal className="w-4 h-4" />
            Filters
            {activeFilterCount > 0 && (
              <span className="px-1.5 py-0.5 text-[10px] rounded-full bg-primary/20 text-primary">
                {activeFilterCount}
              </span>
            )}
          </button>
        </div>

        {showAdvanced && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 pt-1 border-t border-border">
            <div>
              <label className="block text-xs text-muted mb-1">Company</label>
              <input
                type="text"
                placeholder="Filter by company"
                value={filters.company}
                onChange={(e) => updateFilter('company', e.target.value)}
                className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text placeholder:text-muted focus:outline-none focus:border-primary transition-colors"
              />
            </div>
            <div>
              <label className="block text-xs text-muted mb-1">From date</label>
              <input
                type="date"
                value={filters.dateFrom}
                onChange={(e) => updateFilter('dateFrom', e.target.value)}
                className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text focus:outline-none focus:border-primary transition-colors"
              />
            </div>
            <div>
              <label className="block text-xs text-muted mb-1">To date</label>
              <input
                type="date"
                value={filters.dateTo}
                onChange={(e) => updateFilter('dateTo', e.target.value)}
                className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text focus:outline-none focus:border-primary transition-colors"
              />
            </div>
            <div className="flex items-end">
              <label className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border bg-bg cursor-pointer hover:bg-surface-hover transition-colors w-full">
                <input
                  type="checkbox"
                  checked={filters.retryable}
                  onChange={(e) => updateFilter('retryable', e.target.checked)}
                  className="rounded border-border"
                />
                <span className="text-sm text-secondary">Retryable only</span>
              </label>
            </div>
          </div>
        )}

        <div className="flex gap-2 flex-wrap items-center">
          <button
            onClick={() => updateFilter('status', '')}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              filters.status === '' ? 'bg-primary/10 text-primary border border-primary/30' : 'bg-bg text-secondary border border-border hover:bg-surface-hover'
            }`}
          >
            All statuses
          </button>
          {statuses.map((s) => (
            <button
              key={s.value}
              onClick={() => updateFilter('status', s.value)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                filters.status === s.value
                  ? 'bg-primary/10 text-primary border border-primary/30'
                  : 'bg-bg text-secondary border border-border hover:bg-surface-hover'
              }`}
            >
              {s.label}
            </button>
          ))}
          {activeFilterCount > 0 && (
            <button
              onClick={clearFilters}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium text-muted border border-border hover:bg-surface-hover transition-colors ml-auto"
            >
              <X className="w-3 h-3" />
              Clear all
            </button>
          )}
        </div>
      </div>

      <div className="bg-surface rounded-xl border border-border overflow-hidden">
        {error ? (
          <div className="flex flex-col items-center justify-center h-64 gap-3">
            <AlertTriangle className="w-8 h-8 text-red-400" />
            <p className="text-red-400 text-sm">{error}</p>
            <button onClick={loadAllApps}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-surface-hover hover:bg-surface-hover text-text rounded-lg text-xs transition-colors">
              <RefreshCw className="w-3 h-3" />
              Retry
            </button>
          </div>
        ) : loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
          </div>
        ) : visibleApps.length === 0 ? (
          <div className="text-center py-16 text-muted">
            {activeFilterCount > 0 ? 'No applications match your filters' : 'No applications found'}
          </div>
        ) : (
          <div className="divide-y divide-[#334155]">
            {visibleApps.map((app) => (
              <div key={app.id} className="p-4 hover:bg-bg/50 transition-colors">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <Link to={`/jobs/${app.job_id}`} className="text-sm font-semibold text-text hover:text-primary transition-colors">
                      {app.job_title}
                    </Link>
                    <p className="text-xs text-secondary mt-0.5">{app.company}{app.location ? ` — ${app.location}` : ''}</p>
                    <div className="flex items-center gap-2 mt-2 flex-wrap">
                      <span className={`text-xs font-semibold ${
                        app.match_score >= 80 ? 'text-green-400' : app.match_score >= 50 ? 'text-yellow-400' : 'text-red-400'
                      }`}>
                        Score: {app.match_score.toFixed(0)}
                      </span>
                      <StatusBadge status={app.status} />
                      {app.retryable && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-yellow-500/10 text-yellow-400">
                          Retryable
                        </span>
                      )}
                    </div>
                    {app.match_reasoning && (
                      <p className="text-xs text-muted mt-1.5 line-clamp-2">{app.match_reasoning}</p>
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
                    <span className="text-xs text-muted">
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
                        className="p-1.5 rounded-lg hover:bg-surface-hover transition-colors"
                      >
                        <ExternalLink className="w-4 h-4 text-muted" />
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
          <p className="text-sm text-muted">
            Showing {(page - 1) * PER_PAGE + 1}–{Math.min(page * PER_PAGE, totalFiltered)} of {totalFiltered}
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="p-2 rounded-lg border border-border text-secondary hover:bg-surface-hover disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="text-sm text-secondary px-2">{page} / {totalPages}</span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="p-2 rounded-lg border border-border text-secondary hover:bg-surface-hover disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
