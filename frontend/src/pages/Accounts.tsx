import { useState, useEffect } from 'react';
import { Users, Plus, Trash2, Star, Power, PowerOff, Loader2 } from 'lucide-react';
import { api, type AccountItem } from '../lib/api';

export default function Accounts() {
  const [accounts, setAccounts] = useState<AccountItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [isPrimary, setIsPrimary] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => { fetchAccounts(); }, []);

  const fetchAccounts = async () => {
    setLoading(true);
    try {
      const r = await api.accounts.list();
      setAccounts(r.items);
    } catch {} finally { setLoading(false); }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password) {
      setError('Email and password are required');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await api.accounts.create({ email: email.trim(), password, name, is_primary: isPrimary });
      setShowForm(false);
      setEmail('');
      setPassword('');
      setName('');
      setIsPrimary(false);
      await fetchAccounts();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create account');
    } finally { setSaving(false); }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this account?')) return;
    try {
      await api.accounts.delete(id);
      await fetchAccounts();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Delete failed');
    }
  };

  const handleActivate = async (id: number) => {
    try {
      await api.accounts.activate(id);
      await fetchAccounts();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Activation failed');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#38bdf8]" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Users className="w-6 h-6 text-[#38bdf8]" />
            Naukri Accounts
          </h1>
          <p className="text-[#94a3b8] mt-1">Manage multiple Naukri accounts for the agent</p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center justify-center gap-1.5 px-4 py-2 bg-[#38bdf8] text-[#0f172a] rounded-lg text-sm font-medium hover:bg-[#7dd3fc] transition-colors w-full sm:w-auto"
        >
          <Plus className="w-4 h-4" />
          Add Account
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="bg-[#1e293b] rounded-xl border border-[#334155] p-5 space-y-4">
          <h2 className="text-lg font-semibold text-white">New Account</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <input
              type="email" placeholder="Naukri Email" value={email}
              onChange={e => setEmail(e.target.value)}
              className="w-full px-3 py-2 bg-[#0f172a] border border-[#334155] rounded-lg text-white text-sm placeholder-[#64748b] focus:outline-none focus:border-[#38bdf8]"
            />
            <input
              type="password" placeholder="Password" value={password}
              onChange={e => setPassword(e.target.value)}
              className="w-full px-3 py-2 bg-[#0f172a] border border-[#334155] rounded-lg text-white text-sm placeholder-[#64748b] focus:outline-none focus:border-[#38bdf8]"
            />
            <input
              type="text" placeholder="Display Name (optional)" value={name}
              onChange={e => setName(e.target.value)}
              className="w-full px-3 py-2 bg-[#0f172a] border border-[#334155] rounded-lg text-white text-sm placeholder-[#64748b] focus:outline-none focus:border-[#38bdf8]"
            />
            <label className="flex items-center gap-2 text-sm text-[#94a3b8]">
              <input type="checkbox" checked={isPrimary} onChange={e => setIsPrimary(e.target.checked)}
                className="w-4 h-4 rounded border-[#334155] bg-[#0f172a] text-[#38bdf8]" />
              Set as primary
            </label>
          </div>
          {error && <p className="text-sm text-red-400">{error}</p>}
          <div className="flex flex-wrap gap-2 justify-end">
            <button type="button" onClick={() => setShowForm(false)}
              className="px-3 py-2 text-sm text-[#94a3b8] border border-[#334155] rounded-lg hover:bg-[#334155]">Cancel</button>
            <button type="submit" disabled={saving}
              className="px-4 py-2 text-sm bg-[#38bdf8] text-[#0f172a] rounded-lg font-medium hover:bg-[#7dd3fc] disabled:opacity-50 flex items-center gap-1.5">
              {saving && <Loader2 className="w-4 h-4 animate-spin" />}
              Save
            </button>
          </div>
        </form>
      )}

      <div className="grid gap-4">
        {accounts.map(acc => (
          <div key={acc.id} className="bg-[#1e293b] rounded-xl border border-[#334155] p-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-4 min-w-0">
              <div className={`p-2.5 rounded-lg ${acc.is_active ? 'bg-green-500/10' : 'bg-[#334155]'}`}>
                <Users className={`w-5 h-5 ${acc.is_active ? 'text-green-400' : 'text-[#64748b]'}`} />
              </div>
              <div>
                <p className="text-sm font-medium text-white flex items-center gap-2">
                  {acc.name || acc.email}
                  {acc.is_primary && <Star className="w-3.5 h-3.5 text-yellow-400" />}
                </p>
                <p className="text-xs text-[#94a3b8]">{acc.email}</p>
                {acc.last_used_at && (
                  <p className="text-xs text-[#64748b] mt-0.5">Last used: {new Date(acc.last_used_at).toLocaleDateString()}</p>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => handleActivate(acc.id)}
                disabled={acc.is_active}
                className={`p-2 rounded-lg transition-colors ${
                  acc.is_active ? 'bg-green-500/20 text-green-400' : 'text-[#64748b] hover:text-white hover:bg-[#334155]'
                }`}
                title={acc.is_active ? 'Active' : 'Activate'}
              >
                {acc.is_active ? <Power className="w-4 h-4" /> : <PowerOff className="w-4 h-4" />}
              </button>
              {!acc.is_primary && (
                <button
                  onClick={() => handleDelete(acc.id)}
                  className="p-2 text-[#64748b] hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
                  title="Delete"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>
        ))}
        {accounts.length === 0 && (
          <div className="text-center py-12 text-[#64748b]">
            <Users className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>No accounts configured. Add your first Naukri account.</p>
          </div>
        )}
      </div>
    </div>
  );
}
