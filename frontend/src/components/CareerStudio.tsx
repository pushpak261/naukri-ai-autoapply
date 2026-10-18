import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { BookOpen, Download, Sparkles } from 'lucide-react';
import { api, type CareerArtifact, type InterviewFeedback } from '../lib/api';
import { useAuth } from '../lib/AuthContext';

export default function CareerStudio({ jobId }: { jobId?: number }) {
  const { user } = useAuth();
  const [selected, setSelected] = useState('');
  const [artifact, setArtifact] = useState<CareerArtifact | null>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [question, setQuestion] = useState(0);
  const [answer, setAnswer] = useState('');
  const [feedback, setFeedback] = useState<InterviewFeedback | null>(null);
  const pending = useRef<AbortController | null>(null);
  const jobs = useQuery({queryKey:['studio-jobs', user?.email], queryFn:api.copilotOpportunities, enabled: !jobId});
  const history = useQuery({queryKey:['studio-history', user?.email, jobId], queryFn:() => api.careerStudio.history(jobId)});
  const activeJob = jobId ?? (selected ? Number(selected) : undefined);
  useEffect(() => {
    setArtifact(null); setFeedback(null); setAnswer(''); setQuestion(0); setBusy(''); setError('');
    return () => { pending.current?.abort(); pending.current = null; };
  }, [jobId, user?.email]);

  async function run(label: string, action: (signal: AbortSignal) => Promise<void>) {
    if (pending.current) return;
    const controller = new AbortController(); pending.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 110_000);
    setBusy(label); setError('');
    try { await action(controller.signal); }
    catch (e) { if (pending.current === controller) setError(controller.signal.aborted ? 'Request timed out. Please retry.' : e instanceof Error ? e.message : 'Request failed. Please retry.'); }
    finally { window.clearTimeout(timeout); if (pending.current === controller) {pending.current = null; setBusy('');} }
  }
  function show(item: CareerArtifact) {setArtifact(item); setQuestion(0); setAnswer(''); setFeedback(null);}
  function generate(kind: CareerArtifact['kind']) {
    void run('Creating with Gemini…', async signal => {
      const item = await api.careerStudio.generate(kind, kind === 'strategy' ? undefined : activeJob, signal);
      if (!signal.aborted) {show(item); void history.refetch();}
    });
  }
  function download() {
    if (!artifact) return;
    const text = [`# ${artifact.title}`, artifact.summary, ...artifact.sections.flatMap(section => [`## ${section.heading}`, section.content, ...section.evidence.map(e => `> ${e.source}${e.job_id ? ` #${e.job_id}` : ''}: ${e.quote}`)]), ...artifact.questions.map(q => `## ${q.question}\nWhat to demonstrate: ${q.looking_for}`), ...artifact.daily_plan.map(task => `## Day ${task.day}\n${task.action}\n${task.rationale}`), '## Details to verify', ...artifact.missing_information.map(item => `- ${item}`), `Generated ${artifact.created_at} with ${artifact.model}. Review all claims before use.`].join('\n\n');
    const url = URL.createObjectURL(new Blob([text], {type:'text/markdown;charset=utf-8'}));
    const link = document.createElement('a'); link.href = url; link.download = `ApplyOS-${artifact.kind}-${artifact.id}.md`; link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <section aria-label="Career Studio" className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-6 space-y-5">
    <div><p className="eyebrow flex items-center gap-2"><Sparkles size={15} />CAREER STUDIO</p><h2 className="text-xl font-semibold mt-2">From opportunity to prepared candidate.</h2><p className="text-sm text-[var(--color-text-secondary)] mt-2">Create an evidence-linked application pack, rehearse an interview, or plan your next seven days. Uses your saved resume and real listings. Relevant details and practice answers are sent to Gemini only when you request generation or feedback.</p></div>
    {!jobId && <div><label htmlFor="studio-job" className="block text-sm mb-2">Choose a saved role for your pack or rehearsal</label><select id="studio-job" className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3 text-sm" value={selected} disabled={!!busy} onChange={e => {setSelected(e.target.value); setArtifact(null); setFeedback(null); setAnswer('');}}><option value="">Select a role</option>{jobs.data?.opportunities.map(job => <option key={job.id} value={job.id}>{job.title} · {job.company}</option>)}</select>{jobs.isError && <p role="alert" className="text-sm text-red-400">Could not load saved roles. <button className="underline" onClick={() => void jobs.refetch()}>Retry</button></p>}{jobs.data?.opportunities.length === 0 && <p className="text-sm mt-2">No listings yet. <Link to="/agent-control" className="underline">Run a search</Link> to collect real roles.</p>}</div>}
    <div className="flex flex-wrap gap-3"><button className="primary-button" disabled={!!busy || !activeJob} onClick={() => generate('application')}>Build application pack</button><button className="secondary-button" disabled={!!busy || !activeJob} onClick={() => generate('interview')}>Start interview rehearsal</button><button className="secondary-button" disabled={!!busy} onClick={() => generate('strategy')}>Create 7-day search plan</button></div>
    {busy && <p role="status" className="text-sm text-[var(--color-primary)]">{busy}</p>}
    {error && <p role="alert" className="text-sm text-red-400">{error} <Link to="/config#ai-settings" className="underline">AI settings</Link></p>}
    <div><label htmlFor="studio-history" className="text-sm block mb-2 flex items-center gap-2"><BookOpen size={15} />Saved work</label><select id="studio-history" className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-2 text-sm" value={artifact?.id ?? ''} disabled={!!busy} onChange={e => {const id=e.target.value; if (!id) {setArtifact(null); return;} void run('Opening saved work…', async signal => {const item=await api.careerStudio.load(id,signal); if (!signal.aborted) show(item);});}}><option value="">{history.isPending ? 'Loading saved work…' : 'Open a saved pack, rehearsal or plan'}</option>{history.data?.items.map(item => <option value={item.id} key={item.id}>{item.title} · {new Date(item.created_at).toLocaleDateString()}</option>)}</select>{history.isError && <p role="alert" className="text-sm text-red-400">Saved work could not load. <button className="underline" onClick={() => void history.refetch()}>Retry</button></p>}</div>
    {artifact && <article className="space-y-5 border-t border-[var(--color-border)] pt-5" aria-live="polite"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-lg font-semibold">{artifact.title}</h3><p className="text-xs text-[var(--color-text-secondary)] mt-1">{artifact.model} · {new Date(artifact.created_at).toLocaleString()} · Review before use</p></div><button className="secondary-button" onClick={download}><Download size={15} />Export Markdown</button></div><p className="text-sm leading-relaxed">{artifact.summary}</p>
      {artifact.sections.map((section,i) => <section key={i} className="rounded-lg bg-[var(--color-bg)] p-4 space-y-3"><h4 className="font-semibold">{section.heading}</h4><p className="whitespace-pre-wrap text-sm leading-relaxed">{section.content}</p><details className="text-xs text-[var(--color-text-secondary)]"><summary className="cursor-pointer">View checked source quotes</summary>{section.evidence.map((e,j) => <blockquote className="mt-3 border-l-2 border-[var(--color-primary)] pl-3 whitespace-pre-wrap" key={j}>{e.quote}<footer className="mt-1">{e.source === 'resume' ? 'Saved resume' : <Link to={`/jobs/${e.job_id}`} className="underline">Saved job #{e.job_id}</Link>}</footer></blockquote>)}</details></section>)}
      {artifact.daily_plan.length > 0 && <section><h4 className="font-semibold">Your seven-day action plan</h4><ol className="grid sm:grid-cols-2 gap-3 mt-3">{[...artifact.daily_plan].sort((a,b) => a.day-b.day).map(task => <li key={task.day} className="p-4 rounded-lg border border-[var(--color-border)]"><p className="text-xs font-semibold text-[var(--color-primary)]">DAY {task.day}</p><p className="text-sm font-semibold mt-2">{task.action}</p><p className="text-xs text-[var(--color-text-secondary)] mt-2">{task.rationale}</p></li>)}</ol></section>}
      {artifact.missing_information.length > 0 && <div><h4 className="font-semibold text-sm">Details to verify or add</h4><ul className="list-disc pl-5 text-sm space-y-1 mt-2">{artifact.missing_information.map((item,i) => <li key={i}>{item}</li>)}</ul></div>}
      {artifact.kind === 'interview' && artifact.questions.length > 0 && <section className="space-y-3"><h4 className="font-semibold">Practice your answer</h4><label htmlFor="studio-question" className="text-sm block">Interview question</label><select id="studio-question" disabled={!!busy} className="w-full border border-[var(--color-border)] rounded p-2 bg-[var(--color-bg)]" value={question} onChange={e => {setQuestion(Number(e.target.value)); setAnswer(''); setFeedback(null);}}>{artifact.questions.map((q,i) => <option key={i} value={i}>{i+1}. {q.question}</option>)}</select><p className="text-sm">{artifact.questions[question].question}</p><details className="text-sm"><summary className="cursor-pointer">What to demonstrate</summary><p className="mt-2">{artifact.questions[question].looking_for}</p></details><label className="block text-sm" htmlFor="studio-answer">Your answer</label><textarea id="studio-answer" rows={6} maxLength={6000} disabled={!!busy} className="w-full rounded border border-[var(--color-border)] bg-[var(--color-bg)] p-3 text-sm" value={answer} onChange={e => {setAnswer(e.target.value); setFeedback(null);}} placeholder="Describe a real situation, your actions and the result. Unknown details can stay unknown."/><button className="primary-button" disabled={!!busy || answer.trim().length < 20} onClick={() => void run('Reviewing your answer…', async signal => {const result=await api.careerStudio.practice(artifact.id,question,answer,signal); if (!signal.aborted) setFeedback(result);})}>Coach my answer</button>
        {feedback && <div aria-live="polite" className="space-y-3 rounded border border-[var(--color-border)] p-4 text-sm"><p>{feedback.assessment}</p><h5 className="font-semibold">What works</h5><ul className="list-disc pl-5">{feedback.strengths.map((item,i) => <li key={i}>{item}</li>)}</ul><h5 className="font-semibold">Try next</h5><ul className="list-disc pl-5">{feedback.improvements.map((item,i) => <li key={i}>{item}</li>)}</ul><p><strong>Follow-up:</strong> {feedback.follow_up_question}</p></div>}
      </section>}
      <p className="text-xs text-[var(--color-text-secondary)]">Source quotes are checked against saved evidence; generated recommendations still need your review. These tools do not submit applications, send messages or change your resume.</p>
    </article>}
  </section>;
}
