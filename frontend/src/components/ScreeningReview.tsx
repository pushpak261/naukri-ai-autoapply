import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { api } from '../lib/api';

export default function ScreeningReview() {
  const queryClient = useQueryClient();
  const { data, error, refetch } = useQuery({
    queryKey: ['screening-questions'], queryFn: api.screening.questions, refetchInterval: 10000,
  });
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [failure, setFailure] = useState('');
  const questions = data?.items ?? [];
  const save = async (queue: boolean) => {
    const entered = Object.fromEntries(questions.filter(q => q.field_type !== 'file' && answers[q.id]?.trim()).map(q => [q.id, answers[q.id].trim()]));
    if (!Object.keys(entered).length) { setFailure('Enter at least one confirmed answer.'); return; }
    setSaving(true); setFailure(''); setMessage('');
    try {
      const result = await api.screening.save(entered, queue);
      setMessage(`Saved ${result.saved} answer(s). ${result.queued ? `${result.queued} job(s) queued for the agent.` : 'These answers will be reused on the next attempt.'}`);
      setAnswers({});
      await Promise.all([
        queryClient.invalidateQueries({queryKey: ['screening-questions']}),
        queryClient.invalidateQueries({queryKey: ['applications']}),
      ]);
    } catch (err) { setFailure(err instanceof Error ? err.message : 'Could not save answers.'); }
    finally { setSaving(false); }
  };
  const inputClass = 'w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-2 text-sm text-[var(--color-text)]';
  return <section aria-labelledby="screening-review-title" className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 space-y-3">
    <h2 id="screening-review-title" className="font-semibold">Screening answers {questions.length > 0 && `(${questions.length} need your input)`}</h2>
    <p className="text-sm text-[var(--color-text-secondary)]">The Naukri agent answers from your saved facts and resume without Gemini. Confirm missing facts here once so it can complete future forms. It submits only after every detected question has an answer.</p>
    {error && <p role="alert" className="text-sm text-red-400">Could not load screening questions. <button className="underline" onClick={() => refetch()}>Retry</button></p>}
    {!error && data && !questions.length && <p className="text-sm text-[var(--color-text-secondary)]">No questions are waiting for your input. New questions from agent runs will appear here.</p>}
    {questions.map(q => <div key={q.id} className="space-y-2 border-t border-[var(--color-border)] pt-3">
      <label htmlFor={`screening-${q.id}`} className="block text-sm font-medium">{q.question}</label>
      {q.field_type === 'file' ? <p className="text-sm text-[var(--color-text-secondary)]">This attachment needs to be completed in the original job form.</p> : q.options.length ?
        <select id={`screening-${q.id}`} value={answers[q.id] ?? ''} onChange={e => setAnswers({...answers, [q.id]: e.target.value})} className={inputClass} disabled={saving}>
          <option value="">Choose your answer</option>{q.options.map(option => <option key={option} value={option}>{option}</option>)}
        </select> : q.field_type === 'date' || q.field_type === 'number' ?
        <input id={`screening-${q.id}`} type={q.field_type} step="any" value={answers[q.id] ?? ''} onChange={e => setAnswers({...answers, [q.id]: e.target.value})} className={inputClass} disabled={saving}/> :
        <textarea id={`screening-${q.id}`} rows={2} maxLength={2000} value={answers[q.id] ?? ''} onChange={e => setAnswers({...answers, [q.id]: e.target.value})} className={inputClass} disabled={saving}/>
      }
      {q.jobs.length > 0 && <p className="text-xs text-[var(--color-text-secondary)]">Needed for: {q.jobs.map((job, index) => <span key={job.job_id}>{index > 0 && ', '}<Link to={`/jobs/${job.job_id}`} className="underline">{job.title}</Link></span>)}</p>}
    </div>)}
    {questions.some(q => q.field_type !== 'file') && <div className="flex flex-wrap gap-2">
      <button className="secondary-button" disabled={saving} onClick={() => save(false)}>Save answers</button>
      <button className="primary-button" disabled={saving} onClick={() => save(true)}>{saving ? 'Saving…' : 'Save and retry ready jobs'}</button>
      <p className="w-full text-xs text-[var(--color-text-secondary)]">Retry starts eligible jobs once their known questions are resolved. Your filters, daily limit and Dry Run setting still apply.</p>
    </div>}
    {message && <p role="status" className="text-sm text-green-400">{message} <Link to="/agent-control" className="underline">Open Command Center</Link></p>}
    {failure && <p role="alert" className="text-sm text-red-400">{failure}</p>}
  </section>;
}
