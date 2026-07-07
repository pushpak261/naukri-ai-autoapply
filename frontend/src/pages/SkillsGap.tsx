import { useState, useEffect } from 'react';
import {
  RadarChart, Radar as RechartsRadar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Legend,
  PieChart, Pie, Cell,
} from 'recharts';
import { Radar as RadarIcon, Search, FileText, Percent, TrendingUp, Award, Upload, AlertTriangle, RefreshCw } from 'lucide-react';
import { api, type ResumeOptimizationItem, type ResumeOptimizationResponse } from '../lib/api';

export default function SkillsGap() {
  const [data, setData] = useState<ResumeOptimizationResponse | null>(null);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAnalysis = () => {
    setLoading(true);
    setError(null);
    api.resumeOptimization()
      .then(r => setData(r))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchAnalysis(); }, []);

  const skillsData: ResumeOptimizationItem[] = search
    ? (data?.skills_data ?? []).filter(s => s.skill.toLowerCase().includes(search.toLowerCase()))
    : (data?.skills_data ?? []);

  const atsScore = data?.ats ?? { score: 0, label: 'N/A' };
  const keywordDensity = data?.keyword_density ?? [];
  const skillBreakdown = data?.skill_breakdown ?? [];
  const summary = data?.summary ?? { total_applications: 0, total_jobs: 0, total_skills_analyzed: 0, has_resume: false };

  if (loading) {
    return (
      <div className="space-y-6">
        <div>
          <div className="h-8 w-56 bg-surface-hover rounded animate-pulse" />
          <div className="h-4 w-72 bg-surface-hover rounded animate-pulse mt-2" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="bg-surface rounded-xl border border-border p-4 animate-pulse">
              <div className="h-3 w-20 bg-surface-hover rounded mb-3" />
              <div className="h-6 w-16 bg-surface-hover rounded mb-2" />
              <div className="h-3 w-24 bg-surface-hover rounded" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-text flex items-center gap-2">
            <RadarIcon className="w-6 h-6 text-primary" />
            Resume Optimization Engine
          </h1>
          <p className="text-secondary mt-1">Gamified skill analysis, ATS scoring, and keyword optimization</p>
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

  if (!summary.has_resume && summary.total_jobs === 0) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-text flex items-center gap-2">
            <RadarIcon className="w-6 h-6 text-primary" />
            Resume Optimization Engine
          </h1>
          <p className="text-secondary mt-1">Gamified skill analysis, ATS scoring, and keyword optimization</p>
        </div>
        <div className="bg-surface rounded-xl border border-border p-12 text-center">
          <Upload className="w-16 h-16 text-muted mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-text mb-2">Get Started with Resume Optimization</h2>
          <p className="text-secondary max-w-md mx-auto mb-6">
            Upload your resume and run an agent search session to unlock skill analysis, ATS scoring,
            keyword density analysis, and personalized optimization recommendations.
          </p>
          <div className="flex flex-col items-center gap-2 text-sm text-muted">
            <p className="flex items-center gap-2"><Upload className="w-4 h-4 text-primary" /> Go to the <strong>Resume</strong> page to upload your resume</p>
            <p className="flex items-center gap-2"><RefreshCw className="w-4 h-4 text-primary" /> Then run an agent session to collect job listings</p>
            <p className="flex items-center gap-2"><RefreshCw className="w-4 h-4 text-primary" /> Return here and refresh to see your analysis</p>
          </div>
          <button onClick={fetchAnalysis} className="mt-6 inline-flex items-center gap-2 px-4 py-2 bg-primary text-on-primary rounded-lg hover:bg-primary-hover transition-colors font-medium">
            <RefreshCw className="w-4 h-4" /> Refresh Analysis
          </button>
        </div>
      </div>
    );
  }

  if (!summary.has_resume || skillsData.length === 0) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-text flex items-center gap-2">
              <RadarIcon className="w-6 h-6 text-primary" />
              Resume Optimization Engine
            </h1>
            <p className="text-secondary mt-1">Gamified skill analysis, ATS scoring, and keyword optimization</p>
          </div>
          <button onClick={fetchAnalysis} className="inline-flex items-center gap-2 px-3 py-1.5 text-sm bg-surface-hover text-secondary rounded-lg hover:bg-surface-hover transition-colors">
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </button>
        </div>
        <div className="bg-surface rounded-xl border border-border p-8 text-center">
          <Upload className="w-12 h-12 text-muted mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-text mb-2">No Resume Uploaded</h2>
          <p className="text-secondary max-w-md mx-auto">
            Upload your resume on the <strong>Resume</strong> page to enable skill gap analysis,
            ATS scoring, and keyword density optimization.
          </p>
          <button onClick={fetchAnalysis} className="mt-4 inline-flex items-center gap-2 px-4 py-2 bg-primary text-on-primary rounded-lg hover:bg-primary-hover transition-colors font-medium">
            <RefreshCw className="w-4 h-4" /> Refresh
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text flex items-center gap-2">
            <RadarIcon className="w-6 h-6 text-primary" />
            Resume Optimization Engine
          </h1>
          <p className="text-secondary mt-1">Gamified skill analysis, ATS scoring, and keyword optimization</p>
        </div>
        <button onClick={fetchAnalysis} className="inline-flex items-center gap-2 px-3 py-1.5 text-sm bg-surface-hover text-secondary rounded-lg hover:bg-surface-hover transition-colors">
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-surface rounded-xl border border-border p-4">
          <h3 className="text-xs font-medium flex items-center gap-1.5 mb-2 text-secondary">
            <Award className="w-3.5 h-3.5" />
            ATS Compatibility Score
          </h3>
          <div className="flex items-center gap-3">
            <div className="relative w-14 h-14">
              <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
                <circle cx="18" cy="18" r="15.5" fill="none" stroke="#334155" strokeWidth="3" />
                <circle
                  cx="18" cy="18" r="15.5" fill="none"
                  stroke={atsScore.score >= 80 ? '#22c55e' : atsScore.score >= 50 ? '#eab308' : '#ef4444'}
                  strokeWidth="3"
                  strokeDasharray={`${atsScore.score} ${100 - atsScore.score}`}
                  strokeLinecap="round"
                />
              </svg>
              <span className="absolute inset-0 flex items-center justify-center text-sm font-bold text-text">
                {atsScore.score}
              </span>
            </div>
            <div>
              <p className="text-sm font-medium text-text">{atsScore.label}</p>
              <p className="text-xs text-muted">Based on {skillsData.length} skills</p>
            </div>
          </div>
        </div>

        <div className="bg-surface rounded-xl border border-border p-4">
          <h3 className="text-xs font-medium flex items-center gap-1.5 mb-2 text-secondary">
            <TrendingUp className="w-3.5 h-3.5" />
            Skill Coverage
          </h3>
          <div className="flex items-center gap-2">
            <PieChart width={60} height={60}>
              <Pie data={skillBreakdown} cx={30} cy={30} innerRadius={18} outerRadius={28} dataKey="count" stroke="none">
                {skillBreakdown.map((e) => <Cell key={e.name} fill={e.color} />)}
              </Pie>
            </PieChart>
            <div className="space-y-1">
              {skillBreakdown.map(s => (
                <div key={s.name} className="flex items-center gap-2 text-xs">
                  <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: s.color }} />
                  <span className="text-secondary">{s.name}: {s.count}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="bg-surface rounded-xl border border-border p-4">
          <h3 className="text-xs font-medium flex items-center gap-1.5 mb-2 text-secondary">
            <Percent className="w-3.5 h-3.5" />
            Keyword Density
          </h3>
          <p className="text-2xl font-bold text-text">{keywordDensity.length}</p>
          <p className="text-xs text-muted">Keywords with significant gaps</p>
        </div>
      </div>

      <div className="flex items-center gap-3 rounded-lg border border-border bg-surface px-4 py-2 max-w-md">
        <Search className="w-5 h-5 text-muted" />
        <input
          type="text"
          placeholder="Filter by skill name..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="bg-transparent border-none outline-none w-full text-sm text-text"
          aria-label="Filter skills"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-surface rounded-xl border border-border p-5">
          <h2 className="text-lg font-semibold text-text mb-4">Skills Radar</h2>
          {skillsData.length > 0 ? (
            <ResponsiveContainer width="100%" height={400}>
              <RadarChart data={skillsData}>
                <PolarGrid stroke="#334155" />
                <PolarAngleAxis dataKey="skill" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                <PolarRadiusAxis tick={{ fill: '#94a3b8', fontSize: 10 }} />
                <RechartsRadar name="Matching" dataKey="matching" stroke="#22c55e" fill="#22c55e" fillOpacity={0.2} />
                <RechartsRadar name="Missing" dataKey="missing" stroke="#ef4444" fill="#ef4444" fillOpacity={0.2} />
                <Legend formatter={(value: string) => <span style={{ color: '#94a3b8' }}>{value}</span>} />
              </RadarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-64 text-muted">No skill data available</div>
          )}
        </div>

        <div className="bg-surface rounded-xl border border-border p-5">
          <h2 className="text-lg font-semibold text-text mb-4">Match Rate by Skill</h2>
          {skillsData.length > 0 ? (
            <ResponsiveContainer width="100%" height={400}>
              <BarChart data={skillsData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis type="number" domain={[0, 100]} tick={{ fill: '#94a3b8', fontSize: 11 }} unit="%" />
                <YAxis type="category" dataKey="skill" width={100} tick={{ fill: '#94a3b8', fontSize: 10 }} />
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#f1f5f9' }} formatter={(v: unknown) => `${v ?? ''}%`} />
                <Bar dataKey="matchRate" fill="#38bdf8" radius={[0, 4, 4, 0]} name="Match Rate %" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-64 text-muted">No skill data available</div>
          )}
        </div>
      </div>

      {keywordDensity.length > 0 && (
        <div className="bg-surface rounded-xl border border-border p-5">
          <h2 className="text-lg font-semibold text-text mb-4 flex items-center gap-2">
            <FileText className="w-5 h-5 text-primary" />
            Keyword Density Analyzer
          </h2>
          <p className="text-xs mb-4 text-muted">Keywords appearing frequently in job listings but under-represented in your resume</p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-secondary border-b border-border">
                  <th className="text-left py-2 px-3">Keyword</th>
                  <th className="text-right py-2 px-3">In Listings</th>
                  <th className="text-right py-2 px-3">Listing Frequency</th>
                  <th className="text-right py-2 px-3">Your Resume</th>
                  <th className="text-right py-2 px-3">Gap</th>
                  <th className="text-left py-2 px-3">Recommendation</th>
                </tr>
              </thead>
              <tbody>
                {keywordDensity.map((kd, i) => (
                  <tr key={i} className="border-b border-border/50 hover:bg-surface-hover/30">
                    <td className="py-2 px-3 font-medium text-text">{kd.keyword}</td>
                    <td className="py-2 px-3 text-right text-text">{kd.count}x</td>
                    <td className="py-2 px-3 text-right text-secondary">{kd.avgInListings}%</td>
                    <td className="py-2 px-3 text-right">
                      <span className={kd.yourCount > 0 ? 'text-green-400' : 'text-red-400'}>
                        {kd.yourCount > 0 ? 'Yes' : 'No'}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-right">
                      <span className={`font-semibold ${kd.gap > 50 ? 'text-red-400' : kd.gap > 20 ? 'text-yellow-400' : 'text-green-400'}`}>
                        {kd.gap}%
                      </span>
                    </td>
                    <td className="py-2 px-3 text-xs text-muted">
                      {kd.gap > 50 ? `Add "${kd.keyword}" to your resume` : kd.gap > 20 ? `Consider mentioning "${kd.keyword}"` : 'Good coverage'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="bg-surface rounded-xl border border-border p-5">
        <h2 className="text-lg font-semibold text-text mb-4">Top Skills Breakdown</h2>
        {skillsData.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-secondary border-b border-border">
                  <th className="text-left py-2 px-3">Skill</th>
                  <th className="text-right py-2 px-3">Matching</th>
                  <th className="text-right py-2 px-3">Missing</th>
                  <th className="text-right py-2 px-3">Total</th>
                  <th className="text-right py-2 px-3">Match Rate</th>
                </tr>
              </thead>
              <tbody>
                {skillsData.map((s) => (
                  <tr key={s.skill} className="border-b border-border/50 hover:bg-surface-hover/30">
                    <td className="py-2 px-3 font-medium text-text">{s.skill}</td>
                    <td className="py-2 px-3 text-right text-green-400">{s.matching}</td>
                    <td className="py-2 px-3 text-right text-red-400">{s.missing}</td>
                    <td className="py-2 px-3 text-right text-secondary">{s.total}</td>
                    <td className="py-2 px-3 text-right">
                      <span className={`font-semibold ${s.matchRate >= 70 ? 'text-green-400' : s.matchRate >= 40 ? 'text-yellow-400' : 'text-red-400'}`}>
                        {s.matchRate}%
                      </span>
                    </td>
                  </tr>
                ))}
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
