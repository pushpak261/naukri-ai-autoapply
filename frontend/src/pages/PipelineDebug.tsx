import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Search, ExternalLink, Building2, MapPin, Clock, DollarSign,
  Filter, Download, AlertCircle, RefreshCw, ChevronDown, ChevronUp,
  X, Layers, Bug, FileJson, FileSpreadsheet,
} from 'lucide-react';
import { api, type PipelineDebugItem, type PipelineDebugResponse } from '../lib/api';

type TabId = 'pre' | 'post' | 'filtered';

const TABS: { id: TabId; label: string; key: keyof PipelineDebugResponse['summary'] }[] = [
  { id: 'pre', label: 'All Scraped Jobs', key: 'total_scraped' },
  { id: 'post', label: 'Passed All Filters', key: 'passed_all_filters' },
  { id: 'filtered', label: 'Filtered Out', key: 'filtered_out' },
];

const CATEGORY_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  experience_mismatch: { bg: 'bg-orange-900/40', text: 'text-orange-300', border: 'border-orange-700/40' },
  freshness: { bg: 'bg-yellow-900/40', text: 'text-yellow-300', border: 'border-yellow-700/40' },
  early_scam: { bg: 'bg-red-900/40', text: 'text-red-300', border: 'border-red-700/40' },
  company_exclusion: { bg: 'bg-red-900/40', text: 'text-red-300', border: 'border-red-700/40' },
  title_exclusion: { bg: 'bg-orange-900/40', text: 'text-orange-300', border: 'border-orange-700/40' },
  description_exclusion: { bg: 'bg-orange-900/40', text: 'text-orange-300', border: 'border-orange-700/40' },
  authenticity: { bg: 'bg-red-900/40', text: 'text-red-300', border: 'border-red-700/40' },
  duplicate: { bg: 'bg-purple-900/40', text: 'text-purple-300', border: 'border-purple-700/40' },
  deep_scam: { bg: 'bg-red-900/40', text: 'text-red-300', border: 'border-red-700/40' },
  domain_exclusion: { bg: 'bg-orange-900/40', text: 'text-orange-300', border: 'border-orange-700/40' },
  similarity_low: { bg: 'bg-yellow-900/40', text: 'text-yellow-300', border: 'border-yellow-700/40' },
};

const DEFAULT_STYLE = { bg: 'bg-slate-900/40', text: 'text-slate-300', border: 'border-slate-700/40' };

const ITEMS_PER_PAGE = 25;

function getColumnValue(job: PipelineDebugItem, col: string): string {
  switch (col) {
    case 'title': return job.title;
    case 'company': return job.company;
    case 'location': return job.location;
    case 'experience': return job.experience;
    case 'salary': return job.salary;
    case 'source': return job.source;
    case 'posted_date': return job.posted_date;
    case 'filter_reason': return job.filter_reason || '';
    default: return '';
  }
}

