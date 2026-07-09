import { useState, useEffect, useCallback } from 'react';
import { HelpCircle, Search, RefreshCw, Save, Trash2 } from 'lucide-react';
import { api, type ScreeningQuestionItem, type ScreeningQuestionStats } from '../lib/api';

type StatusFilter = 'pending' | 'all';

export default function ScreeningQuestions() {
  const [items, setItems] = useState<ScreeningQuestionItem[]>([]);
  const [stats, setStats] = useState<ScreeningQuestionStats | null>(null);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('pending');
  const [loading, setLoading] = useState(true);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [savingId, setSavingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [list, s] = await Promise.all([
        api.screeningQuestions.list(statusFilter, search),
        api.screeningQuestions.stats(),
      ]);
      setItems(list.items);
      setStats(s);
      setDrafts(prev => {
        const next = { ...prev };
        for (const item of list.items) {
          if (next[item.id] === undefined) {
            next[item.id] = item.answer_text || '';
          }
        }
        return next;
      });
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to load screening questions' });
    } finally {
      setLoading(false);
    }
  }, [statusFilter, search]);

  useEffect(() => {
    setLoading(true);
    fetchData();
  }, [fetchData]);

  const handleSave = async (id: number) => {
    const answer = (drafts[id] || '').trim();
    if (!answer) {
      setMessage({ type: 'error', text: 'Answer cannot be empty' });
      return;
    }
    setSavingId(id);
    setMessage(null);
    try {
      await api.screeningQuestions.save(id, answer);
      setMessage({ type: 'success', text: 'Answer saved. It will be reused on the next apply.' });
      await fetchData();
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to save answer' });
    } finally {
      setSavingId(null);
    }
  };

  const handleDelete = async (id: number) => {
    setDeletingId(id);
    setMessage(null);
    try {
      await api.screeningQuestions.delete(id);
      setMessage({ type: 'success', text: 'Question removed' });
      await fetchData();
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to delete question' });
    } finally {
      setDeletingId(null);
    }
  };

  const formatOptions = (item: ScreeningQuestionItem) => {
    if (!item.options?.length) return '—';
    return item.options
      .map(o => o.text || o.value || '')
      .filter(Boolean)
      .join(', ');
  };

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
          <HelpCircle className="w-6 h-6 text-primary" />
          Screening Q&amp;A
        </h1>
        <p className="text-secondary mt-1">
          Review screening questions the agent could not answer. Save answers here to reuse on future applications.
        </p>
      </div>

      {stats && (
        <div className="grid grid-cols-4 gap-4">
          <div className="bg-surface rounded-xl border border-border p-4 text-center">
            <p className="text-2xl font-bold text-amber-400">{stats.pending}</p>
            <p className="text-xs text-secondary mt-1">Pending</p>
          </div>
          <div className="bg-surface rounded-xl border border-border p-4 text-center">
            <p className="text-2xl font-bold text-green-400">{stats.answered}</p>
            <p className="text-xs text-secondary mt-1">Answered</p>
          </div>
          <div className="bg-surface rounded-xl border border-border p-4 text-center">
            <p className="text-2xl font-bold text-text">{stats.total}</p>
            <p className="text-xs text-secondary mt-1">Total</p>
          </div>
          <div className="bg-surface rounded-xl border border-border p-4 text-center">
            <p className="text-2xl font-bold text-red-400">{stats.total_failures}</p>
            <p className="text-xs text-secondary mt-1">Total Failures</p>
          </div>
        </div>
      )}

      {message && (
        <div
          className={`rounded-lg px-4 py-3 text-sm ${
            message.type === 'success'
              ? 'bg-green-500/10 text-green-400 border border-green-500/30'
              : 'bg-red-500/10 text-red-400 border border-red-500/30'
          }`}
        >
          {message.text}
        </div>
      )}

      <div className="bg-surface rounded-xl border border-border p-5">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
          <div className="flex items-center gap-2">
            {(['pending', 'all'] as StatusFilter[]).map(filter => (
              <button
                key={filter}
                onClick={() => setStatusFilter(filter)}
                className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                  statusFilter === filter
                    ? 'bg-primary text-white'
                    : 'bg-surface-hover text-secondary hover:text-text'
                }`}
              >
                {filter === 'pending' ? 'Pending' : 'All'}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-3 flex-1 max-w-md">
            <div className="flex items-center gap-3 bg-bg border border-border rounded-lg px-4 py-2 flex-1">
              <Search className="w-5 h-5 text-muted" />
              <input
                type="text"
                placeholder="Search questions..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="bg-transparent border-none outline-none text-text placeholder:text-muted w-full text-sm"
              />
            </div>
            <button
              onClick={fetchData}
              className="flex items-center gap-1.5 px-3 py-2 bg-surface-hover hover:bg-surface-hover text-text rounded-lg text-sm transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              Refresh
            </button>
          </div>
        </div>

        {items.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-secondary border-b border-border">
                  <th className="text-left py-2 px-3">Question</th>
                  <th className="text-left py-2 px-3">Type</th>
                  <th className="text-left py-2 px-3">Options</th>
                  <th className="text-left py-2 px-3">Last Job</th>
                  <th className="text-center py-2 px-3">Failures</th>
                  <th className="text-left py-2 px-3 min-w-[220px]">Answer</th>
                  <th className="text-right py-2 px-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map(item => (
                  <tr key={item.id} className="border-b border-border/50 hover:bg-surface-hover/30 align-top">
                    <td className="py-3 px-3 text-text max-w-[280px]">{item.question_text}</td>
                    <td className="py-3 px-3 text-secondary">{item.question_type}</td>
                    <td className="py-3 px-3 text-secondary max-w-[180px] truncate" title={formatOptions(item)}>
                      {formatOptions(item)}
                    </td>
                    <td className="py-3 px-3 text-secondary max-w-[180px]">
                      {item.last_job_title ? (
                        <span>
                          {item.last_job_title}
                          {item.last_job_company ? ` @ ${item.last_job_company}` : ''}
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="py-3 px-3 text-center">
                      <span className={item.failure_count > 1 ? 'text-red-400 font-semibold' : 'text-secondary'}>
                        {item.failure_count}
                      </span>
                    </td>
                    <td className="py-3 px-3">
                      <input
                        type="text"
                        value={drafts[item.id] ?? ''}
                        onChange={e =>
                          setDrafts(prev => ({ ...prev, [item.id]: e.target.value }))
                        }
                        placeholder="Enter your answer..."
                        className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-text text-sm outline-none focus:border-primary"
                      />
                      {item.status === 'answered' && item.source === 'user' && (
                        <p className="text-xs text-green-400 mt-1">Saved answer</p>
                      )}
                    </td>
                    <td className="py-3 px-3">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => handleSave(item.id)}
                          disabled={savingId === item.id}
                          className="flex items-center gap-1 px-2.5 py-1.5 bg-primary hover:bg-primary/90 disabled:opacity-50 text-white rounded-lg text-xs transition-colors"
                        >
                          <Save className="w-3.5 h-3.5" />
                          {savingId === item.id ? 'Saving...' : 'Save'}
                        </button>
                        <button
                          onClick={() => handleDelete(item.id)}
                          disabled={deletingId === item.id}
                          className="flex items-center gap-1 px-2.5 py-1.5 bg-red-600/80 hover:bg-red-600 disabled:opacity-50 text-white rounded-lg text-xs transition-colors"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-secondary text-center py-10">
            {statusFilter === 'pending'
              ? 'No pending screening questions. Failed questions will appear here after apply runs.'
              : 'No screening questions found.'}
          </p>
        )}
      </div>
    </div>
  );
}
