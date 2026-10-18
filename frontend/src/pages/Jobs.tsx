import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { Search, ExternalLink, Building2, MapPin, DollarSign, ChevronLeft, ChevronRight } from 'lucide-react';
import StatusBadge from '../components/StatusBadge';
import { api } from '../lib/api';

export default function Jobs() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const perPage = 20;

  const result = useQuery({
    queryKey: ['jobs', page, search, statusFilter, sourceFilter],
    queryFn: () => api.jobs(page, perPage, search, statusFilter, 'newest', 0, 100, sourceFilter),
  });
  const jobs = result.data?.items ?? [];
  const total = result.data?.total ?? 0;
  const loading = result.isPending;
  const error = result.error?.message;

  const totalPages = Math.ceil(total / perPage);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--color-text)]">Jobs</h1>
        <p className="text-[var(--color-text-secondary)] mt-1">All jobs discovered by the agent ({total} total)</p>
      </div>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--color-text-muted)]" />
          <input
            type="text"
            placeholder="Search by title, company, location, skills..."
            value={search}
            onChange={(e) => { setPage(1); setSearch(e.target.value); }}
            className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg pl-10 pr-4 py-2.5 text-sm text-[var(--color-text)] placeholder-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-primary)] transition-colors"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => { setPage(1); setStatusFilter(e.target.value); }}
          className="w-full sm:w-auto bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-4 py-2.5 text-sm text-[var(--color-text-secondary)] focus:outline-none focus:border-[var(--color-primary)] transition-colors"
        >
          <option value="">All Status</option>
          <option value="applied">Applied</option>
          <option value="skipped_low_score">Low Score</option>
          <option value="failed">Failed</option>
        </select>
        <select
          value={sourceFilter}
          onChange={(e) => { setPage(1); setSourceFilter(e.target.value); }}
          className="w-full sm:w-auto bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-4 py-2.5 text-sm text-[var(--color-text-secondary)] focus:outline-none focus:border-[var(--color-primary)] transition-colors"
        >
          <option value="">All Platforms</option>
          <option value="naukri">Naukri</option>
          <option value="linkedin">LinkedIn</option>
        </select>
      </div>

      <div className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] overflow-hidden">
        {error ? (
          <div role="alert" className="text-center py-16 text-red-400">
            <p>{error}</p>
            <button onClick={() => result.refetch()} className="mt-3 text-sm underline">Try again</button>
          </div>
        ) : loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[var(--color-primary)]" />
          </div>
        ) : jobs.length === 0 ? (
          <div className="overview-empty px-6 py-12">
            <Search size={28} aria-hidden="true" />
            <h3>{search || statusFilter || sourceFilter ? 'No jobs match these filters' : 'Your next opportunity starts with a search'}</h3>
            <p>{search || statusFilter || sourceFilter
              ? 'Try a broader keyword or reset your filters to see more opportunities.'
              : 'Jobs are collected during search runs. Review your preferences, then start a discovery run from Command center.'}</p>
            {search || statusFilter || sourceFilter ? (
              <button className="secondary-button" onClick={() => { setSearch(''); setStatusFilter(''); setSourceFilter(''); setPage(1); }}>Reset filters</button>
            ) : (
              <Link className="primary-button" to="/agent-control">Open command center <ExternalLink size={15} /></Link>
            )}
          </div>
        ) : (
          <div className="divide-y divide-[#334155]">
            {jobs.map((job) => (
              <div
                key={job.id}
                onClick={() => navigate(`/jobs/${job.id}`)}
                className="flex items-start gap-4 p-4 hover:bg-[var(--color-bg)]/50 transition-colors group cursor-pointer"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="text-sm font-semibold text-[var(--color-text)] group-hover:text-[var(--color-primary)] transition-colors">
                      {job.title}
                    </h3>
                    {job.application_status && (
                      <StatusBadge status={job.application_status} />
                    )}
                    {job.source && (
                      <span className={`px-2 py-0.5 text-[10px] rounded-full font-medium ${
                        job.source === 'linkedin'
                          ? 'bg-[#0077b5]/10 text-[#0077b5] border border-[#0077b5]/20'
                          : 'bg-[#38bdf8]/10 text-[var(--color-primary)] border border-[var(--color-primary)]/20'
                      }`}>
                        {job.source === 'linkedin' ? 'LinkedIn' : 'Naukri'}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 mt-1.5 text-xs text-[var(--color-text-secondary)]">
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
                  <div className="flex items-center gap-3 mt-1.5 text-xs text-[var(--color-text-muted)]">
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
                        <span key={skill} className="px-2 py-0.5 text-[10px] bg-[#38bdf8]/10 text-[var(--color-primary)] rounded-full">
                          {skill.trim()}
                        </span>
                      ))}
                      {job.skills.split(',').length > 5 && (
                        <span className="px-2 py-0.5 text-[10px] text-[var(--color-text-muted)]">
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
                    className="p-1.5 rounded-lg hover:bg-[var(--color-surface-hover)] transition-colors"
                  >
                    <ExternalLink className="w-4 h-4 text-[var(--color-text-muted)]" />
                  </a>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between">
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

