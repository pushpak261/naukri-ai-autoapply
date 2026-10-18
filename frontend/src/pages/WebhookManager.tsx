import { useState, useEffect } from 'react';
import { Webhook, Plus, Trash2, TestTube, Power, PowerOff, Loader2 } from 'lucide-react';
import { api, type WebhookItem } from '../lib/api';

const EVENT_OPTIONS = [
  { value: 'application.created', label: 'Application Submitted' },
  { value: 'application.failed', label: 'Application Failed' },
  { value: 'run.completed', label: 'Agent Run Completed' },
  { value: 'scam.detected', label: 'Scam Detected' },
  { value: 'match.found', label: 'High Match Found' },
];

export default function WebhookManager() {
  const [webhooks, setWebhooks] = useState<WebhookItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [secret, setSecret] = useState('');
  const [events, setEvents] = useState<string[]>(['application.created']);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<number | null>(null);
  const [error, setError] = useState('');

  useEffect(() => { fetchWebhooks(); }, []);

  const fetchWebhooks = async () => {
    setLoading(true);
    setError('');
    try {
      const r = await api.webhooks.list();
      setWebhooks(r.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load webhooks. Please retry.');
    } finally { setLoading(false); }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !url.trim()) {
      setError('Name and URL are required');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await api.webhooks.create({
        name: name.trim(),
        url: url.trim(),
        secret,
        events: events.join(','),
      });
      setShowForm(false);
      setName(''); setUrl(''); setSecret(''); setEvents(['application.created']);
      await fetchWebhooks();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create webhook');
    } finally { setSaving(false); }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this webhook?')) return;
    try {
      await api.webhooks.delete(id);
      await fetchWebhooks();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Delete failed');
    }
  };

  const handleTest = async (id: number) => {
    setTesting(id);
    try {
      const r = await api.webhooks.test(id);
      alert(`Test sent! Response: ${r.result?.status || r.result?.error || 'unknown'}`);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Test failed');
    } finally { setTesting(null); }
  };

  const toggleEvent = (ev: string) => {
    setEvents(prev => prev.includes(ev) ? prev.filter(e => e !== ev) : [...prev, ev]);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[var(--color-primary)]" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[var(--color-text)] flex items-center gap-2">
            <Webhook className="w-6 h-6 text-[var(--color-primary)]" />
            Webhooks
          </h1>
          <p className="text-[var(--color-text-secondary)] mt-1">Send event notifications to external services</p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center justify-center gap-1.5 px-4 py-2 bg-[#38bdf8] text-[#0f172a] rounded-lg text-sm font-medium hover:bg-[#7dd3fc] transition-colors w-full sm:w-auto"
        >
          <Plus className="w-4 h-4" />
          Add Webhook
        </button>
      </div>

      {error && !showForm && <div role="alert" className="text-red-400"><p>{error}</p><button onClick={fetchWebhooks}>Retry loading webhooks</button></div>}
      {showForm && (
        <form onSubmit={handleCreate} className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-5 space-y-4">
          <h2 className="text-lg font-semibold text-[var(--color-text)]">New Webhook</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <input type="text" placeholder="Webhook Name" value={name} onChange={e => setName(e.target.value)}
              className="w-full px-3 py-2 bg-[var(--color-bg)] border border-[var(--color-border)] rounded-lg text-[var(--color-text)] text-sm placeholder-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-primary)]" />
            <input type="url" placeholder="URL (https://...)" value={url} onChange={e => setUrl(e.target.value)}
              className="w-full px-3 py-2 bg-[var(--color-bg)] border border-[var(--color-border)] rounded-lg text-[var(--color-text)] text-sm placeholder-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-primary)]" />
            <input type="text" placeholder="Secret (optional, for HMAC signing)" value={secret} onChange={e => setSecret(e.target.value)}
              className="w-full px-3 py-2 bg-[var(--color-bg)] border border-[var(--color-border)] rounded-lg text-[var(--color-text)] text-sm placeholder-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-primary)]" />
          </div>
          <div>
            <p className="text-sm text-[var(--color-text-secondary)] mb-2">Events to subscribe to:</p>
            <div className="flex flex-wrap gap-2">
              {EVENT_OPTIONS.map(opt => (
                <label key={opt.value} className="flex items-center gap-1.5 text-sm text-[var(--color-text-secondary)] cursor-pointer">
                  <input type="checkbox" checked={events.includes(opt.value)} onChange={() => toggleEvent(opt.value)}
                    className="w-4 h-4 rounded border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-primary)]" />
                  {opt.label}
                </label>
              ))}
            </div>
          </div>
          {error && <p className="text-sm text-red-400">{error}</p>}
          <div className="flex flex-wrap gap-2 justify-end">
            <button type="button" onClick={() => setShowForm(false)}
              className="px-3 py-2 text-sm text-[var(--color-text-secondary)] border border-[var(--color-border)] rounded-lg hover:bg-[var(--color-surface-hover)]">Cancel</button>
            <button type="submit" disabled={saving}
              className="px-4 py-2 text-sm bg-[#38bdf8] text-[#0f172a] rounded-lg font-medium hover:bg-[#7dd3fc] disabled:opacity-50 flex items-center gap-1.5">
              {saving && <Loader2 className="w-4 h-4 animate-spin" />}
              Save
            </button>
          </div>
        </form>
      )}

      <div className="grid gap-4">
        {webhooks.map(wh => (
          <div key={wh.id} className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-3">
              <div className="flex items-center gap-3 min-w-0">
                <div className={`p-2 rounded-lg ${wh.is_active ? 'bg-[#38bdf8]/10' : 'bg-[var(--color-surface-hover)]'}`}>
                  <Webhook className={`w-5 h-5 ${wh.is_active ? 'text-[var(--color-primary)]' : 'text-[var(--color-text-muted)]'}`} />
                </div>
                <div>
                  <p className="text-sm font-medium text-[var(--color-text)]">{wh.name}</p>
                  <p className="text-xs text-[var(--color-text-secondary)] font-mono truncate max-w-md">{wh.url}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => handleTest(wh.id)} disabled={testing === wh.id}
                  className="p-2 text-[var(--color-text-muted)] hover:text-[var(--color-primary)] hover:bg-[#38bdf8]/10 rounded-lg transition-colors" title="Test">
                  {testing === wh.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <TestTube className="w-4 h-4" />}
                </button>
                <button onClick={() => handleDelete(wh.id)}
                  className="p-2 text-[var(--color-text-muted)] hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors" title="Delete">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
            <div className="flex items-center gap-4 text-xs text-[var(--color-text-muted)]">
              <span className={`flex items-center gap-1 ${wh.is_active ? 'text-green-400' : ''}`}>
                {wh.is_active ? <Power className="w-3 h-3" /> : <PowerOff className="w-3 h-3" />}
                {wh.is_active ? 'Active' : 'Inactive'}
              </span>
              <span>Events: {wh.events.join(', ')}</span>
              {wh.failure_count > 0 && <span className="text-red-400">{wh.failure_count} failures</span>}
              {wh.last_triggered_at && <span>Last: {new Date(wh.last_triggered_at).toLocaleString()}</span>}
            </div>
          </div>
        ))}
        {webhooks.length === 0 && (
          <div className="text-center py-12 text-[var(--color-text-muted)]">
            <Webhook className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>No webhooks configured. Add one to receive event notifications.</p>
          </div>
        )}
      </div>
    </div>
  );
}
