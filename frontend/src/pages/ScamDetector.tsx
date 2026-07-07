import { useState, useEffect } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  PieChart, Pie, Cell, Legend,
} from 'recharts';
import { ShieldAlert, AlertTriangle, CheckCircle, Info, Search, RefreshCw, ExternalLink } from 'lucide-react';
import { api, type ScamAnalysisItem } from '../lib/api';

function scamCategory(score: number): { label: string; color: string; icon: typeof ShieldAlert } {
  if (score >= 60) return { label: 'Suspicious', color: '#ef4444', icon: AlertTriangle };
  if (score >= 30) return { label: 'Moderate Risk', color: '#eab308', icon: Info };
  return { label: 'Safe', color: '#22c55e', icon: CheckCircle };
}

export default function ScamDetector() {
  const [data, setData] = useState<{
    risk_distribution: { name: string; value: number; color: string }[];
    score_distribution: ScamAnalysisItem[];
    highest_risk: ScamAnalysisItem[];
    summary: { total_jobs: number; avg_score: number; safe_count: number; moderate_count: number; suspicious_count: number };
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAnalysis = () => {
    setLoading(true);
    setError(null);
    api.scamAnalysis()
      .then(r => setData(r))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchAnalysis(); }, []);

  const distribution = data?.risk_distribution.filter(d => d.value > 0) ?? [];
  const sorted = data?.score_distribution ?? [];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-text flex items-center gap-2">
            <ShieldAlert className="w-6 h-6 text-primary" />
            Scam Detector Analyzer
          </h1>
          <p className="text-secondary mt-1">Heuristic-based risk assessment for job listings</p>
        </div>
        <div className="bg-surface rounded-xl border border-border p-8 text-center">
          <AlertTriangle className="w-12 h-12 text-red-400 mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-text mb-2">Failed to load analysis</h2>
          <p className="text-secondary mb-4">{error}</p>
          <button onClick={fetchAnalysis} className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-on-primary rounded-lg hover:bg-primary-hover transition-colors font-medium">
            <RefreshCw className="w-4 h-4" /> Retry
          </button>
        </div>
      </div>
    );
  }

  if (!data || !data.summary || data.summary.total_jobs === 0) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-text flex items-center gap-2">
            <ShieldAlert className="w-6 h-6 text-primary" />
            Scam Detector Analyzer
          </h1>
          <p className="text-secondary mt-1">Heuristic-based risk assessment for job listings</p>
        </div>
        <div className="bg-surface rounded-xl border border-border p-12 text-center">
          <Search className="w-16 h-16 text-muted mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-text mb-2">No Jobs Analyzed Yet</h2>
          <p className="text-secondary max-w-md mx-auto mb-6">
            The scam detector analyzes job listings after the agent has run a search session.
            Start an agent run to collect job data, then return here to see the risk analysis.
          </p>
          <div className="flex flex-col items-center gap-2 text-sm text-muted">
            <p className="flex items-center gap-2"><ExternalLink className="w-4 h-4 text-primary" /> Go to the <strong>Agent Control</strong> page and start a job search</p>
            <p className="flex items-center gap-2"><RefreshCw className="w-4 h-4 text-primary" /> After the run completes, refresh this page</p>
          </div>
          <button onClick={fetchAnalysis} className="mt-6 inline-flex items-center gap-2 px-4 py-2 bg-primary text-on-primary rounded-lg hover:bg-primary-hover transition-colors font-medium">
            <RefreshCw className="w-4 h-4" /> Refresh Analysis
          </button>
        </div>
      </div>
    );
  }

  const summary = data.summary;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text flex items-center gap-2">
            <ShieldAlert className="w-6 h-6 text-primary" />
            Scam Detector Analyzer
          </h1>
          <p className="text-secondary mt-1">Heuristic-based risk assessment for job listings</p>
        </div>
        <button onClick={fetchAnalysis} className="inline-flex items-center gap-2 px-3 py-1.5 text-sm bg-surface-hover text-secondary rounded-lg hover:bg-surface-hover transition-colors">
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-surface rounded-xl border border-border p-4 text-center">
          <p className="text-2xl font-bold text-text">{summary.total_jobs}</p>
          <p className="text-xs text-secondary mt-1">Total Jobs Analyzed</p>
        </div>
        <div className="bg-surface rounded-xl border border-border p-4 text-center">
          <p className="text-2xl font-bold text-green-400">{summary.safe_count}</p>
          <p className="text-xs text-secondary mt-1">Safe Listings</p>
        </div>
        <div className="bg-surface rounded-xl border border-border p-4 text-center">
          <p className="text-2xl font-bold text-yellow-400">{summary.moderate_count}</p>
          <p className="text-xs text-secondary mt-1">Moderate Risk</p>
        </div>
        <div className="bg-surface rounded-xl border border-border p-4 text-center">
          <p className="text-2xl font-bold text-red-400">{summary.suspicious_count}</p>
          <p className="text-xs text-secondary mt-1">Suspicious Listings</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-surface rounded-xl border border-border p-5">
          <h2 className="text-lg font-semibold text-text mb-4">Risk Distribution</h2>
          {distribution.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie data={distribution} cx="50%" cy="50%" outerRadius={100} dataKey="value" nameKey="name" stroke="none" label={({ percent }: { percent?: number }) => `${((percent ?? 0) * 100).toFixed(0)}%`}>
                  {distribution.map((d, i) => <Cell key={i} fill={d.color} />)}
                </Pie>
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#f1f5f9' }} />
                <Legend formatter={(value: string) => <span style={{ color: '#94a3b8' }}>{value}</span>} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-64 text-muted">No data</div>
          )}
        </div>

        <div className="bg-surface rounded-xl border border-border p-5">
          <h2 className="text-lg font-semibold text-text mb-4">Score Distribution</h2>
          {sorted.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={sorted.slice(0, 20)}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="job_title" tick={{ fill: '#94a3b8', fontSize: 9 }} angle={-45} textAnchor="end" height={80} />
                <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} domain={[0, 100]} unit="%" />
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#f1f5f9' }} />
                <Bar dataKey="score" fill="#ef4444" radius={[4, 4, 0, 0]} name="Scam Score" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-64 text-muted">No data</div>
          )}
        </div>
      </div>

      <div className="bg-surface rounded-xl border border-border p-5">
        <h2 className="text-lg font-semibold text-text mb-4">Highest Risk Listings</h2>
        {data.highest_risk.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-secondary border-b border-border">
                  <th className="text-left py-2 px-3">Job Title</th>
                  <th className="text-left py-2 px-3">Company</th>
                  <th className="text-right py-2 px-3">Risk Score</th>
                  <th className="text-left py-2 px-3">Category</th>
                </tr>
              </thead>
              <tbody>
                {data.highest_risk.map((a) => {
                  const cat = scamCategory(a.score);
                  const CatIcon = cat.icon;
                  return (
                    <tr key={a.job_id} className="border-b border-border/50 hover:bg-surface-hover/30">
                      <td className="py-2 px-3 text-text">{a.job_title}</td>
                      <td className="py-2 px-3 text-secondary">{a.company}</td>
                      <td className="py-2 px-3 text-right">
                        <span className={`font-semibold ${a.score >= 60 ? 'text-red-400' : a.score >= 30 ? 'text-yellow-400' : 'text-green-400'}`}>
                          {a.score}
                        </span>
                      </td>
                      <td className="py-2 px-3">
                        <span className="flex items-center gap-1.5 text-xs" style={{ color: cat.color }}>
                          <CatIcon className="w-3.5 h-3.5" />
                          {cat.label}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-8 text-muted">No data</div>
        )}
      </div>
    </div>
  );
}
