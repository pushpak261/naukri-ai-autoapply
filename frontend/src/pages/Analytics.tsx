import { useState, useEffect } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  AreaChart, Area, Legend,
} from 'recharts';
import { BarChart3, TrendingUp, Building2, Hash, Calendar } from 'lucide-react';
import { api, type CompanyDistribution, type LocationDistribution, type KeywordPerformance, type DailyTimeline, type SuccessRateTrend } from '../lib/api';
import LocationChart from '../components/LocationChart';

export default function Analytics() {
  const [companies, setCompanies] = useState<CompanyDistribution[]>([]);
  const [locations, setLocations] = useState<LocationDistribution[]>([]);
  const [keywords, setKeywords] = useState<KeywordPerformance[]>([]);
  const [timeline, setTimeline] = useState<DailyTimeline[]>([]);
  const [trend, setTrend] = useState<SuccessRateTrend[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.analytics.companyDistribution(),
      api.analytics.locationDistribution(),
      api.analytics.keywordPerformance(),
      api.analytics.dailyTimeline(),
      api.analytics.successRateTrend(),
    ]).then(([c, l, k, t, s]) => {
      setCompanies(c.items);
      setLocations(l.items);
      setKeywords(k.items);
      setTimeline(t.items);
      setTrend(s.items);
    }).finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text flex items-center gap-2">
          <BarChart3 className="w-6 h-6 text-primary" />
          Analytics Dashboard
        </h1>
        <p className="text-secondary mt-1">Comprehensive insights into job application performance</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-surface rounded-xl border border-border p-5">
          <h2 className="text-lg font-semibold text-text mb-4 flex items-center gap-2">
            <Building2 className="w-5 h-5 text-primary" />
            Company Distribution
          </h2>
          {companies.length > 0 ? (
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={companies} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis type="number" tick={{ fill: '#94a3b8', fontSize: 12 }} />
                <YAxis type="category" dataKey="company" width={120} tick={{ fill: '#94a3b8', fontSize: 11 }} />
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#f1f5f9' }} />
                <Bar dataKey="count" fill="#38bdf8" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-64 text-muted">No data</div>
          )}
        </div>

        <LocationChart data={locations} loading={loading} />

        <div className="bg-surface rounded-xl border border-border p-5">
          <h2 className="text-lg font-semibold text-text mb-4 flex items-center gap-2">
            <Hash className="w-5 h-5 text-primary" />
            Keyword Performance
          </h2>
          {keywords.length > 0 ? (
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={keywords}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="keyword" tick={{ fill: '#94a3b8', fontSize: 11 }} />
                <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} />
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#f1f5f9' }} />
                <Bar dataKey="found" fill="#38bdf8" radius={[4, 4, 0, 0]} name="Found" stackId="a" />
                <Bar dataKey="applied" fill="#22c55e" radius={[4, 4, 0, 0]} name="Applied" stackId="a" />
                <Bar dataKey="skipped" fill="#eab308" radius={[4, 4, 0, 0]} name="Skipped" stackId="a" />
                <Bar dataKey="failed" fill="#ef4444" radius={[4, 4, 0, 0]} name="Failed" stackId="a" />
                <Legend formatter={(value: string) => <span style={{ color: '#94a3b8' }}>{value}</span>} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-64 text-muted">No data</div>
          )}
        </div>

        <div className="bg-surface rounded-xl border border-border p-5">
          <h2 className="text-lg font-semibold text-text mb-4 flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-primary" />
            Success Rate Trend
          </h2>
          {trend.length > 0 ? (
            <ResponsiveContainer width="100%" height={320}>
              <AreaChart data={trend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 11 }} />
                <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} unit="%" />
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#f1f5f9' }} />
                <Area type="monotone" dataKey="success_rate" stroke="#22c55e" fill="#22c55e" fillOpacity={0.15} strokeWidth={2} name="Success Rate %" />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-64 text-muted">No data</div>
          )}
        </div>
      </div>

      <div className="bg-surface rounded-xl border border-border p-5">
        <h2 className="text-lg font-semibold text-text mb-4 flex items-center gap-2">
          <Calendar className="w-5 h-5 text-primary" />
          Daily Timeline (30 days)
        </h2>
        {timeline.length > 0 ? (
          <ResponsiveContainer width="100%" height={400}>
            <BarChart data={timeline}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} />
              <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#f1f5f9' }} />
              <Bar dataKey="total" fill="#38bdf8" radius={[4, 4, 0, 0]} name="Total" />
              <Legend formatter={(value: string) => <span style={{ color: '#94a3b8' }}>{value}</span>} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex items-center justify-center h-64 text-muted">No data</div>
        )}
      </div>
    </div>
  );
}
