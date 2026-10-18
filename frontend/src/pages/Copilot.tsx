import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ArrowRight, BookOpen, Check, ChevronRight, Copy, ListChecks, MapPin, RefreshCw, ShieldCheck, Sparkles, Target, X } from 'lucide-react';
import { api } from '../lib/api';
import { useAuth } from '../lib/AuthContext';
import CareerStudio from '../components/CareerStudio';

const panel = 'rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]';
const muted = 'text-[var(--color-text-secondary)]';
const labels = { prioritize: 'Worth a closer look', prepare: 'Prepare before applying', review: 'Review the evidence', already_in_progress: 'Already in progress' };

function EvidenceList({ title, items }: { title: string; items: string[] }) {
  return <section><h3 className="text-sm font-semibold mb-3">{title}</h3>{items.length ? <ul className={`space-y-2 text-sm leading-relaxed ${muted}`}>{items.map((item, i) => <li key={`${item}-${i}`} className="flex gap-2"><ChevronRight size={15} className="shrink-0 mt-1 text-[var(--color-primary)]" /><span>{item}</span></li>)}</ul> : <p className={`text-sm ${muted}`}>No evidence available yet.</p>}</section>;
}

export default function Copilot() {
  const { user } = useAuth();
  const [selected, setSelected] = useState<number | null>(null);
  const [copyStatus, setCopyStatus] = useState('');
  const briefPanel = useRef<HTMLElement>(null);
  const result = useQuery({ queryKey: ['copilot', user?.email], queryFn: api.copilotOpportunities });
  const brief = useQuery({ queryKey: ['copilot-brief', selected, user?.email], queryFn: () => api.copilotBrief(selected!), enabled: selected !== null });
  useEffect(() => { setSelected(null); setCopyStatus(''); }, [user?.email, result.dataUpdatedAt]);
  useEffect(() => {
    setCopyStatus('');
    if (selected !== null) {
      briefPanel.current?.scrollIntoView({ block: 'start' });
      briefPanel.current?.focus({ preventScroll: true });
    }
  }, [selected, brief.dataUpdatedAt, brief.isError]);
  const data = result.data;
  const copyDraft = async () => {
    try {
      await navigator.clipboard.writeText(brief.data?.outreach_draft ?? '');
      setCopyStatus('Draft copied. Personalize it before sending.');
    } catch {
      setCopyStatus('Copy unavailable. Select and copy the draft text below.');
    }
  };
  return <div className="space-y-6 text-[var(--color-text)]">
    <header className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
      <div><p className="flex items-center gap-2 text-xs font-semibold tracking-widest uppercase text-[var(--color-primary)]"><Sparkles size={15} /> Your next move, with context</p><h1 className="text-3xl font-bold mt-2 tracking-tight">Opportunity Copilot</h1><p className={`mt-2 max-w-2xl text-sm leading-relaxed ${muted}`}>Turn your profile and discovered jobs into a focused shortlist, clear skill priorities, and a practical preparation brief.</p></div>
      <button className="secondary-button shrink-0" onClick={() => { setSelected(null); void result.refetch(); }} disabled={result.isFetching}><RefreshCw size={15} className={result.isFetching ? 'animate-spin' : ''} />Refresh analysis</button>
    </header>
    <CareerStudio />
    <div className="flex gap-3 rounded-xl bg-[var(--color-primary)]/10 border border-[var(--color-primary)]/20 p-4 text-sm"><ShieldCheck className="shrink-0 text-[var(--color-primary)]" size={19} /><p className={muted}>Scores explain overlap with your saved profile. They are evidence-based heuristics, not hiring odds or an external AI assessment. Copilot never submits applications or sends messages.</p></div>
    {result.isPending ? <div className={`${panel} p-12 text-center`} role="status"><Sparkles className="animate-pulse mx-auto mb-3 text-[var(--color-primary)]" /><p>Reviewing your workspace evidence…</p></div> : result.isError ? <div className={`${panel} p-8`} role="alert"><h2 className="font-semibold">Your analysis could not load</h2><p className={`mt-2 text-sm ${muted}`}>{result.error.message}</p><button className="secondary-button mt-4" onClick={() => void result.refetch()}>Try again</button></div> : data && <>
      <div className="grid lg:grid-cols-[minmax(0,1fr)_320px] gap-6 items-start">
        <div className="space-y-5">
          {!data.profile_ready && <section className={`${panel} p-5 border-l-4 border-l-[var(--color-primary)]`}><h2 className="font-semibold">Give your shortlist a stronger foundation</h2><p className={`text-sm mt-2 mb-4 ${muted}`}>Add your skills and experience to your profile so Copilot can explain how each role connects to your background.</p><Link className="primary-button" to="/resume">Complete your profile <ArrowRight size={15} /></Link></section>}
          <div className="flex flex-wrap items-end justify-between gap-2"><h2 className="text-lg font-semibold">Your opportunity shortlist</h2><span className={`text-xs ${muted}`}>{data.total_reviewed} jobs reviewed · {data.opportunities.length} shown</span></div>
          {data.opportunities.length === 0 ? <section className={`${panel} p-10 text-center`}><Target size={30} className="mx-auto mb-4 text-[var(--color-primary)]" /><h3 className="font-semibold text-lg">A clearer shortlist starts with real jobs</h3><p className={`text-sm max-w-md mx-auto mt-2 mb-5 ${muted}`}>Discover roles from your workspace first. Your opportunities and preparation briefs will appear here as evidence becomes available.</p><Link className="primary-button" to="/jobs">Discover jobs <ArrowRight size={15} /></Link></section> : <ol className="space-y-4">{data.opportunities.map((job, index) => <li key={job.id} className={`${panel} overflow-hidden`}>
            <article className="p-5 sm:p-6"><div className="flex items-start gap-4"><div className="text-sm font-semibold text-[var(--color-text-muted)] pt-1 w-5 shrink-0">{String(index + 1).padStart(2, '0')}</div><div className="min-w-0 flex-1"><p className="text-xs text-[var(--color-primary)] font-semibold mb-2">{labels[job.recommendation]}</p><Link to={`/jobs/${job.id}`} className="text-lg font-semibold hover:underline break-words">{job.title}</Link><p className={`mt-1 text-sm ${muted}`}>{job.company} · {job.source}</p>{job.location && <p className={`flex items-center gap-1 mt-2 text-xs ${muted}`}><MapPin size={12} />{job.location}</p>}</div><div className="text-right shrink-0"><strong className="text-2xl tabular-nums text-[var(--color-primary)]">{job.score === null ? '—' : Math.round(job.score)}</strong><p className={`text-[11px] mt-1 ${muted}`}>evidence score</p><p className={`text-[11px] mt-1 capitalize ${muted}`}>{job.confidence} confidence</p></div></div>
              <div className="mt-5 grid sm:grid-cols-2 gap-5"><EvidenceList title="Why it surfaced" items={job.reasons} /><EvidenceList title="Check before applying" items={job.cautions} /></div>
              <div className="flex flex-wrap gap-2 mt-5">{job.matching_skills.map(skill => <span key={`match-${skill}`} className="text-xs px-2 py-1 rounded bg-[var(--color-primary)]/10 text-[var(--color-primary)]">✓ {skill}</span>)}{job.missing_skills.map(skill => <span key={`gap-${skill}`} className={`text-xs px-2 py-1 rounded border border-[var(--color-border)] ${muted}`}>Explore: {skill}</span>)}</div>
              <div className="flex flex-wrap justify-between gap-3 items-center border-t border-[var(--color-border)] mt-5 pt-4"><Link to={`/jobs/${job.id}`} className="text-sm font-semibold text-[var(--color-primary)] inline-flex items-center gap-1">Inspect role <ArrowRight size={14} /></Link><button className="secondary-button" onClick={() => setSelected(job.id)}><BookOpen size={15} />Prepare for this role</button></div>
            </article>
          </li>)}</ol>}
        </div>
        <aside className="space-y-5 lg:sticky lg:top-6">
          <section className={`${panel} p-5`}><div className="flex items-center gap-2 mb-4"><ListChecks size={18} className="text-[var(--color-primary)]" /><h2 className="font-semibold">Your next best steps</h2></div><ol className="space-y-5">{data.actions.map((action, index) => <li key={`${action.title}-${index}`}><Link to={action.href} className="text-sm font-semibold hover:underline inline-flex gap-2 items-center">{action.title}<ArrowRight size={13} /></Link><p className={`text-xs leading-relaxed mt-1 ${muted}`}>{action.detail}</p></li>)}</ol>{!data.actions.length && <p className={`text-sm ${muted}`}>Review a role to plan your next step.</p>}</section>
          <section className={`${panel} p-5`}><h2 className="font-semibold">Skills with the most reach</h2><p className={`text-xs leading-relaxed mt-2 ${muted}`}>Missing profile skills across the reviewed roles. Build evidence where it matters to you.</p><ul className="mt-4 divide-y divide-[var(--color-border)]">{data.skill_focus.map(item => <li key={item.skill} className="py-3 flex justify-between gap-3 text-sm"><span>{item.skill}</span><span className={`text-xs whitespace-nowrap ${muted}`}>{item.jobs} {item.jobs === 1 ? 'role' : 'roles'}</span></li>)}</ul>{!data.skill_focus.length && <p className={`text-sm mt-4 ${muted}`}>No repeated skill gaps identified in the available evidence.</p>}</section>
        </aside>
      </div>
    </>}
    {selected !== null && <section ref={briefPanel} tabIndex={-1} className={`${panel} p-5 sm:p-7 scroll-mt-6`} aria-label="Role preparation brief" aria-live="polite"><div className="flex items-start justify-between gap-4 mb-5"><div><p className="text-xs uppercase tracking-widest text-[var(--color-primary)] font-semibold">Role preparation</p><h2 className="text-xl font-semibold mt-1">{brief.data?.job.title ?? 'Your preparation brief'}</h2>{brief.data && <p className={`text-sm mt-1 ${muted}`}>{brief.data.job.company} · {brief.data.job.source}</p>}</div><button aria-label="Close preparation brief" className="secondary-button" onClick={() => setSelected(null)}><X size={16} /></button></div>
      {brief.isPending ? <p role="status" className={muted}>Preparing a brief from your saved profile and this role…</p> : brief.isError ? <div role="alert"><p className="text-sm">{brief.error.message}</p><button className="secondary-button mt-3" onClick={() => void brief.refetch()}>Retry brief</button></div> : brief.data && <><div className="grid md:grid-cols-2 gap-7"><EvidenceList title="Talking points to personalize" items={brief.data.talking_points} /><EvidenceList title="Questions to ask the recruiter" items={brief.data.questions} /><EvidenceList title="Your preparation checklist" items={brief.data.checklist} /><section><div className="flex flex-wrap justify-between items-center gap-2 mb-3"><h3 className="text-sm font-semibold">Your outreach starting point</h3><button className="secondary-button" onClick={() => void copyDraft()}><Copy size={14} />Copy draft</button></div><p className={`text-sm leading-relaxed whitespace-pre-wrap rounded-lg bg-[var(--color-bg)] p-4 border border-[var(--color-border)] ${muted}`}>{brief.data.outreach_draft}</p><p className={`text-xs mt-2 ${muted}`}>Review every claim and add your own examples before sharing.</p>{copyStatus && <p role="status" className="text-xs mt-3 flex gap-2 items-center"><Check size={13} />{copyStatus}</p>}</section></div><p className={`text-xs mt-6 pt-4 border-t border-[var(--color-border)] ${muted}`}>Prepared from workspace evidence using a local heuristic. No message has been sent.</p></>}
    </section>}
  </div>;
}
