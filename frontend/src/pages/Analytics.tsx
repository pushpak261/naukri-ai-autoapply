import { useState, useEffect } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  AreaChart, Area, Legend,
} from 'recharts';
import { BarChart3, TrendingUp, Building2, Hash, Calendar } from 'lucide-react';
import { Link } from 'react-router-dom';
import { api, type CompanyDistribution, type LocationDistribution, type KeywordPerformance, type DailyTimeline, type SuccessRateTrend } from '../lib/api';
import LocationChart from '../components/LocationChart';

export default function Analytics() {
  const [companies, setCompanies] = useState<CompanyDistribution[]>([]);
  const [locations, setLocations] = useState<LocationDistribution[]>([]);
  const [keywords, setKeywords] = useState<KeywordPerformance[]>([]);
  const [timeline, setTimeline] = useState<DailyTimeline[]>([]);
  const [trend, setTrend] = useState<SuccessRateTrend[]>([]);
  const [loading, setLoading] = useState(true);

  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    Promise.all([
      api.analytics.companyDistribution(),
      api.analytics.locationDistribution(),
      api.analytics.keywordPerformance(),
      api.analytics.dailyTimeline(),
      api.analytics.successRateTrend(),
    ]).then(([c, l, k, t, s]) => {
      if (!active) return;
      setCompanies(c.items);
      setLocations(l.items);
      setKeywords(k.items);
      setTimeline(t.items);
      setTrend(s.items);
    }).catch((cause: unknown) => {
      if (active) setError(cause instanceof Error ? cause.message : 'Unable to load analytics.');
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [attempt]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[var(--color-primary)]" />
      </div>
    );
  }

  if (error) {
    return <section className="workspace-panel notice-error" role="alert">
      <h1 className="text-lg font-semibold">Analytics is temporarily unavailable</h1>
      <p>{error}</p>
      <button className="secondary-button" onClick={() => setAttempt(value => value + 1)}>Retry analytics</button>
    </section>;
  }

  if ([companies, locations, keywords, timeline, trend].every(items => items.length === 0)) {
    return <section className="workspace-panel overview-empty">
      <BarChart3 size={32} aria-hidden="true" />
      <h1 className="text-xl font-semibold">A clearer picture starts with your first run.</h1>
      <p>Your real search and application activity will populate these analytics. Review your preferences, then start a search from Command center.</p>
      <Link to="/agent-control" className="primary-button">Open command center</Link>
    </section>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--color-text)] flex items-center gap-2">
          <BarChart3 className="w-6 h-6 text-[var(--color-primary)]" />
          Analytics Dashboard
        </h1>
        <p className="text-[var(--color-text-secondary)] mt-1">Counts describe tracked application records and outcomes, not hiring or interview results.</p>
      </div>

      <p className="muted text-sm">Company and location counts include all tracked outcomes. Keyword groups may overlap; grouped bars compare total records with outcome subsets. Submission rate is applied records divided by all tracked records, including skips, dry runs, and errors.</p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-5">
          <h2 className="text-lg font-semibold text-[var(--color-text)] mb-4 flex items-center gap-2">
            <Building2 className="w-5 h-5 text-[var(--color-primary)]" />
            Tracked records by company
          </h2>
          {companies.length > 0 ? (
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={companies} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis type="number" tick={{ fill: 'var(--color-text-secondary)', fontSize: 12 }} />
                <YAxis type="category" dataKey="company" width={120} tick={{ fill: 'var(--color-text-secondary)', fontSize: 11 }} />
                <Tooltip contentStyle={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: '8px', color: 'var(--color-text)' }} />
                <Bar dataKey="count" fill="var(--color-primary)" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-64 text-[var(--color-text-muted)]">No data</div>
          )}
        </div>

        <LocationChart data={locations} loading={loading} />

        <div className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-5">
          <h2 className="text-lg font-semibold text-[var(--color-text)] mb-4 flex items-center gap-2">
            <Hash className="w-5 h-5 text-[var(--color-primary)]" />
            Tracked records by keyword
          </h2>
          {keywords.length > 0 ? (
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={keywords}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey="keyword" tick={{ fill: 'var(--color-text-secondary)', fontSize: 11 }} />
                <YAxis tick={{ fill: 'var(--color-text-secondary)', fontSize: 12 }} />
                <Tooltip contentStyle={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: '8px', color: 'var(--color-text)' }} />
                <Bar dataKey="found" fill="var(--color-primary)" radius={[4, 4, 0, 0]} name="Tracked" />
                <Bar dataKey="applied" fill="#22c55e" radius={[4, 4, 0, 0]} name="Applied" />
                <Bar dataKey="skipped" fill="#eab308" radius={[4, 4, 0, 0]} name="Skipped" />
                <Bar dataKey="failed" fill="#ef4444" radius={[4, 4, 0, 0]} name="Failed" />
                <Legend formatter={(value: string) => <span style={{ color: 'var(--color-text-secondary)' }}>{value}</span>} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-64 text-[var(--color-text-muted)]">No data</div>
          )}
        </div>

        <div className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-5">
          <h2 className="text-lg font-semibold text-[var(--color-text)] mb-4 flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-[var(--color-primary)]" />
            Submission rate trend
          </h2>
          {trend.length > 0 ? (
            <ResponsiveContainer width="100%" height={320}>
              <AreaChart data={trend}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey="date" tick={{ fill: 'var(--color-text-secondary)', fontSize: 11 }} />
                <YAxis tick={{ fill: 'var(--color-text-secondary)', fontSize: 12 }} unit="%" />
                <Tooltip contentStyle={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: '8px', color: 'var(--color-text)' }} />
                <Area type="monotone" dataKey="success_rate" stroke="#22c55e" fill="#22c55e" fillOpacity={0.15} strokeWidth={2} name="Submission rate %" />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-64 text-[var(--color-text-muted)]">No data</div>
          )}
        </div>
      </div>

      <div className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-5">
        <h2 className="text-lg font-semibold text-[var(--color-text)] mb-4 flex items-center gap-2">
          <Calendar className="w-5 h-5 text-[var(--color-primary)]" />
          Tracked records by day (30 days)
        </h2>
        {timeline.length > 0 ? (
          <ResponsiveContainer width="100%" height={400}>
            <BarChart data={timeline}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
              <XAxis dataKey="date" tick={{ fill: 'var(--color-text-secondary)', fontSize: 11 }} />
              <YAxis tick={{ fill: 'var(--color-text-secondary)', fontSize: 12 }} />
              <Tooltip contentStyle={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: '8px', color: 'var(--color-text)' }} />
              <Bar dataKey="total" fill="var(--color-primary)" radius={[4, 4, 0, 0]} name="Tracked records" />
              <Legend formatter={(value: string) => <span style={{ color: 'var(--color-text-secondary)' }}>{value}</span>} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex items-center justify-center h-64 text-[var(--color-text-muted)]">No data</div>
        )}
      </div>
    </div>
  );
}
