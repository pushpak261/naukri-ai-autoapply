import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft, ChevronRight, ExternalLink } from 'lucide-react';
import StatusBadge from '../components/StatusBadge';
import { api, type ApplicationItem, type StatusInfo } from '../lib/api';

export default function Applications() {
  const [apps, setApps] = useState<ApplicationItem[]>([]);
  const [statuses, setStatuses] = useState<StatusInfo[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const perPage = 20;

  const fetch = useCallback(async () => {
    setLoading(true);
    try {
      const [data, statusData] = await Promise.all([
        api.applications(page, perPage, statusFilter),
        api.applicationStatuses(),
      ]);
      setApps(data.items);
      setTotal(data.total);
      setStatuses(statusData.statuses);
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => { fetch(); }, [fetch]);
  useEffect(() => { setPage(1); }, [statusFilter]);

  const totalPages = Math.ceil(total / perPage);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Applications</h1>
        <p className="text-[#94a3b8] mt-1">All application attempts ({total} total)</p>
      </div>

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
        {loading ? (
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
