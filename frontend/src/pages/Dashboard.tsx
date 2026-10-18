import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight,ArrowUpRight,Briefcase,Check,CheckCircle2,Download,FileText,RefreshCw,Search,ShieldCheck,SlidersHorizontal,TrendingUp,XCircle } from 'lucide-react';
import { BarChart,Bar,XAxis,YAxis,Tooltip,ResponsiveContainer,CartesianGrid } from 'recharts';
import { api,downloadExport } from '../lib/api';
import { useDashboard } from '../lib/hooks';
import StatusBadge from '../components/StatusBadge';
import { CardSkeleton } from '../components/Skeleton';
export default function Dashboard() {
  const { stats,session,metrics }=useDashboard();
  const config=useQuery({ queryKey: ['config'],queryFn: api.config,staleTime: 30000 });
  const resume=useQuery({ queryKey: ['resume-profile'],queryFn: api.resumeProfile,staleTime: 30000 });
  const [exporting,setExporting]=useState(false);
  const [exportError,setExportError]=useState('');
  async function exportData(path: string,name: string) {
    setExporting(true); setExportError(''); try {
      await downloadExport(path,name);
    }
      catch(e) {
        setExportError(e instanceof Error? e.message:'Export failed. Please try again.');
      }
      finally {
      setExporting(false);
    }
  }
  const milestones=[{ title: 'Add your resume',text: 'Give matching a foundation.',to: '/resume',icon: FileText,done: resume.data?.exists,loading: resume.isLoading,error: resume.isError },{ title: 'Set your preferences',text: 'Choose roles and locations.',to: '/config',icon: Search,done: config.data? config.data.search.keywords.length>0&&config.data.search.locations.length>0:undefined,loading: config.isLoading,error: config.isError },{ title: 'Connect Naukri',text: 'Check your platform session.',to: '/agent-control',icon: ShieldCheck,done: session.data?.valid,loading: session.isLoading,error: session.isError },{ title: 'Review run settings',text: 'Check daily cap and dry run.',to: '/config',icon: SlidersHorizontal,done: undefined,loading: config.isLoading,error: config.isError }];
  const completed=milestones.slice(0,3).filter(m => m.done).length;
  const data=stats.data;
  const chart=data?.recent_runs.slice(0,10).reverse().map(r => ({ date: r.started_at.slice(5,10),Applied: r.applied,Skipped: r.skipped,Failed: r.failed }))||[];
  return <div className="overview space-y-6">
    <section className="overview-intro">
      <div>
        <p className="eyebrow">YOUR SEARCH, AT A GLANCE</p>
        <h1>Make room for your next opportunity.</h1>
        <p className="muted">A clear view of your progress. A considered next step.</p>
      </div>
      <Link to="/jobs" className="primary-button">Explore jobs <ArrowUpRight size={17} />
      </Link>
    </section>
    <section className="setup-panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">START WITH A STRONG FOUNDATION</p>
          <h2>Your workspace, ready for action.</h2>
        </div>
        <Link to="/help" className="text-link">Setup guide <ArrowUpRight size={15} />
        </Link>
      </div>
      <div className="setup-progress">
        <span style={{ width: `${completed/3*100}%` }} />
      </div>
      <p className="setup-caption">{completed} of 3 setup checks confirmed · Review run settings before starting</p>
      <div className="milestones">{milestones.map((m,i) => <Link key={m.title} to={m.to} className="milestone">
        <div className={`milestone-icon ${m.done? 'done':''}`}>{m.done? <Check size={19} />:<m.icon size={19} />}</div>
        <small>0{i+1} / {m.loading? 'CHECKING':m.error? 'UNAVAILABLE':m.done? 'CONFIRMED':i===3? 'REVIEW':'TO DO'}</small>
        <strong>{m.title}<ArrowUpRight size={15} />
        </strong>
        <p>{i===3&&config.data? `${config.data.application.dry_run? 'Dry run enabled':'Live applications'} · ${config.data.application.daily_cap} daily cap`:m.text}</p>
      </Link>)}</div>
    </section>
    <div className="section-heading">
      <h2>Search performance</h2>
      <span className="subtle-label">Application totals · All time</span>
    </div>
    {stats.isLoading? <div className="metric-grid">{[1,2,3,4].map(n => <CardSkeleton key={n} />)}</div>:stats.isError? <div className="notice-error" role="alert">
      <strong>We couldn’t load your activity.</strong>
      <p>{stats.error.message}</p>
      <button className="secondary-button" onClick={() => stats.refetch()}>
        <RefreshCw size={15} />Try again</button>
    </div>:data&&<div className="metric-grid">{[{ label: 'Jobs discovered',value: data.total_jobs_found,icon: Briefcase,note: 'Across the last 10 runs' },{ label: 'Applications sent',value: data.total_applied,icon: CheckCircle2,note: `${data.today_applied} today · ${data.daily_cap} daily cap` },{ label: 'Skipped',value: data.total_skipped,icon: ArrowRight,note: 'Filtered or passed over' },{ label: 'Needs attention',value: data.total_failed,icon: XCircle,note: 'Failed application attempts' }].map((m,i) => <article className={`overview-metric metric-${i}`} key={m.label}>
      <div>
        <span>{m.label}</span>
        <m.icon size={18} />
      </div>
      <strong>{m.value.toLocaleString()}</strong>
      <p>{m.note}</p>
    </article>)}</div>}
    <div className="overview-columns">
      <section className="workspace-panel">
        <div className="section-heading">
          <div>
            <h2>Application activity</h2>
            <p className="muted text-sm mt-1">Applied, skipped, and failed · Last 10 runs</p>
          </div>
          <TrendingUp size={20} className="accent" />
        </div>{chart.length? <>
          <div className="chart-legend">
            <span>
              <i style={{ background: '#319482' }} />Applied</span>
            <span>
              <i style={{ background: '#bd954b' }} />Skipped</span>
            <span>
              <i style={{ background: '#cc7373' }} />Failed</span>
          </div>
          <div className="activity-chart">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={chart}>
                <CartesianGrid vertical={false} stroke="var(--color-border)" />
                <XAxis dataKey="date" tick={{ fill: 'var(--color-text-secondary)',fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis allowDecimals={false} tick={{ fill: 'var(--color-text-secondary)',fontSize: 11 }} axisLine={false} tickLine={false} width={32} />
                <Tooltip contentStyle={{ background: 'var(--color-surface)',color: 'var(--color-text)',border: '1px solid var(--color-border)',borderRadius: 8 }} />
                <Bar dataKey="Applied" fill="#319482" radius={[3,3,0,0]} />
                <Bar dataKey="Skipped" fill="#bd954b" radius={[3,3,0,0]} />
                <Bar dataKey="Failed" fill="#cc7373" radius={[3,3,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>:<div className="overview-empty">
          <TrendingUp size={28} />
          <h3>{stats.isError? 'Activity is unavailable':'Your progress starts here'}</h3>
          <p>{stats.isError? 'Retry loading your activity above.':'Run your first search to see application activity here.'}</p>
          <Link className="text-link" to="/agent-control">Open command center <ArrowRight size={15} />
          </Link>
        </div>}</section>
      <section className="workspace-panel run-brief">
        <p className="eyebrow">BEFORE YOUR NEXT RUN</p>
        <h2>Stay in control<br />of every application.</h2>
        <p className="muted">Review your preferences and use dry run to inspect matches before sending applications.</p>
        <div className="run-fact">
          <span>Naukri session</span>
          <strong>{session.isLoading? 'Checking…':session.isError? 'Unavailable':session.data?.valid? 'Valid':'Connection needed'}</strong>
        </div>
        <div className="run-fact">
          <span>Application mode</span>
          <strong>{config.isLoading? 'Loading…':config.isError? 'Unavailable':config.data?.application.dry_run? 'Dry run':'Live'}</strong>
        </div>
        <div className="run-fact">
          <span>Matching configuration</span>
          <strong>{config.isLoading ? 'Loading…' : config.isError ? 'Unavailable' : !config.data?.ai.enable_matching ? 'Disabled' : config.data.ai.use_gemini && config.data.ai.has_api_key ? 'Gemini configured' : 'Local matching'}</strong>
        </div>
        <div className="run-fact">
          <span>Recorded runs</span>
          <strong>{metrics.isLoading? 'Loading…':metrics.isError? 'Unavailable':metrics.data?.total_runs??'—'}</strong>
        </div>
        <Link to="/agent-control" className="primary-button">Open command center <ArrowUpRight size={16} />
        </Link>
        <Link to="/linkedin" className="text-link mt-3">Manage LinkedIn separately <ArrowUpRight size={14} />
        </Link>
      </section>
    </div>
    <div className="overview-columns">
      <section className="workspace-panel">
        <div className="section-heading">
          <h2>Recent applications</h2>
          <Link to="/applications" className="text-link">View all <ArrowUpRight size={14} />
          </Link>
        </div>{data?.recent_applications.length? <div className="activity-list">{data.recent_applications.map((a,i) => <div className="activity-row" key={i}>
          <span className="company-monogram">{a.company?.slice(0,1)||'J'}</span>
          <div>
            <strong>{a.job_title}</strong>
            <p>{a.company} · Match {(a.match_score??0).toFixed(0)}</p>
          </div>
          <StatusBadge status={a.status} />
        </div>)}</div>:<div className="compact-empty">
          <FileText size={23} />
          <h3>{stats.isError? 'Applications unavailable':'No applications yet'}</h3>
          <p>{stats.isError? 'Retry loading your activity above.':'Your application history will appear after your first run.'}</p>
        </div>}</section>
      <section className="workspace-panel">
        <div className="section-heading">
          <h2>Recent runs</h2>
          <Link to="/run-logs" className="text-link">View history <ArrowUpRight size={14} />
          </Link>
        </div>{data?.recent_runs.length? <div className="activity-list">{data.recent_runs.map(r => <div key={r.id} className="activity-row">
          <div>
            <strong>{r.keywords||'Search run'}</strong>
            <p>{r.started_at.slice(0,16).replace('T',' ')} · {r.applied} applied</p>
          </div>
          <StatusBadge status={r.status} />
        </div>)}</div>:<div className="compact-empty">
          <Search size={23} />
          <h3>{stats.isError? 'Run history unavailable':'A fresh start'}</h3>
          <p>{stats.isError? 'Retry loading your activity above.':'Completed searches and run details will be recorded here.'}</p>
        </div>}</section>
    </div>
    <footer className="overview-export">
      <div>
        <strong>Your data, ready to review.</strong>
        <p className="muted text-sm">Export your application history or a snapshot of your statistics.</p>
      </div>
      <div className="flex gap-2 flex-wrap">
        <button className="secondary-button" disabled={exporting} onClick={() => exportData('/export/applications/csv','applications.csv')}>
          <Download size={15} />{exporting? 'Exporting…':'Applications CSV'}</button>
        <button className="secondary-button" disabled={exporting} onClick={() => exportData('/export/stats/json','stats.json')}>
          <Download size={15} />Statistics JSON</button>
      </div>{exportError&&<p className="notice-error w-full" role="alert">{exportError}</p>}</footer>
  </div>;
}
