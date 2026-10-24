import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';

const sourceLabels: Record<string, string> = {
  confirmed: 'Confirmed by you', profile: 'From your profile',
  technical: 'Technical explanation', ai_suggestion: 'AI suggestion · needs confirmation',
};

export default function AnswerMemory() {
  const client = useQueryClient();
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('');
  const [editing, setEditing] = useState('');
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [failure, setFailure] = useState('');
  useEffect(() => {
    const timer = setTimeout(() => setFilter(search.trim()), 300);
    return () => clearTimeout(timer);
  }, [search]);
  const {data, error, isPending, refetch} = useQuery({
    queryKey: ['screening-memory', filter], queryFn: () => api.screening.memory(filter), refetchInterval: 30000,
  });
  const change = async (id: string, forget = false) => {
    setBusy(true); setFailure(''); setMessage('');
    try {
      if (forget) await api.screening.forget(id);
      else await api.screening.save({[id]: draft.trim()});
      setMessage(forget ? 'Answer and matching variants forgotten. Profile facts can be learned again from your saved profile.' : 'Answer confirmed. Future applications will use this correction for the same question and units.');
      setEditing(''); setDraft('');
      await Promise.all([
        client.invalidateQueries({queryKey: ['screening-memory']}),
        client.invalidateQueries({queryKey: ['screening-questions']}),
      ]);
    } catch (err) { setFailure(err instanceof Error ? err.message : 'Could not update answer memory.'); }
    finally { setBusy(false); }
  };
  const inputClass = 'w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-2 text-sm text-[var(--color-text)]';
  return <details className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
    <summary className="cursor-pointer font-semibold">Answer memory {data && `(${data.total} saved)`}</summary>
    <div className="space-y-3 pt-3">
      <p className="text-sm text-[var(--color-text-secondary)]">Both agents reuse your confirmed answers and remember answers from your profile. Profile-derived answers refresh when your profile changes. AI suggestions need your confirmation before memory can reuse them. Job-specific answers stay with that job.</p>
      <div className="space-y-2">
        <label htmlFor="answer-memory-search" className="text-sm font-medium">Search remembered answers</label>
        <div className="flex flex-wrap items-center gap-2">
          <input id="answer-memory-search" type="search" aria-describedby="answer-memory-results" placeholder="Search questions to filter saved answers" maxLength={200} value={search} onChange={e => setSearch(e.target.value)} className={`${inputClass} min-w-0 flex-1`}/>
          {(search || filter) && <button className="secondary-button" onClick={() => {setSearch(''); setFilter('');}}>Clear search</button>}
        </div>
      </div>
      <p id="answer-memory-results" role="status" className="text-sm text-[var(--color-text-secondary)]">
        {data && !error && <>Showing {data.items.length} of {data.total} saved answers{filter && <> matching “{filter}”</>}.</>}
      </p>
      {isPending && <p role="status">Loading answer memory…</p>}
      {error && <p role="alert">Could not load answer memory. <button className="underline" onClick={() => refetch()}>Retry</button></p>}
      {data && !data.items.length && <p className="text-sm text-[var(--color-text-secondary)]">{filter ? 'No matching remembered answers.' : 'Answers will appear here as your agents fill forms or you confirm screening questions.'}</p>}
      {data?.items.map(item => <article key={item.id} className="border-t border-[var(--color-border)] pt-3 space-y-2">
        <p className="text-sm font-medium">{item.question}</p>
        <p className="text-xs text-[var(--color-text-secondary)]">{sourceLabels[item.source] ?? item.source} · {item.scope === 'job' ? 'This job only' : 'Across applications'} · Reused {item.use_count} time(s)</p>
        {editing === item.id ? <div className="space-y-2">
          <label htmlFor={`memory-${item.id}`} className="text-sm">Confirmed answer</label>
          {item.options.length ? <select id={`memory-${item.id}`} value={draft} disabled={busy} onChange={e => setDraft(e.target.value)} className={inputClass}>
            <option value="">Choose an answer</option>{item.options.map(option => <option key={option} value={option}>{option}</option>)}
          </select> : item.field_type === 'date' || item.field_type === 'number' ? <input id={`memory-${item.id}`} type={item.field_type} step="any" value={draft} onChange={e => setDraft(e.target.value)} disabled={busy} className={inputClass}/> :
            <textarea id={`memory-${item.id}`} rows={3} maxLength={2000} value={draft} onChange={e => setDraft(e.target.value)} disabled={busy} className={inputClass}/>}
          <button className="primary-button" disabled={busy || !draft.trim()} onClick={() => change(item.id)}>Confirm answer</button>
          <button className="secondary-button ml-2" disabled={busy} onClick={() => setEditing('')}>Cancel</button>
        </div> : <>
          <p className="whitespace-pre-wrap text-sm text-[var(--color-text-secondary)]">{item.answer}</p>
          <div className="flex gap-2">
            <button className="secondary-button" disabled={busy} onClick={() => {setEditing(item.id); setDraft(item.answer); setMessage(''); setFailure('');}}>Review or correct</button>
            <button className="secondary-button" disabled={busy} onClick={() => change(item.id, true)}>Forget answer</button>
          </div>
        </>}
      </article>)}
      {data?.items.length === 100 && <p className="text-xs text-[var(--color-text-secondary)]">Showing up to 100 matching answers. Refine your search to find older questions.</p>}
      {message && <p role="status" className="text-sm text-green-400">{message}</p>}
      {failure && <p role="alert" className="text-sm text-red-400">{failure}</p>}
    </div>
  </details>;
}
