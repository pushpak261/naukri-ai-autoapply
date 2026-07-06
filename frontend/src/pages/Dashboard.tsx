import { Link } from 'react-router-dom';
import {
  Briefcase, CheckCircle, XCircle, SkipForward, Clock, TrendingUp,
  BarChart3, Target, Activity, Shield, Bot, Download,
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  PieChart, Pie, Cell, Legend,
} from 'recharts';
import StatCard from '../components/StatCard';
import StatusBadge from '../components/StatusBadge';
import { CardSkeleton, ChartSkeleton } from '../components/Skeleton';
import { useDashboard } from '../lib/hooks';
import { api } from '../lib/api';

export default function Dashboard() {
  const { stats, session, metrics } = useDashboard();

  if (stats.isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <div className="h-8 w-48 bg-[#334155] rounded animate-pulse" />
          <div className="h-4 w-72 bg-[#334155] rounded animate-pulse mt-2" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => <CardSkeleton key={i} />)}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => <CardSkeleton key={i} />)}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {[1, 2].map((i) => <ChartSkeleton key={i} />)}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {[1, 2].map((i) => <ChartSkeleton key={i} />)}
        </div>
      </div>
    );
  }

  if (stats.isError) {
    return <div className="text-red-400">Failed to load dashboard data: {stats.error.message}</div>;
  }

  const data = stats.data!;
  const pieData = [
    { name: 'Applied', value: data.stats.applied, color: '#22c55e' },
    { name: 'Skipped', value: data.stats.skipped, color: '#eab308' },
    { name: 'Failed', value: data.stats.failed, color: '#ef4444' },
  ];

  const runChartData = data.recent_runs.slice(0, 10).reverse().map((r) => ({
    date: r.started_at.slice(0, 10),
    Applied: r.applied,
    Skipped: r.skipped,
    Failed: r.failed,
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: 'var(--color-text)' }}>Dashboard</h1>
          <p className="mt-1" style={{ color: 'var(--color-text-secondary)' }}>Overview of your AI job application agent</p>
        </div>
        <div className="flex gap-2">
          <a
            href={api.exportData.applicationsCsv()}
            download
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
            style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}
          >
            <Download className="w-3.5 h-3.5" />
            Export CSV
          </a>
          <a
            href={api.exportData.statsJson()}
            download
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
            style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}
          >
            <Download className="w-3.5 h-3.5" />
            Export JSON
          </a>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Total Jobs Found" value={data.total_jobs_found} icon={Briefcase} color="#38bdf8" />
        <StatCard title="Total Applied" value={data.total_applied} icon={CheckCircle} color="#22c55e" subtitle={`${data.today_applied} today (cap: ${data.daily_cap})`} />
        <StatCard title="Skipped" value={data.total_skipped} icon={SkipForward} color="#eab308" />
        <StatCard title="Failed" value={data.total_failed} icon={XCircle} color="#ef4444" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-4">
          <h3 className="text-xs font-medium text-[#94a3b8] flex items-center gap-1.5 mb-2">
            <Shield className="w-3.5 h-3.5" />
            Session Health
          </h3>
          {session.isLoading ? (
            <div className="space-y-2">
              <div className="h-4 w-20 bg-[#334155] rounded animate-pulse" />
              <div className="h-3 w-32 bg-[#334155] rounded animate-pulse" />
            </div>
          ) : session.data ? (
            <div>
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${session.data.valid ? 'bg-green-500' : 'bg-red-500'}`} />
                <span className="text-sm" style={{ color: session.data.valid ? 'var(--color-success)' : 'var(--color-danger)' }}>
                  {session.data.valid ? 'Active' : 'Invalid/Expired'}
                </span>
              </div>
              <p className="text-xs mt-1" style={{ color: 'var(--color-text-muted)' }}>
                {session.data.message || (session.data.valid ? `${session.data.cookie_count} cookies` : 'No valid cookies')}
              </p>
              {session.data.last_modified && (
                <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>Updated: {new Date(session.data.last_modified).toLocaleDateString()}</p>
              )}
            </div>
          ) : (
            <p className="text-sm text-[#64748b]">No session</p>
          )}
        </div>

        <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-4">
          <h3 className="text-xs font-medium text-[#94a3b8] flex items-center gap-1.5 mb-2">
            <Activity className="w-3.5 h-3.5" />
            Model Health
          </h3>
          {metrics.isLoading ? (
            <div className="space-y-2">
              <div className="h-4 w-24 bg-[#334155] rounded animate-pulse" />
              <div className="h-3 w-20 bg-[#334155] rounded animate-pulse" />
            </div>
          ) : metrics.data ? (
            <div>
              <p className="text-sm text-white">API Calls: {metrics.data.api_calls}</p>
              <p className="text-xs text-[#64748b] mt-1">Total runs: {metrics.data.total_runs}</p>
              {metrics.data.duration_seconds > 0 && (
                <p className="text-xs text-[#64748b]">Duration: {Math.round(metrics.data.duration_seconds / 60)} min</p>
              )}
            </div>
          ) : (
            <p className="text-sm text-[#64748b]">No metrics</p>
          )}
        </div>

        <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-4">
          <h3 className="text-xs font-medium text-[#94a3b8] flex items-center gap-1.5 mb-2">
            <Bot className="w-3.5 h-3.5" />
            Quick Actions
          </h3>
          <div className="flex flex-wrap gap-1.5">
            <Link to="/agent-control" className="text-xs px-2 py-1 rounded bg-[#334155] hover:bg-[#475569] text-[#94a3b8] hover:text-white transition-colors">Agent</Link>
            <Link to="/analytics" className="text-xs px-2 py-1 rounded bg-[#334155] hover:bg-[#475569] text-[#94a3b8] hover:text-white transition-colors">Analytics</Link>
            <Link to="/skills-gap" className="text-xs px-2 py-1 rounded bg-[#334155] hover:bg-[#475569] text-[#94a3b8] hover:text-white transition-colors">Skills</Link>
            <Link to="/scam-detector" className="text-xs px-2 py-1 rounded bg-[#334155] hover:bg-[#475569] text-[#94a3b8] hover:text-white transition-colors">Scams</Link>
            <Link to="/cache-explorer" className="text-xs px-2 py-1 rounded bg-[#334155] hover:bg-[#475569] text-[#94a3b8] hover:text-white transition-colors">Cache</Link>
            <Link to="/log-viewer" className="text-xs px-2 py-1 rounded bg-[#334155] hover:bg-[#475569] text-[#94a3b8] hover:text-white transition-colors">Logs</Link>
            <Link to="/backups" className="text-xs px-2 py-1 rounded bg-[#334155] hover:bg-[#475569] text-[#94a3b8] hover:text-white transition-colors">Backups</Link>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-5">
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-[#38bdf8]" />
            Application Trend (Last 10 Runs)
          </h2>
          {runChartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={runChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 12 }} />
                <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} />
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#f1f5f9' }} />
                <Bar dataKey="Applied" fill="#22c55e" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Skipped" fill="#eab308" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Failed" fill="#ef4444" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-64 text-[#64748b]">No run data yet</div>
          )}
        </div>

        <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-5">
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <Target className="w-5 h-5 text-[#38bdf8]" />
            Application Distribution (7 days)
          </h2>
          {data.stats.total > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" innerRadius={60} outerRadius={100} dataKey="value" stroke="none">
                  {pieData.map((entry) => <Cell key={entry.name} fill={entry.color} />)}
                </Pie>
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#f1f5f9' }} />
                <Legend formatter={(value: string) => <span style={{ color: '#94a3b8' }}>{value}</span>} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-64 text-[#64748b]">No applications yet</div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <Clock className="w-5 h-5 text-[#38bdf8]" />
              Recent Applications
            </h2>
            <Link to="/applications" className="text-sm text-[#38bdf8] hover:underline">View all</Link>
          </div>
          <div className="space-y-2">
            {data.recent_applications.length > 0 ? (
              data.recent_applications.map((app, i) => (
                <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-[#0f172a] border border-[#334155]">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-white truncate">{app.job_title}</p>
                    <p className="text-xs text-[#64748b] truncate">{app.company}</p>
                  </div>
                  <div className="flex items-center gap-3 ml-3">
                    <span className={`text-sm font-semibold ${app.match_score >= 80 ? 'text-green-400' : app.match_score >= 50 ? 'text-yellow-400' : 'text-red-400'}`}>
                      {app.match_score.toFixed(0)}
                    </span>
                    <StatusBadge status={app.status} />
                  </div>
                </div>
              ))
            ) : (
              <div className="text-center py-8 text-[#64748b]">No recent applications</div>
            )}
          </div>
        </div>

        <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-[#38bdf8]" />
              Recent Runs
            </h2>
            <Link to="/run-logs" className="text-sm text-[#38bdf8] hover:underline">View all</Link>
          </div>
          <div className="space-y-2">
            {data.recent_runs.length > 0 ? (
              data.recent_runs.map((run) => (
                <div key={run.id} className="flex items-center justify-between p-3 rounded-lg bg-[#0f172a] border border-[#334155]">
                  <div className="min-w-0 flex-1">
                    <p className="text-xs text-[#94a3b8]">{run.started_at.slice(0, 16).replace('T', ' ')}</p>
                    <p className="text-sm text-white truncate mt-0.5">{run.keywords.slice(0, 40)}</p>
                  </div>
                  <div className="flex items-center gap-3 ml-3">
                    <span className="text-xs text-[#94a3b8]">+{run.applied} / -{run.skipped}</span>
                    <StatusBadge status={run.status} />
                  </div>
                </div>
              ))
            ) : (
              <div className="text-center py-8 text-[#64748b]">No runs yet</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
