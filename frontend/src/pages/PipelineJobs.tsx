import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  Search, ExternalLink, Building2, MapPin, DollarSign,
  Layers, RefreshCw, AlertCircle, Bot,
} from 'lucide-react';
import { api, type PipelineStage } from '../lib/api';

const STAGE_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  scraped: { bg: 'bg-slate-800/80', border: 'border-slate-600/50', text: 'text-slate-300' },
  after_early_scam: { bg: 'bg-sky-900/60', border: 'border-sky-600/40', text: 'text-sky-300' },
  after_exclusions: { bg: 'bg-indigo-900/60', border: 'border-indigo-600/40', text: 'text-indigo-300' },
  after_deep_scam: { bg: 'bg-violet-900/60', border: 'border-violet-600/40', text: 'text-violet-300' },
  final: { bg: 'bg-emerald-900/60', border: 'border-emerald-600/40', text: 'text-emerald-300' },
};

const STAGE_META: Record<string, { icon: string; short: string }> = {
  scraped: { icon: '📥', short: 'Raw' },
  after_early_scam: { icon: '🛡️', short: 'Early Scam' },
  after_exclusions: { icon: '🚫', short: 'Exclusions' },
  after_deep_scam: { icon: '🔬', short: 'Deep Scam' },
  final: { icon: '✅', short: 'Final' },
};