function exportToCSV(items: PipelineDebugItem[], filename: string) {
  const headers = ['Title', 'Company', 'Location', 'Experience', 'Salary', 'Skills', 'URL', 'Source', 'Posted Date', 'Filter Reason'];
  const rows = items.map(j => [
    `"${j.title.replace(/"/g, '""')}"`,
    `"${j.company.replace(/"/g, '""')}"`,
    `"${j.location.replace(/"/g, '""')}"`,
    `"${j.experience.replace(/"/g, '""')}"`,
    `"${j.salary.replace(/"/g, '""')}"`,
    `"${j.skills.replace(/"/g, '""')}"`,
    j.url,
    j.source,
    j.posted_date,
    `"${(j.filter_reason || '').replace(/"/g, '""')}"`,
  ]);
  const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

function exportToJSON(items: PipelineDebugItem[], filename: string) {
  const blob = new Blob([JSON.stringify(items, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

export default function PipelineDebug() {
  const [data, setData] = useState<PipelineDebugResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>('pre');
  const [sourceFilter, setSourceFilter] = useState('');
  const [search, setSearch] = useState('');
  const [sortCol, setSortCol] = useState('title');
  const [sortAsc, setSortAsc] = useState(true);
  const [page, setPage] = useState(1);
  const [expandedJob, setExpandedJob] = useState<number | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.pipelineDebug(sourceFilter);
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load pipeline debug data');
    } finally {
      setLoading(false);
    }
  }, [sourceFilter]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const activeJobs = useMemo(() => {
    if (!data) return [];
    const source = data[activeTab === 'pre' ? 'pre_filter' : activeTab === 'post' ? 'post_filter' : 'filtered_out'];
    return source;
  }, [data, activeTab]);

  const filtered = useMemo(() => {
    if (!search.trim()) return activeJobs;
    const q = search.toLowerCase();
    return activeJobs.filter(j =>
      j.title.toLowerCase().includes(q) ||
      j.company.toLowerCase().includes(q) ||
      j.location.toLowerCase().includes(q) ||
      j.skills.toLowerCase().includes(q) ||
      (j.filter_reason || '').toLowerCase().includes(q)
    );
  }, [activeJobs, search]);

  const sorted = useMemo(() => {
    const arr = [...filtered];
    arr.sort((a, b) => {
      const va = getColumnValue(a, sortCol).toLowerCase();
      const vb = getColumnValue(b, sortCol).toLowerCase();
      const cmp = va.localeCompare(vb);
      return sortAsc ? cmp : -cmp;
    });
    return arr;
  }, [filtered, sortCol, sortAsc]);

  const paginated = useMemo(() => {
    const start = (page - 1) * ITEMS_PER_PAGE;
    return sorted.slice(start, start + ITEMS_PER_PAGE);
  }, [sorted, page]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / ITEMS_PER_PAGE));

  const handleSort = (col: string) => {
    if (sortCol === col) {
      setSortAsc(a => !a);
    } else {
      setSortCol(col);
      setSortAsc(true);
    }
  };

  const handleSearch = (val: string) => {
    setSearch(val);
    setPage(1);
  };

  const handleTabChange = (tab: TabId) => {
    setActiveTab(tab);
    setPage(1);
    setSearch('');
    setExpandedJob(null);
  };

  const currentExportLabel = TABS.find(t => t.id === activeTab)?.label.replace(/\s+/g, '_').toLowerCase() || 'jobs';

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#38bdf8]" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Bug className="w-7 h-7 text-[#38bdf8]" />
          <div>
            <h1 className="text-2xl font-bold text-white">Pipeline Debug</h1>
            <p className="text-sm text-[#94a3b8]">Job filtering pipeline — before and after view</p>
          </div>
        </div>
        <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-10 text-center">
          <AlertCircle className="w-12 h-12 text-red-400 mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-white mb-2">Failed to load</h2>
          <p className="text-sm text-[#94a3b8] mb-5">{error}</p>
          <button onClick={fetchData}
            className="inline-flex items-center gap-2 px-5 py-2 bg-[#38bdf8] text-[#0f172a] rounded-lg hover:bg-[#7dd3fc] transition-colors font-medium text-sm">
            <RefreshCw className="w-4 h-4" /> Retry
          </button>
        </div>
      </div>
    );
  }

  if (!data || !data.summary.total_scraped) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Bug className="w-7 h-7 text-[#38bdf8]" />
          <div>
            <h1 className="text-2xl font-bold text-white">Pipeline Debug</h1>
            <p className="text-sm text-[#94a3b8]">Job filtering pipeline — before and after view</p>
          </div>
        </div>
        <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-14 text-center">
          <Search className="w-14 h-14 text-[#475569] mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-white mb-2">No Jobs Yet</h2>
          <p className="text-sm text-[#94a3b8] max-w-md mx-auto mb-6">
            Run the agent to collect jobs from Naukri or LinkedIn, then return here to see the full pipeline debug view.
          </p>
        </div>
      </div>
    );
  }

  const { summary, filter_breakdown, filter_labels } = data;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Bug className="w-7 h-7 text-[#38bdf8]" />
          <div>
            <h1 className="text-2xl font-bold text-white">Pipeline Debug</h1>
            <p className="text-sm text-[#94a3b8]">
              {summary.total_scraped} total jobs — {summary.passed_all_filters} passed all filters, {summary.filtered_out} filtered out
            </p>
          </div>
        </div>
        <button onClick={fetchData}
          className="inline-flex items-center gap-2 px-3 py-1.5 text-sm bg-[#334155] text-[#94a3b8] rounded-lg hover:bg-[#475569] transition-colors">
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-4">
          <div className="flex items-center gap-2 text-[#38bdf8] mb-1">
            <Layers className="w-4 h-4" />
            <span className="text-xs font-medium uppercase tracking-wider">Total Scraped</span>
          </div>
          <div className="text-3xl font-bold text-white">{summary.total_scraped}</div>
          <div className="text-xs text-[#64748b] mt-1">Jobs before any filtering</div>
        </div>
        <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-4">
          <div className="flex items-center gap-2 text-[#22c55e] mb-1">
            <Filter className="w-4 h-4" />
            <span className="text-xs font-medium uppercase tracking-wider">Passed All Filters</span>
          </div>
          <div className="text-3xl font-bold text-white">{summary.passed_all_filters}</div>
          <div className="text-xs text-[#64748b] mt-1">
            {summary.total_scraped > 0 ? `${(summary.passed_all_filters / summary.total_scraped * 100).toFixed(1)}% pass rate` : '—'}
          </div>
        </div>
        <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-4">
          <div className="flex items-center gap-2 text-[#ef4444] mb-1">
            <X className="w-4 h-4" />
            <span className="text-xs font-medium uppercase tracking-wider">Filtered Out</span>
          </div>
          <div className="text-3xl font-bold text-white">{summary.filtered_out}</div>
          <div className="text-xs text-[#64748b] mt-1">
            {summary.total_scraped > 0 ? `${(summary.filtered_out / summary.total_scraped * 100).toFixed(1)}% filtered rate` : '—'}
          </div>
        </div>
      </div>

      {/* Filter Breakdown */}
      {summary.filtered_out > 0 && (
        <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-4">
          <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-[#f59e0b]" />
            Filter Breakdown — Why Jobs Were Removed
          </h3>
          <div className="flex flex-wrap gap-2">
            {Object.entries(filter_breakdown)
              .filter(([, count]) => count > 0)
              .sort(([, a], [, b]) => b - a)
              .map(([cat, count]) => {
                const style = CATEGORY_STYLES[cat] || DEFAULT_STYLE;
                const label = filter_labels[cat] || cat;
                return (
                  <span key={cat}
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${style.bg} ${style.text} ${style.border}`}>
                    {label}
                    <span className="font-bold">{count}</span>
                  </span>
                );
              })}
          </div>
        </div>
      )}

      {/* Tabs, Search, Source Filter */}
      <div className="bg-[#1e293b] rounded-xl border border-[#334155] overflow-hidden">
        <div className="flex items-center justify-between flex-wrap gap-2 p-3 border-b border-[#334155]">
          <div className="flex items-center gap-1">
            {TABS.map(tab => {
              const count = summary[tab.key];
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => handleTabChange(tab.id)}
                  className={`px-3 py-1.5 text-sm rounded-lg transition-all cursor-pointer ${
                    isActive
                      ? 'bg-[#38bdf8]/10 text-[#38bdf8] font-medium'
                      : 'text-[#94a3b8] hover:text-white hover:bg-[#334155]'
                  }`}
                >
                  {tab.label}
                  <span className={`ml-1.5 px-1.5 py-0.5 text-[10px] rounded-full ${
                    isActive ? 'bg-[#38bdf8]/20 text-[#38bdf8]' : 'bg-[#334155] text-[#64748b]'
                  }`}>{count}</span>
                </button>
              );
            })}
          </div>
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#64748b]" />
              <input
                type="text"
                placeholder="Search jobs..."
                value={search}
                onChange={(e) => handleSearch(e.target.value)}
                className="w-40 bg-[#0f172a] border border-[#334155] rounded-lg pl-8 pr-2.5 py-1.5 text-xs text-white placeholder-[#64748b] focus:outline-none focus:border-[#38bdf8] transition-colors"
              />
            </div>
            <select
              value={sourceFilter}
              onChange={(e) => { setSourceFilter(e.target.value); setPage(1); }}
              className="bg-[#0f172a] border border-[#334155] rounded-lg px-2.5 py-1.5 text-xs text-[#94a3b8] focus:outline-none focus:border-[#38bdf8] transition-colors"
            >
              <option value="">All Sources</option>
              <option value="naukri">Naukri</option>
              <option value="linkedin">LinkedIn</option>
            </select>
            <div className="flex items-center gap-1 border-l border-[#334155] pl-2">
              <button
                onClick={() => exportToCSV(sorted, `pipeline_debug_${currentExportLabel}.csv`)}
                className="p-1.5 rounded-lg hover:bg-[#334155] transition-colors text-[#64748b] hover:text-[#38bdf8]"
                title="Export as CSV"
              >
                <FileSpreadsheet className="w-4 h-4" />
              </button>
              <button
                onClick={() => exportToJSON(sorted, `pipeline_debug_${currentExportLabel}.json`)}
                className="p-1.5 rounded-lg hover:bg-[#334155] transition-colors text-[#64748b] hover:text-[#38bdf8]"
                title="Export as JSON"
              >
                <FileJson className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Results count + pagination */}
        <div className="flex items-center justify-between px-3 py-2 border-b border-[#334155] bg-[#0f172a]/30">
          <span className="text-xs text-[#64748b]">
            {sorted.length} job{sorted.length !== 1 ? 's' : ''}
            {search && ` matching "${search}"`}
            {sorted.length !== filtered.length && ` (filtered from ${filtered.length})`}
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="px-2 py-1 text-xs rounded bg-[#334155] text-[#94a3b8] hover:bg-[#475569] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Prev
            </button>
            <span className="text-xs text-[#64748b]">
              Page {page} of {totalPages}
            </span>
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="px-2 py-1 text-xs rounded bg-[#334155] text-[#94a3b8] hover:bg-[#475569] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Next
            </button>
          </div>
        </div>

        {/* Table header */}
        <div className="hidden md:grid grid-cols-12 gap-2 px-3 py-2 bg-[#0f172a]/50 text-xs font-medium text-[#64748b] uppercase tracking-wider border-b border-[#334155]">
          <button onClick={() => handleSort('title')} className="col-span-3 flex items-center gap-1 text-left hover:text-white transition-colors">
            Title {sortCol === 'title' && (sortAsc ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />)}
          </button>
          <button onClick={() => handleSort('company')} className="col-span-2 flex items-center gap-1 text-left hover:text-white transition-colors">
            Company {sortCol === 'company' && (sortAsc ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />)}
          </button>
          <button onClick={() => handleSort('location')} className="col-span-2 flex items-center gap-1 text-left hover:text-white transition-colors">
            Location {sortCol === 'location' && (sortAsc ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />)}
          </button>
          <button onClick={() => handleSort('experience')} className="col-span-1 flex items-center gap-1 text-left hover:text-white transition-colors">
            Exp {sortCol === 'experience' && (sortAsc ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />)}
          </button>
          <button onClick={() => handleSort('salary')} className="col-span-1 flex items-center gap-1 text-left hover:text-white transition-colors">
            Salary {sortCol === 'salary' && (sortAsc ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />)}
          </button>
          <button onClick={() => handleSort('source')} className="col-span-1 flex items-center gap-1 text-left hover:text-white transition-colors">
            Source {sortCol === 'source' && (sortAsc ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />)}
          </button>
          <span className="col-span-1">Apply</span>
          {activeTab === 'filtered' && (
            <span className="col-span-1">Reason</span>
          )}
        </div>

        {/* Table rows */}
        <div className="divide-y divide-[#334155]">
          {paginated.length === 0 ? (
            <div className="text-center py-12 text-sm text-[#64748b]">
              {search ? 'No jobs match your search' : 'No jobs in this view'}
            </div>
          ) : (
            paginated.map((job) => {
              const isExpanded = expandedJob === job.id;
              const catStyle = job.filter_category ? (CATEGORY_STYLES[job.filter_category] || DEFAULT_STYLE) : null;
              return (
                <div key={`${activeTab}-${job.id}`}>
                  <div
                    className="md:grid md:grid-cols-12 gap-2 px-3 py-3 hover:bg-[#0f172a]/40 transition-colors cursor-pointer"
                    onClick={() => setExpandedJob(isExpanded ? null : job.id)}
                  >
                    {/* Mobile: show all info stacked */}
                    <div className="md:hidden space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-semibold text-white">{job.title}</span>
                        {catStyle && (
                          <span className={`px-1.5 py-0.5 text-[10px] rounded-full font-medium border ${catStyle.bg} ${catStyle.text} ${catStyle.border}`}>
                            {filter_labels[job.filter_category!] || job.filter_category}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 text-xs text-[#94a3b8] flex-wrap">
                        <span className="flex items-center gap-1"><Building2 className="w-3 h-3" />{job.company}</span>
                        {job.location && <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{job.location}</span>}
                        {job.experience && <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{job.experience}</span>}
                        {job.salary && <span className="flex items-center gap-1"><DollarSign className="w-3 h-3" />{job.salary}</span>}
                      </div>
                      <div className="flex items-center gap-2 text-xs text-[#64748b]">
                        <span className={`px-1 py-0.5 text-[10px] rounded font-medium ${
                          job.source === 'linkedin' ? 'bg-[#0077b5]/10 text-[#0077b5]' : 'bg-[#38bdf8]/10 text-[#38bdf8]'
                        }`}>{job.source === 'linkedin' ? 'LinkedIn' : 'Naukri'}</span>
                        {job.filter_reason && <span className="text-[#f59e0b] truncate max-w-[200px]">{job.filter_reason}</span>}
                      </div>
                      <div className="flex gap-2 pt-1">
                        <a href={job.url} target="_blank" rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="inline-flex items-center gap-1 px-2 py-1 text-[10px] bg-[#38bdf8]/10 text-[#38bdf8] rounded hover:bg-[#38bdf8]/20 transition-colors">
                          <ExternalLink className="w-3 h-3" /> Apply
                        </a>
                      </div>
                    </div>

                    {/* Desktop: grid layout */}
                    <div className="hidden md:flex md:col-span-3 items-center gap-2 min-w-0">
                      <span className="text-sm font-medium text-white truncate">{job.title}</span>
                    </div>
                    <div className="hidden md:flex md:col-span-2 items-center text-sm text-[#94a3b8] truncate">
                      <Building2 className="w-3 h-3 mr-1 shrink-0" />
                      {job.company}
                    </div>
                    <div className="hidden md:flex md:col-span-2 items-center text-sm text-[#94a3b8] truncate">
                      <MapPin className="w-3 h-3 mr-1 shrink-0" />
                      {job.location || '—'}
                    </div>
                    <div className="hidden md:flex md:col-span-1 items-center text-sm text-[#94a3b8]">
                      {job.experience || '—'}
                    </div>
                    <div className="hidden md:flex md:col-span-1 items-center text-sm text-[#94a3b8]">
                      {job.salary || '—'}
                    </div>
                    <div className="hidden md:flex md:col-span-1 items-center">
                      <span className={`px-1.5 py-0.5 text-[10px] rounded font-medium ${
                        job.source === 'linkedin' ? 'bg-[#0077b5]/10 text-[#0077b5]' : 'bg-[#38bdf8]/10 text-[#38bdf8]'
                      }`}>{job.source === 'linkedin' ? 'LI' : 'NK'}</span>
                    </div>
                    <div className="hidden md:flex md:col-span-1 items-center">
                      <a href={job.url} target="_blank" rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="p-1 rounded-lg hover:bg-[#334155] transition-colors"
                        title="Open job application link">
                        <ExternalLink className="w-4 h-4 text-[#38bdf8]" />
                      </a>
                    </div>
                    {activeTab === 'filtered' && (
                      <div className="hidden md:flex md:col-span-1 items-center">
                        {catStyle && (
                          <span className={`px-1.5 py-0.5 text-[10px] rounded-full font-medium border whitespace-nowrap ${catStyle.bg} ${catStyle.text} ${catStyle.border}`}>
                            {filter_labels[job.filter_category!] || job.filter_category}
                          </span>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Expanded details */}
                  {isExpanded && (
                    <div className="px-3 py-3 bg-[#0f172a]/40 border-t border-[#334155]">
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                        <div>
                          <span className="text-[#64748b] text-xs uppercase tracking-wider">Skills</span>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {job.skills ? job.skills.split(',').slice(0, 8).map(s => (
                              <span key={s} className="px-2 py-0.5 text-[11px] bg-[#38bdf8]/8 text-[#38bdf8] rounded-full">{s.trim()}</span>
                            )) : <span className="text-[#475569]">None listed</span>}
                          </div>
                        </div>
                        <div>
                          <span className="text-[#64748b] text-xs uppercase tracking-wider">Details</span>
                          <div className="mt-1 space-y-1 text-[#94a3b8]">
                            <div>Posted: {job.posted_date || 'Unknown'}</div>
                            <div>Openings: {job.openings || 'Not specified'}</div>
                            <div>Source: {job.source === 'linkedin' ? 'LinkedIn' : 'Naukri'}</div>
                            <div>Scraped: {new Date(job.scraped_at).toLocaleString()}</div>
                          </div>
                        </div>
                        {job.filter_reason && (
                          <div className="md:col-span-2">
                            <span className="text-[#64748b] text-xs uppercase tracking-wider">Filter Reason</span>
                            <div className="mt-1 flex items-center gap-2">
                              {catStyle && (
                                <span className={`px-2 py-0.5 text-[11px] rounded-full font-medium border ${catStyle.bg} ${catStyle.text} ${catStyle.border}`}>
                                  {filter_labels[job.filter_category!] || job.filter_category}
                                </span>
                              )}
                              <span className="text-[#f59e0b]">{job.filter_reason}</span>
                            </div>
                          </div>
                        )}
                        {job.scam_details && job.scam_details.length > 0 && (
                          <div className="md:col-span-2">
                            <span className="text-[#64748b] text-xs uppercase tracking-wider">Scam Detection Details</span>
                            <div className="mt-1 flex flex-wrap gap-1">
                              {job.scam_details.map((r, i) => (
                                <span key={i} className="px-2 py-0.5 text-[11px] bg-red-900/30 text-red-300 rounded-full">{r}</span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Bottom pagination */}
        {sorted.length > ITEMS_PER_PAGE && (
          <div className="flex items-center justify-between px-3 py-2 border-t border-[#334155] bg-[#0f172a]/30">
            <span className="text-xs text-[#64748b]">
              Showing {(page - 1) * ITEMS_PER_PAGE + 1}–{Math.min(page * ITEMS_PER_PAGE, sorted.length)} of {sorted.length}
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="px-2 py-1 text-xs rounded bg-[#334155] text-[#94a3b8] hover:bg-[#475569] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Prev
              </button>
              {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                const start = Math.max(1, Math.min(page - 2, totalPages - 4));
                const p = start + i;
                if (p > totalPages) return null;
                return (
                  <button
                    key={p}
                    onClick={() => setPage(p)}
                    className={`px-2 py-1 text-xs rounded transition-colors ${
                      p === page ? 'bg-[#38bdf8] text-[#0f172a] font-medium' : 'bg-[#334155] text-[#94a3b8] hover:bg-[#475569]'
                    }`}
                  >
                    {p}
                  </button>
                );
              })}
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="px-2 py-1 text-xs rounded bg-[#334155] text-[#94a3b8] hover:bg-[#475569] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
