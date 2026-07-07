import { useQuery } from '@tanstack/react-query';
import { LineChart, TrendingUp, DollarSign, Shield, Target, Award } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  PieChart, Pie, Cell,
} from 'recharts';
import { api } from '../lib/api';
import StatCard from '../components/StatCard';

const COLORS = ['#38bdf8', '#22c55e', '#eab308', '#ef4444', '#a78bfa', '#f472b6', '#fb923c', '#34d399'];

export default function MarketIntelligence() {
  const salary = useQuery({ queryKey: ['market-intel', 'salary'], queryFn: () => api.marketIntel.salaryBenchmarks() });
  const skills = useQuery({ queryKey: ['market-intel', 'skills'], queryFn: () => api.marketIntel.skillDemand() });
  const competitors = useQuery({ queryKey: ['market-intel', 'competitors'], queryFn: () => api.marketIntel.competitorCompanies() });
  const winRate = useQuery({ queryKey: ['market-intel', 'win-rate'], queryFn: () => api.marketIntel.winRatePrediction() });

  const isLoading = salary.isLoading || skills.isLoading || competitors.isLoading || winRate.isLoading;
  const isError = salary.isError || skills.isError || competitors.isError || winRate.isError;

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <div className="h-8 w-64 bg-surface-hover rounded animate-pulse" />
          <div className="h-4 w-80 bg-surface-hover rounded animate-pulse mt-2" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="bg-surface rounded-xl border border-border p-4 animate-pulse">
              <div className="h-3 w-20 bg-surface-hover rounded mb-3" />
              <div className="h-6 w-16 bg-surface-hover rounded" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (isError) {
    return <div className="text-red-400">Failed to load market intelligence data.</div>;
  }

  const salarySummary = salary.data?.summary;
  const skillItems = skills.data?.items ?? [];
  const competitorItems = competitors.data?.items ?? [];
  const winRateItems = winRate.data?.items ?? [];

  const topSkills = skillItems.slice(0, 10);
  const skillPieData = topSkills.map((s, i) => ({
    name: s.skill,
    value: s.count,
    color: COLORS[i % COLORS.length],
  }));

  const winRateColors = ['#ef4444', '#eab308', '#38bdf8', '#22c55e', '#22c55e'];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold" style={{ color: 'var(--color-text)' }}>Job Market Intelligence</h1>
        <p className="mt-1" style={{ color: 'var(--color-text-secondary)' }}>AI-powered insights into salary benchmarks, skill demand, and your competitive position</p>
      </div>

      {salarySummary && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard title="Market Avg. CTC" value={`₹${salarySummary.average_market_ctc}L`} icon={TrendingUp} color="#38bdf8" subtitle={`Based on ${salarySummary.total_listings} listings`} />
          <StatCard title="Min Market CTC" value={`₹${salarySummary.min_market_ctc}L`} icon={DollarSign} color="#22c55e" />
          <StatCard title="Max Market CTC" value={`₹${salarySummary.max_market_ctc}L`} icon={Award} color="#eab308" />
          <StatCard title="Win Rate (85%+)" value={winRateItems.length > 0 ? `${winRateItems[winRateItems.length - 1]?.success_rate ?? 0}%` : 'N/A'} icon={Target} color="#a78bfa" />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-xl border p-5" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2" style={{ color: 'var(--color-text)' }}>
            <LineChart className="w-5 h-5" style={{ color: 'var(--color-primary)' }} />
            Salary Benchmark by Role
          </h2>
          {salary.data && salary.data.items.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={salary.data.items.slice(0, 20)}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="title" tick={{ fill: '#94a3b8', fontSize: 10 }} angle={-30} textAnchor="end" height={80} />
                <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} />
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#f1f5f9' }} />
                <Bar dataKey="avg" fill="#38bdf8" radius={[4, 4, 0, 0]} name="Avg CTC (L)" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-64" style={{ color: 'var(--color-text-muted)' }}>No salary data available yet</div>
          )}
        </div>

        <div className="rounded-xl border p-5" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2" style={{ color: 'var(--color-text)' }}>
            <Shield className="w-5 h-5" style={{ color: 'var(--color-primary)' }} />
            Top Skills by Demand
          </h2>
          {skillPieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie data={skillPieData} cx="50%" cy="50%" outerRadius={100} dataKey="value" stroke="none" label={({ name, value }) => `${name} (${value})`}>
                  {skillPieData.map((entry) => <Cell key={entry.name} fill={entry.color} />)}
                </Pie>
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#f1f5f9' }} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-64" style={{ color: 'var(--color-text-muted)' }}>Not enough skill data yet</div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-xl border p-5" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2" style={{ color: 'var(--color-text)' }}>
            <Target className="w-5 h-5" style={{ color: 'var(--color-primary)' }} />
            Win Rate by Match Score Bracket
          </h2>
          {winRateItems.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={winRateItems}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="bracket" tick={{ fill: '#94a3b8', fontSize: 12 }} />
                <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} unit="%" />
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#f1f5f9' }} />
                <Bar dataKey="success_rate" radius={[4, 4, 0, 0]}>
                  {winRateItems.map((_, i) => <Cell key={i} fill={winRateColors[i % winRateColors.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-64" style={{ color: 'var(--color-text-muted)' }}>Not enough data to predict win rates</div>
          )}
        </div>

        <div className="rounded-xl border p-5" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2" style={{ color: 'var(--color-text)' }}>
            <Award className="w-5 h-5" style={{ color: 'var(--color-primary)' }} />
            Competitor Companies
          </h2>
          <div className="space-y-2 max-h-[300px] overflow-y-auto">
            {competitorItems.length > 0 ? (
              competitorItems.map((c, i) => (
                <div key={i} className="flex items-center justify-between p-3 rounded-lg" style={{ backgroundColor: 'var(--color-bg)', border: '1px solid var(--color-border)' }}>
                  <div>
                    <p className="text-sm font-medium" style={{ color: 'var(--color-text)' }}>{c.company}</p>
                    <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>{c.application_count} applications</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <div
                      className="text-sm font-semibold"
                      style={{ color: c.avg_match_score >= 70 ? 'var(--color-success)' : c.avg_match_score >= 40 ? 'var(--color-warning)' : 'var(--color-danger)' }}
                    >
                      {c.avg_match_score}%
                    </div>
                    <div className="w-16 h-1.5 rounded-full" style={{ backgroundColor: 'var(--color-border)' }}>
                      <div
                        className="h-full rounded-full transition-all"
                        style={{ width: `${c.avg_match_score}%`, backgroundColor: c.avg_match_score >= 70 ? 'var(--color-success)' : c.avg_match_score >= 40 ? 'var(--color-warning)' : 'var(--color-danger)' }}
                      />
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-center py-8" style={{ color: 'var(--color-text-muted)' }}>No competitor data yet</div>
            )}
          </div>
        </div>
      </div>

      <div className="rounded-xl border p-5" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2" style={{ color: 'var(--color-text)' }}>
          <TrendingUp className="w-5 h-5" style={{ color: 'var(--color-primary)' }} />
          Skill Demand Heatmap
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
          {skillItems.slice(0, 60).map((s, i) => {
            const intensity = Math.min(s.avg_score / 100, 1);
            const bgColor = `rgba(56, 189, 248, ${0.1 + intensity * 0.6})`;
            return (
              <div
                key={i}
                className="p-2 rounded-lg text-center border"
                style={{ backgroundColor: bgColor, borderColor: 'var(--color-border)' }}
                title={`${s.skill}: ${s.count} jobs, avg score ${s.avg_score}%`}
              >
                <p className="text-xs font-medium truncate" style={{ color: 'var(--color-text)' }}>{s.skill}</p>
                <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>{s.avg_score}%</p>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
