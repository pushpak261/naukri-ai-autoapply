import { useState, useEffect, useCallback } from 'react';
import { Database, Search, Trash2, RefreshCw, BarChart3 } from 'lucide-react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import { api, type MatchCacheEntry, type MatchCacheStats } from '../lib/api';

export default function CacheExplorer() {
  const [entries, setEntries] = useState<MatchCacheEntry[]>([]);
  const [stats, setStats] = useState<MatchCacheStats | null>(null);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [clearing, setClearing] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [e, s] = await Promise.all([
        api.cache.matchCache(search),
        api.cache.matchCacheStats(),
      ]);
      setEntries(e.items);
      setStats(s);
    } catch {} finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleClear = async () => {
    setClearing(true);
    await api.cache.clearMatchCache();
    await fetchData();
    setClearing(false);
  };

  const scoreDist = stats ? [
    { name: '0-20', value: entries.filter(e => e.score < 20).length, color: '#ef4444' },
    { name: '20-40', value: entries.filter(e => e.score >= 20 && e.score < 40).length, color: '#f97316' },
    { name: '40-60', value: entries.filter(e => e.score >= 40 && e.score < 60).length, color: '#eab308' },
    { name: '60-80', value: entries.filter(e => e.score >= 60 && e.score < 80).length, color: '#22c55e' },
    { name: '80-100', value: entries.filter(e => e.score >= 80).length, color: '#06b6d4' },
  ].filter(d => d.value > 0) : [];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#38bdf8]" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Database className="w-6 h-6 text-[#38bdf8]" />
          Match Cache Explorer
        </h1>
        <p className="text-[#94a3b8] mt-1">Browse and manage AI match results cache</p>
      </div>

      {stats && (
        <div className="grid grid-cols-4 gap-4">
          <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-4 text-center">
            <p className="text-2xl font-bold text-white">{stats.total_entries}</p>
            <p className="text-xs text-[#94a3b8] mt-1">Total Entries</p>
          </div>
          <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-4 text-center">
            <p className="text-2xl font-bold text-[#38bdf8]">{stats.avg_score}</p>
            <p className="text-xs text-[#94a3b8] mt-1">Avg Score</p>
          </div>
          <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-4 text-center">
            <p className="text-2xl font-bold text-green-400">{stats.would_apply}</p>
            <p className="text-xs text-[#94a3b8] mt-1">Would Apply</p>
          </div>
          <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-4 text-center">
            <p className="text-2xl font-bold text-red-400">{stats.would_skip}</p>
            <p className="text-xs text-[#94a3b8] mt-1">Would Skip</p>
          </div>
        </div>
      )}

      {scoreDist.length > 0 && (
        <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-5">
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-[#38bdf8]" />
            Score Distribution
          </h2>
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie data={scoreDist} cx="50%" cy="50%" outerRadius={90} dataKey="value" nameKey="name" stroke="none" label={({ name, value }) => `${name}: ${value}`}>
                {scoreDist.map((d, i) => <Cell key={i} fill={d.color} />)}
              </Pie>
              <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#f1f5f9' }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-5">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
          <div className="flex items-center gap-3 bg-[#0f172a] border border-[#334155] rounded-lg px-4 py-2 flex-1 max-w-md">
            <Search className="w-5 h-5 text-[#64748b]" />
            <input
              type="text"
              placeholder="Search by key, job_id, or resume_hash..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="bg-transparent border-none outline-none text-white placeholder-[#64748b] w-full text-sm"
            />
          </div>
          <div className="flex gap-2">
            <button onClick={fetchData} className="flex items-center gap-1.5 px-3 py-2 bg-[#334155] hover:bg-[#475569] text-white rounded-lg text-sm transition-colors">
              <RefreshCw className="w-4 h-4" />
              Refresh
            </button>
            <button onClick={handleClear} disabled={clearing} className="flex items-center gap-1.5 px-3 py-2 bg-red-600 hover:bg-red-700 disabled:bg-gray-700 text-white rounded-lg text-sm transition-colors">
              <Trash2 className="w-4 h-4" />
              {clearing ? 'Clearing...' : 'Clear Cache'}
            </button>
          </div>
        </div>

        {entries.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[#94a3b8] border-b border-[#334155]">
                  <th className="text-left py-2 px-3">Key</th>
                  <th className="text-right py-2 px-3">Score</th>
                  <th className="text-center py-2 px-3">Should Apply</th>
                  <th className="text-left py-2 px-3">Matching Skills</th>
                  <th className="text-left py-2 px-3">Missing Skills</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.key} className="border-b border-[#334155]/50 hover:bg-[#334155]/30">
                    <td className="py-2 px-3 text-white font-mono text-xs max-w-[200px] truncate">{e.key}</td>
                    <td className="py-2 px-3 text-right">
                      <span className={`font-semibold ${e.score >= 70 ? 'text-green-400' : e.score >= 40 ? 'text-yellow-400' : 'text-red-400'}`}>
                        {e.score}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-center">
                      {e.should_apply ? (
                        <span className="text-green-400 text-xs">YES</span>
                      ) : (
                        <span className="text-red-400 text-xs">NO</span>
                      )}
                    </td>
                    <td className="py-2 px-3 text-[#94a3b8] max-w-[200px] truncate">
                      {Array.isArray(e.matching_skills) ? e.matching_skills.join(', ') : e.matching_skills}
                    </td>
                    <td className="py-2 px-3 text-[#94a3b8] max-w-[200px] truncate">
                      {Array.isArray(e.missing_skills) ? e.missing_skills.join(', ') : e.missing_skills}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-8 text-[#64748b]">No cache entries found</div>
        )}
      </div>
    </div>
  );
}
