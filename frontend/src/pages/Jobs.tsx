import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Search, ExternalLink, Building2, MapPin, DollarSign, ChevronLeft, ChevronRight } from 'lucide-react';
import StatusBadge from '../components/StatusBadge';
import { api, type JobItem } from '../lib/api';

export default function Jobs() {
  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const perPage = 20;

  const fetchJobs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.jobs(page, perPage, search, statusFilter);
      setJobs(data.items);
      setTotal(data.total);
    } finally {
      setLoading(false);
    }
  }, [page, search, statusFilter]);

  useEffect(() => { fetchJobs(); }, [fetchJobs]);
  useEffect(() => { setPage(1); }, [search, statusFilter]);

  const totalPages = Math.ceil(total / perPage);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Jobs</h1>
        <p className="text-[#94a3b8] mt-1">All jobs discovered by the agent ({total} total)</p>
      </div>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#64748b]" />
          <input
            type="text"
            placeholder="Search by title, company, location, skills..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-[#1e293b] border border-[#334155] rounded-lg pl-10 pr-4 py-2.5 text-sm text-white placeholder-[#64748b] focus:outline-none focus:border-[#38bdf8] transition-colors"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="bg-[#1e293b] border border-[#334155] rounded-lg px-4 py-2.5 text-sm text-[#94a3b8] focus:outline-none focus:border-[#38bdf8] transition-colors"
        >
          <option value="">All Status</option>
          <option value="applied">Applied</option>
          <option value="skipped_low_score">Low Score</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      <div className="bg-[#1e293b] rounded-xl border border-[#334155] overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#38bdf8]" />
          </div>
        ) : jobs.length === 0 ? (
          <div className="text-center py-16 text-[#64748b]">No jobs found</div>
        ) : (
          <div className="divide-y divide-[#334155]">
            {jobs.map((job) => (
              <Link
                key={job.id}
                to={`/jobs/${job.id}`}
                className="flex items-start gap-4 p-4 hover:bg-[#0f172a]/50 transition-colors group"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="text-sm font-semibold text-white group-hover:text-[#38bdf8] transition-colors">
                      {job.title}
                    </h3>
                    {job.application_status && (
                      <StatusBadge status={job.application_status} />
                    )}
                  </div>
                  <div className="flex items-center gap-3 mt-1.5 text-xs text-[#94a3b8]">
                    <span className="flex items-center gap-1">
                      <Building2 className="w-3.5 h-3.5" />
                      {job.company}
                    </span>
                    {job.location && (
                      <span className="flex items-center gap-1">
                        <MapPin className="w-3.5 h-3.5" />
                        {job.location}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 mt-1.5 text-xs text-[#64748b]">
                    {job.experience && <span>{job.experience}</span>}
                    {job.salary && (
                      <span className="flex items-center gap-1">
                        <DollarSign className="w-3 h-3" />
                        {job.salary}
                      </span>
                    )}
                  </div>
                  {job.skills && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {job.skills.split(',').slice(0, 5).map((skill) => (
                        <span key={skill} className="px-2 py-0.5 text-[10px] bg-[#38bdf8]/10 text-[#38bdf8] rounded-full">
                          {skill.trim()}
                        </span>
                      ))}
                      {job.skills.split(',').length > 5 && (
                        <span className="px-2 py-0.5 text-[10px] text-[#64748b]">
                          +{job.skills.split(',').length - 5}
                        </span>
                      )}
                    </div>
                  )}
                </div>
                <div className="flex flex-col items-end gap-2 shrink-0">
                  {job.match_score !== null && (
                    <span className={`text-sm font-bold ${
                      job.match_score >= 80 ? 'text-green-400' : job.match_score >= 50 ? 'text-yellow-400' : 'text-red-400'
                    }`}>
                      {job.match_score.toFixed(0)}
                    </span>
                  )}
                  <a
                    href={job.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="p-1.5 rounded-lg hover:bg-[#334155] transition-colors"
                  >
                    <ExternalLink className="w-4 h-4 text-[#64748b]" />
                  </a>
                </div>
              </Link>
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
