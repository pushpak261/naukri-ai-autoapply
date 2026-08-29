import { useState, useEffect, useCallback } from 'react';
import {
  Filter,
  CheckCircle2,
  XCircle,
  Search,
  RefreshCw,
  Building2,
  MapPin,
  Clock,
  ExternalLink,
  ShieldAlert,
  ChevronLeft,
  ChevronRight,
  Sliders,
  Send,
  Zap,
  Check,
  AlertTriangle,
  Info,
} from 'lucide-react';
import { api, type InspectorResponse, type InspectorJobItem } from '../lib/api';

const FILTER_KEYS = [
  { key: 'enable_scam_filter', label: 'Scam / Consultancy Filter', icon: ShieldAlert, desc: 'Detects fake placement agencies & spam signals' },
  { key: 'enable_experience_filter', label: 'Experience Limit', icon: Clock, desc: 'Filters jobs requiring experience above max setting' },
  { key: 'enable_freshness_filter', label: 'Freshness Limit', icon: RefreshCw, desc: 'Filters jobs posted beyond max freshness days' },
  { key: 'enable_title_blacklist', label: 'Title Blacklist', icon: Filter, desc: 'Excludes titles containing sales, BPO, leads, etc.' },
  { key: 'enable_company_blacklist', label: 'Company Blacklist', icon: Building2, desc: 'Excludes blacklisted hiring companies' },
  { key: 'enable_description_blacklist', label: 'Description Blacklist', icon: Info, desc: 'Excludes registration fee / whatsapp scam keywords' },
  { key: 'enable_heuristics', label: 'Min Heuristic Score', icon: Zap, desc: 'Filters out low similarity TF-IDF vector scores (<0.08)' },
  { key: 'enable_match_score_filter', label: 'AI Match Score Threshold', icon: Sliders, desc: 'Filters jobs below configured AI match score threshold' },
];