export default function PipelineJobs() {
  const [stages, setStages] = useState<PipelineStage[]>([]);
  const [summary, setSummary] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeStage, setActiveStage] = useState('scraped');
  const [sourceFilter, setSourceFilter] = useState('');
  const [search, setSearch] = useState('');

  const fetchPipeline = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.pipelineJobs(sourceFilter);
      setStages(data.stages);
      setSummary(data.summary);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load pipeline data');
    } finally {
      setLoading(false);
    }
  }, [sourceFilter]);

  useEffect(() => { fetchPipeline(); }, [fetchPipeline]);

  const activeStageData = stages.find(s => s.id === activeStage);
  const filteredJobs = activeStageData && search
    ? activeStageData.jobs.filter(j => {
        const q = search.toLowerCase();
        return j.title.toLowerCase().includes(q) ||
          j.company.toLowerCase().includes(q) ||
          j.location.toLowerCase().includes(q) ||
          (j.skills && j.skills.toLowerCase().includes(q));
      })
    : activeStageData?.jobs ?? [];

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
          <Layers className="w-7 h-7 text-[#38bdf8]" />
          <div>
            <h1 className="text-2xl font-bold text-white">Pipeline Jobs</h1>
            <p className="text-sm text-[#94a3b8]">Job filtering pipeline stages</p>
          </div>
        </div>
        <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-10 text-center">
          <AlertCircle className="w-12 h-12 text-red-400 mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-white mb-2">Failed to load pipeline data</h2>
          <p className="text-sm text-[#94a3b8] mb-5">{error}</p>
          <button onClick={fetchPipeline}
            className="inline-flex items-center gap-2 px-5 py-2 bg-[#38bdf8] text-[#0f172a] rounded-lg hover:bg-[#7dd3fc] transition-colors font-medium text-sm">
            <RefreshCw className="w-4 h-4" /> Retry
          </button>
        </div>
      </div>
    );
  }

  if (!stages.length || !summary.total_jobs) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Layers className="w-7 h-7 text-[#38bdf8]" />
          <div>
            <h1 className="text-2xl font-bold text-white">Pipeline Jobs</h1>
            <p className="text-sm text-[#94a3b8]">Job filtering pipeline stages — review jobs at every filter stage</p>
          </div>
        </div>
        <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-14 text-center">
          <Search className="w-14 h-14 text-[#475569] mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-white mb-2">No Jobs Yet</h2>
          <p className="text-sm text-[#94a3b8] max-w-md mx-auto mb-6">
            Run the agent to collect jobs from Naukri or LinkedIn, then return here to see them at every pipeline stage.
          </p>
          <Link to="/agent-control"
            className="inline-flex items-center gap-2 px-5 py-2 bg-[#38bdf8] text-[#0f172a] rounded-lg hover:bg-[#7dd3fc] transition-colors font-medium text-sm">
            <Bot className="w-4 h-4" /> Go to Agent Control
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Layers className="w-7 h-7 text-[#38bdf8]" />
          <div>
            <h1 className="text-2xl font-bold text-white">Pipeline Jobs</h1>
            <p className="text-sm text-[#94a3b8]">
              {summary.total_jobs} total jobs — review at every filter stage
            </p>
          </div>
        </div>
        <button onClick={fetchPipeline}
          className="inline-flex items-center gap-2 px-3 py-1.5 text-sm bg-[#334155] text-[#94a3b8] rounded-lg hover:bg-[#475569] transition-colors">
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      {/* Pipeline Flow Visualization */}
      <div className="flex items-center gap-1 overflow-x-auto pb-2">
        {stages.map((stage, i) => {
          const meta = STAGE_META[stage.id] || { icon: '•', short: stage.id };
          const isActive = activeStage === stage.id;
          const colors = STAGE_COLORS[stage.id] || STAGE_COLORS.scraped;
          const prevCount = i > 0 ? stages[i - 1].count : stage.count;
          const filtered = prevCount - stage.count;
          return (
            <div key={stage.id} className="flex items-center gap-1 shrink-0">
              <button
                onClick={() => setActiveStage(stage.id)}
                className={`flex flex-col items-center gap-1 px-3 py-2 rounded-xl border text-center transition-all cursor-pointer min-w-[100px] ${
                  isActive ? `ring-2 ring-[#38bdf8] ${colors.bg} ${colors.border}` : 'bg-[#1e293b] border-[#334155] hover:bg-[#1e293b]/80'
                }`}
              >
                <span className="text-lg">{meta.icon}</span>
                <span className={`text-xs font-medium leading-tight ${isActive ? colors.text : 'text-[#94a3b8]'}`}>{meta.short}</span>
                <span className={`text-sm font-bold ${isActive ? colors.text : 'text-white'}`}>{stage.count}</span>
                {filtered > 0 && isActive && i > 0 && (
                  <span className="text-[10px] text-red-400">-{filtered}</span>
                )}
              </button>
              {i < stages.length - 1 && (
                <div className="text-[#475569] text-lg shrink-0">→</div>
              )}
            </div>
          );
        })}
      </div>

      {/* Active Stage */}
      {activeStageData && (
        <div className="bg-[#1e293b] rounded-xl border border-[#334155] overflow-hidden">
          <div className="p-4 border-b border-[#334155]">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div>
                <h2 className="text-base font-semibold text-white flex items-center gap-2">
                  <span>{STAGE_META[activeStageData.id]?.icon}</span>
                  {activeStageData.label}
                  <span className="text-sm font-normal text-[#64748b] ml-1">({activeStageData.jobs.length} jobs)</span>
                </h2>
                <p className="text-xs text-[#94a3b8] mt-0.5">{activeStageData.description}</p>
              </div>
              <div className="flex items-center gap-2">
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#64748b]" />
                  <input
                    type="text"
                    placeholder="Search..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="w-40 bg-[#0f172a] border border-[#334155] rounded-lg pl-8 pr-2.5 py-1.5 text-xs text-white placeholder-[#64748b] focus:outline-none focus:border-[#38bdf8] transition-colors"
                  />
                </div>
                <select
                  value={sourceFilter}
                  onChange={(e) => setSourceFilter(e.target.value)}
                  className="bg-[#0f172a] border border-[#334155] rounded-lg px-2.5 py-1.5 text-xs text-[#94a3b8] focus:outline-none focus:border-[#38bdf8] transition-colors"
                >
                  <option value="">All</option>
                  <option value="naukri">Naukri</option>
                  <option value="linkedin">LinkedIn</option>
                </select>
              </div>
            </div>
          </div>

          {filteredJobs.length === 0 ? (
            <div className="text-center py-12 text-sm text-[#64748b]">No jobs match your search</div>
          ) : (
            <div className="divide-y divide-[#334155]">
              {filteredJobs.map((job) => (
                <div key={`${job.stage}-${job.id}`}
                  className="flex items-start gap-3 p-3.5 hover:bg-[#0f172a]/40 transition-colors group">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-sm font-semibold text-white group-hover:text-[#38bdf8] transition-colors">{job.title}</h3>
                      {job.source && (
                        <span className={`px-1.5 py-0.5 text-[10px] rounded-full font-medium ${
                          job.source === 'linkedin'
                            ? 'bg-[#0077b5]/10 text-[#0077b5] border border-[#0077b5]/20'
                            : 'bg-[#38bdf8]/10 text-[#38bdf8] border border-[#38bdf8]/20'
                        }`}>{job.source === 'linkedin' ? 'LinkedIn' : 'Naukri'}</span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-xs text-[#94a3b8]">
                      <span className="flex items-center gap-1"><Building2 className="w-3 h-3" />{job.company}</span>
                      {job.location && <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{job.location}</span>}
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-xs text-[#64748b]">
                      {job.experience && <span>{job.experience}</span>}
                      {job.salary && <span className="flex items-center gap-1"><DollarSign className="w-3 h-3" />{job.salary}</span>}
                    </div>
                    {job.skills && (
                      <div className="flex flex-wrap gap-1 mt-1.5">
                        {job.skills.split(',').slice(0, 4).map((s) => (
                          <span key={s} className="px-1.5 py-0.5 text-[10px] bg-[#38bdf8]/8 text-[#38bdf8] rounded-full">{s.trim()}</span>
                        ))}
                        {job.skills.split(',').length > 4 && (
                          <span className="px-1.5 py-0.5 text-[10px] text-[#64748b]">+{job.skills.split(',').length - 4}</span>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="shrink-0 pt-1">
                    <a href={job.url} target="_blank" rel="noopener noreferrer"
                      className="p-1.5 rounded-lg hover:bg-[#334155] transition-colors block">
                      <ExternalLink className="w-4 h-4 text-[#64748b]" />
                    </a>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