export default function JobInspector() {
  const [data, setData] = useState<InspectorResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusView, setStatusView] = useState<'all' | 'passed' | 'rejected' | 'applied'>('all');
  const [sourceFilter, setSourceFilter] = useState<'all' | 'naukri' | 'linkedin'>('all');
  const [page, setPage] = useState(1);
  const [filterToggles, setFilterToggles] = useState<Record<string, boolean>>({
    master_enable: true,
    enable_scam_filter: true,
    enable_experience_filter: true,
    enable_freshness_filter: true,
    enable_title_blacklist: true,
    enable_company_blacklist: true,
    enable_description_blacklist: true,
    enable_heuristics: true,
    enable_match_score_filter: true,
  });

  const [selectedJobIds, setSelectedJobIds] = useState<number[]>([]);
  const [applying, setApplying] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const fetchInspectorData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.jobsInspector(page, 20, search, statusView, filterToggles, sourceFilter);
      setData(res);
      if (res.active_toggles) {
        setFilterToggles((prev) => ({ ...prev, ...res.active_toggles }));
      }
    } catch (err: any) {
      console.error('Failed to fetch inspector data:', err);
    } finally {
      setLoading(false);
    }
  }, [page, search, statusView, filterToggles, sourceFilter]);

  useEffect(() => {
    fetchInspectorData();
  }, [page, search, statusView, sourceFilter]);

  const handleToggleFilter = (key: string) => {
    const nextVal = !filterToggles[key];
    const newToggles = { ...filterToggles, [key]: nextVal };
    setFilterToggles(newToggles);
  };

  const handleMasterToggle = () => {
    const nextMaster = !filterToggles.master_enable;
    const newToggles: Record<string, boolean> = { master_enable: nextMaster };
    FILTER_KEYS.forEach((f) => {
      newToggles[f.key] = nextMaster;
    });
    setFilterToggles(newToggles);
  };

  const handleSelectJob = (id: number) => {
    setSelectedJobIds((prev) =>
      prev.includes(id) ? prev.filter((jId) => jId !== id) : [...prev, id]
    );
  };

  const handleSelectAllOnPage = () => {
    if (!data) return;
    const pageJobIds = data.items.map((j) => j.id);
    const allSelected = pageJobIds.every((id) => selectedJobIds.includes(id));
    if (allSelected) {
      setSelectedJobIds((prev) => prev.filter((id) => !pageJobIds.includes(id)));
    } else {
      setSelectedJobIds((prev) => Array.from(new Set([...prev, ...pageJobIds])));
    }
  };

  const handleApplyBatch = async (idsToApply: number[]) => {
    if (idsToApply.length === 0) return;
    setApplying(true);
    try {
      const res = await api.applyJobsBatch(idsToApply);
      setToastMessage(res.message);
      setSelectedJobIds([]);
      await fetchInspectorData();
    } catch (err: any) {
      setToastMessage(`Apply error: ${err.message}`);
    } finally {
      setApplying(false);
      setTimeout(() => setToastMessage(null), 4000);
    }
  };

  const perPage = 20;
  const totalPages = data ? Math.ceil(data.total / perPage) : 1;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-[#38bdf8]/10 rounded-xl border border-[#38bdf8]/20 text-[#38bdf8]">
              <Filter className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white">Job Filter Inspector & Debugger</h1>
              <p className="text-[#94a3b8] text-sm mt-0.5">
                Inspect raw scraped jobs vs filtered jobs, toggle pipeline filters in real-time, and apply to client jobs.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => fetchInspectorData()}
            className="flex items-center gap-2 px-3.5 py-2 bg-[#1e293b] border border-[#334155] rounded-xl text-sm font-medium text-[#94a3b8] hover:text-white hover:border-[#38bdf8] transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-[#38bdf8]' : ''}`} />
            Refresh
          </button>
          <button
            onClick={handleMasterToggle}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all ${
              filterToggles.master_enable
                ? 'bg-[#38bdf8] text-black hover:bg-[#0284c7]'
                : 'bg-red-500/20 border border-red-500/40 text-red-400 hover:bg-red-500/30'
            }`}
          >
            <Zap className="w-4 h-4" />
            {filterToggles.master_enable ? 'Disable All Filters' : 'Enable All Filters'}
          </button>
        </div>
      </div>

      {/* Notification Toast */}
      {toastMessage && (
        <div className="flex items-center gap-3 p-4 bg-[#0f172a] border border-[#38bdf8]/50 rounded-xl text-sm text-[#38bdf8] shadow-lg animate-fade-in">
          <CheckCircle2 className="w-5 h-5 shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Summary KPI Grid */}
      {data && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="p-4 bg-[#1e293b] border border-[#334155] rounded-xl">
            <div className="text-xs font-medium text-[#94a3b8] uppercase tracking-wider">Scraped Raw Jobs</div>
            <div className="text-2xl font-bold text-white mt-1">{data.summary.total_scraped_raw}</div>
            <div className="text-xs text-[#64748b] mt-1">Total jobs discovered before filtering</div>
          </div>
          <div className="p-4 bg-[#1e293b] border border-green-500/30 rounded-xl bg-green-500/5">
            <div className="text-xs font-medium text-green-400 uppercase tracking-wider">Passed Active Filters</div>
            <div className="text-2xl font-bold text-green-400 mt-1">{data.summary.total_passed}</div>
            <div className="text-xs text-green-400/70 mt-1">Ready for AI evaluation & auto-apply</div>
          </div>
          <div className="p-4 bg-[#1e293b] border border-amber-500/30 rounded-xl bg-amber-500/5">
            <div className="text-xs font-medium text-amber-400 uppercase tracking-wider">Filtered Out (Rejected)</div>
            <div className="text-2xl font-bold text-amber-400 mt-1">{data.summary.total_rejected}</div>
            <div className="text-xs text-amber-400/70 mt-1">Blocked by 1 or more active filters</div>
          </div>
          <div className="p-4 bg-[#1e293b] border border-[#38bdf8]/30 rounded-xl bg-[#38bdf8]/5">
            <div className="text-xs font-medium text-[#38bdf8] uppercase tracking-wider">Applied Jobs</div>
            <div className="text-2xl font-bold text-[#38bdf8] mt-1">{data.summary.total_applied}</div>
            <div className="text-xs text-[#38bdf8]/70 mt-1">Submitted applications</div>
          </div>
        </div>
      )}

      {/* Filter Controls Panel */}
      <div className="p-5 bg-[#1e293b] border border-[#334155] rounded-xl space-y-4">
        <div className="flex items-center justify-between border-b border-[#334155] pb-3">
          <div className="flex items-center gap-2">
            <Sliders className="w-5 h-5 text-[#38bdf8]" />
            <h2 className="text-base font-semibold text-white">Pipeline Filter Controls</h2>
          </div>
          <span className="text-xs text-[#94a3b8]">
            Toggle filters below to test job outcomes in real-time
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
          {FILTER_KEYS.map(({ key, label, icon: Icon, desc }) => {
            const isEnabled = filterToggles[key] ?? true;
            const keyMap: Record<string, string> = {
              enable_experience_filter: 'experience',
              enable_freshness_filter: 'freshness',
              enable_scam_filter: 'scam_detection',
              enable_title_blacklist: 'title_blacklist',
              enable_company_blacklist: 'company_blacklist',
              enable_description_blacklist: 'description_blacklist',
              enable_heuristics: 'heuristics',
              enable_match_score_filter: 'match_score',
            };
            const statKey = keyMap[key];
            const rejectedCount = data?.summary?.rejections_by_filter?.[statKey] ?? 0;

            return (
              <div
                key={key}
                onClick={() => handleToggleFilter(key)}
                className={`p-3.5 rounded-xl border transition-all cursor-pointer flex flex-col justify-between ${
                  isEnabled
                    ? 'bg-[#0f172a] border-[#38bdf8]/40 hover:border-[#38bdf8]'
                    : 'bg-[#1e293b]/50 border-[#334155] opacity-60 hover:opacity-100'
                }`}
              >
                <div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Icon className={`w-4 h-4 ${isEnabled ? 'text-[#38bdf8]' : 'text-[#64748b]'}`} />
                      <span className="text-xs font-semibold text-white">{label}</span>
                    </div>
                    <div
                      className={`w-9 h-5 rounded-full p-0.5 transition-colors ${
                        isEnabled ? 'bg-[#38bdf8]' : 'bg-[#334155]'
                      }`}
                    >
                      <div
                        className={`w-4 h-4 rounded-full bg-white transition-transform ${
                          isEnabled ? 'translate-x-4' : 'translate-x-0'
                        }`}
                      />
                    </div>
                  </div>
                  <p className="text-[11px] text-[#64748b] mt-1.5 line-clamp-2">{desc}</p>
                </div>
                {isEnabled && (
                  <div className="mt-2 text-[10px] font-medium text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded-md inline-block self-start">
                    Blocked {rejectedCount} jobs
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Main Jobs Section Controls */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="relative flex-1 sm:w-72">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#64748b]" />
              <input
                type="text"
                placeholder="Search jobs by title, company..."
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
                className="w-full bg-[#1e293b] border border-[#334155] rounded-xl pl-9 pr-4 py-2 text-sm text-white placeholder-[#64748b] focus:outline-none focus:border-[#38bdf8]"
              />
            </div>
            <select
              value={statusView}
              onChange={(e: any) => {
                setStatusView(e.target.value);
                setPage(1);
              }}
              className="bg-[#1e293b] border border-[#334155] rounded-xl px-3 py-2 text-sm text-[#94a3b8] focus:outline-none focus:border-[#38bdf8]"
            >
              <option value="all">All Jobs</option>
              <option value="passed">Passed Filters Only</option>
              <option value="rejected">Rejected Jobs Only</option>
              <option value="applied">Applied Jobs Only</option>
            </select>
            <select
              value={sourceFilter}
              onChange={(e: any) => {
                setSourceFilter(e.target.value);
                setPage(1);
              }}
              className="bg-[#1e293b] border border-[#334155] rounded-xl px-3 py-2 text-sm text-[#94a3b8] focus:outline-none focus:border-[#38bdf8]"
            >
              <option value="all">All Sources</option>
              <option value="naukri">Naukri</option>
              <option value="linkedin">LinkedIn</option>
            </select>
          </div>

          <div className="flex items-center gap-3">
            {data && data.items.length > 0 && (
              <button
                onClick={handleSelectAllOnPage}
                className="text-xs font-medium text-[#38bdf8] hover:underline"
              >
                {data.items.every((j) => selectedJobIds.includes(j.id))
                  ? 'Deselect Page'
                  : 'Select Page'}
              </button>
            )}

            <button
              disabled={selectedJobIds.length === 0 || applying}
              onClick={() => handleApplyBatch(selectedJobIds)}
              className="flex items-center gap-2 px-4 py-2 bg-[#38bdf8] text-black font-semibold text-sm rounded-xl hover:bg-[#0284c7] disabled:opacity-40 disabled:cursor-not-allowed transition-all"
            >
              <Send className="w-4 h-4" />
              Apply to Selected ({selectedJobIds.length})
            </button>
          </div>
        </div>

        {/* Job List Container */}
        <div className="bg-[#1e293b] rounded-xl border border-[#334155] overflow-hidden">
          {loading ? (
            <div className="flex flex-col items-center justify-center h-64 gap-3">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#38bdf8]" />
              <p className="text-sm text-[#64748b]">Evaluating jobs against pipeline filters...</p>
            </div>
          ) : !data || data.items.length === 0 ? (
            <div className="text-center py-16 text-[#64748b] space-y-2">
              <Filter className="w-8 h-8 mx-auto opacity-40 text-[#64748b]" />
              <p className="text-base font-medium text-white">No jobs found matching your criteria</p>
              <p className="text-xs">Try adjusting your search terms or filter toggle controls above.</p>
            </div>
          ) : (
            <div className="divide-y divide-[#334155]">
              {data.items.map((job: InspectorJobItem) => {
                const isSelected = selectedJobIds.includes(job.id);

                return (
                  <div
                    key={job.id}
                    className={`p-4 transition-colors hover:bg-[#0f172a]/50 ${
                      isSelected ? 'bg-[#38bdf8]/5' : ''
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => handleSelectJob(job.id)}
                        className="mt-1 rounded border-[#334155] text-[#38bdf8] focus:ring-0 cursor-pointer"
                      />

                      <div className="flex-1 min-w-0">
                        {/* Title & Status */}
                        <div className="flex items-center gap-2 flex-wrap">
                          <h3 className="text-base font-semibold text-white">{job.title}</h3>

                          {job.application?.status === 'applied' ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 text-xs font-semibold rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
                              <Check className="w-3 h-3" /> Applied
                            </span>
                          ) : job.passed ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 text-xs font-semibold rounded-full bg-green-500/10 text-green-400 border border-green-500/20">
                              <CheckCircle2 className="w-3 h-3" /> Passed Filters
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 text-xs font-semibold rounded-full bg-red-500/10 text-red-400 border border-red-500/20">
                              <XCircle className="w-3 h-3" /> Rejected ({job.rejection_reasons.length})
                            </span>
                          )}

                          {job.source && (
                            <span className="px-2 py-0.5 text-[10px] font-medium bg-[#38bdf8]/10 text-[#38bdf8] border border-[#38bdf8]/20 rounded-full">
                              {job.source.toUpperCase()}
                            </span>
                          )}
                        </div>

                        {/* Meta info */}
                        <div className="flex flex-wrap items-center gap-4 mt-2 text-xs text-[#94a3b8]">
                          <span className="flex items-center gap-1 font-medium text-white">
                            <Building2 className="w-3.5 h-3.5 text-[#64748b]" />
                            {job.company}
                          </span>
                          {job.location && (
                            <span className="flex items-center gap-1">
                              <MapPin className="w-3.5 h-3.5 text-[#64748b]" />
                              {job.location}
                            </span>
                          )}
                          {job.experience && (
                            <span className="flex items-center gap-1">
                              <Clock className="w-3.5 h-3.5 text-[#64748b]" />
                              {job.experience}
                            </span>
                          )}
                        </div>

                        {/* Filter Audit Badges */}
                        <div className="flex flex-wrap items-center gap-1.5 mt-3">
                          {Object.entries(job.filter_evaluations).map(([fKey, fVal]) => {
                            if (!fVal.enabled) return null;
                            return (
                              <span
                                key={fKey}
                                className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium rounded border ${
                                  fVal.passed
                                    ? 'bg-green-500/5 text-green-400 border-green-500/20'
                                    : 'bg-red-500/10 text-red-400 border-red-500/30'
                                }`}
                                title={fVal.reason}
                              >
                                {fVal.passed ? (
                                  <CheckCircle2 className="w-2.5 h-2.5" />
                                ) : (
                                  <XCircle className="w-2.5 h-2.5" />
                                )}
                                {fVal.name}
                              </span>
                            );
                          })}
                        </div>

                        {/* Rejection reason warning box */}
                        {!job.passed && job.rejection_reasons.length > 0 && (
                          <div className="mt-3 p-2.5 bg-red-500/5 border border-red-500/20 rounded-lg text-xs text-red-300 flex items-start gap-2">
                            <AlertTriangle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
                            <div>
                              <span className="font-semibold text-red-400">Rejection Reasons:</span>
                              <ul className="list-disc list-inside mt-0.5 space-y-0.5 text-red-300/90">
                                {job.rejection_reasons.map((r, i) => (
                                  <li key={i}>{r}</li>
                                ))}
                              </ul>
                            </div>
                          </div>
                        )}
                      </div>

                      {/* Right Action buttons */}
                      <div className="flex flex-col items-end gap-2 shrink-0">
                        <a
                          href={job.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="p-2 rounded-lg bg-[#0f172a] hover:bg-[#334155] border border-[#334155] text-[#94a3b8] hover:text-white transition-colors"
                          title="Open job link"
                        >
                          <ExternalLink className="w-4 h-4" />
                        </a>

                        <button
                          onClick={() => handleApplyBatch([job.id])}
                          disabled={job.application?.status === 'applied' || applying}
                          className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                            job.application?.status === 'applied'
                              ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20 cursor-default'
                              : 'bg-[#38bdf8] text-black hover:bg-[#0284c7]'
                          }`}
                        >
                          {job.application?.status === 'applied' ? 'Applied' : 'Apply Now'}
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Pagination Footer */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-[#64748b]">
            Showing {(page - 1) * perPage + 1}–{Math.min(page * perPage, data?.total || 0)} of {data?.total || 0}
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="p-2 rounded-xl border border-[#334155] text-[#94a3b8] hover:bg-[#334155] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="text-sm text-[#94a3b8] px-2">{page} / {totalPages}</span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="p-2 rounded-xl border border-[#334155] text-[#94a3b8] hover:bg-[#334155] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
