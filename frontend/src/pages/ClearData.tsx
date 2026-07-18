import { useState } from 'react';
import { Trash2, AlertTriangle, Database, FileJson, FileText, LogOut, RefreshCw } from 'lucide-react';
import { api } from '../lib/api';

export default function ClearData() {
  const [clearing, setClearing] = useState(false);
  const [result, setResult] = useState<{ status: string; message: string; details: string[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmText, setConfirmText] = useState('');

  const handleClear = async () => {
    if (confirmText !== 'CLEAR') return;
    setClearing(true);
    setResult(null);
    setError(null);
    try {
      const r = await api.clearAll();
      setResult(r);
      setConfirmText('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to clear data');
    }
    setClearing(false);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Database className="w-6 h-6 text-red-400" />
          Clear All Data
        </h1>
        <p className="text-[#94a3b8] mt-1">Reset database, caches, sessions, and logs</p>
      </div>

      <div className="bg-[#1e293b] rounded-xl border border-red-500/30 p-6">
        <div className="flex items-start gap-3 mb-4">
          <AlertTriangle className="w-6 h-6 text-red-400 shrink-0 mt-0.5" />
          <div>
            <h2 className="text-lg font-semibold text-white">Danger Zone</h2>
            <p className="text-[#94a3b8] text-sm mt-1">
              This action will permanently delete all data. This cannot be undone.
            </p>
          </div>
        </div>

        <div className="space-y-3 mb-6">
          <h3 className="text-sm font-medium text-[#94a3b8]">The following will be deleted:</h3>
          <ul className="space-y-2">
            {[
              { icon: Database, label: 'All database tables (jobs, applications, run logs, accounts, webhooks, etc.)', color: 'text-red-400' },
              { icon: FileJson, label: 'Cache files (match cache, QA cache, metrics)', color: 'text-orange-400' },
              { icon: LogOut, label: 'All session files (Naukri & LinkedIn)', color: 'text-yellow-400' },
              { icon: FileText, label: 'Log files', color: 'text-blue-400' },
            ].map(({ icon: Icon, label, color }) => (
              <li key={label} className="flex items-center gap-2 text-sm text-[#cbd5e1]">
                <Icon className={`w-4 h-4 ${color} shrink-0`} />
                <span>{label}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 mb-6">
          <p className="text-sm text-red-300">
            This action is irreversible. Make sure to export or backup your data first.
          </p>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-[#94a3b8] mb-2">
              Type <span className="font-mono text-red-400">CLEAR</span> to confirm
            </label>
            <input
              type="text"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder="Type CLEAR to confirm"
              className="w-full max-w-xs px-3 py-2 bg-[#0f172a] border border-[#334155] rounded-lg text-white text-sm focus:outline-none focus:border-red-500 placeholder-[#64748b]"
            />
          </div>
          <button
            onClick={handleClear}
            disabled={clearing || confirmText !== 'CLEAR'}
            className="flex items-center gap-2 px-5 py-2.5 bg-red-600 hover:bg-red-700 disabled:bg-gray-700 text-white disabled:text-[#64748b] rounded-lg text-sm font-medium transition-colors"
          >
            {clearing ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Trash2 className="w-4 h-4" />
            )}
            {clearing ? 'Clearing...' : 'Clear All Data'}
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-lg text-sm bg-red-500/10 text-red-400 border border-red-500/30">
          <AlertTriangle className="w-4 h-4" />
          {error}
        </div>
      )}

      {result && (
        <div className="bg-[#1e293b] rounded-xl border border-green-500/30 p-5 space-y-3">
          <div className="flex items-center gap-2 text-green-400">
            <Database className="w-5 h-5" />
            <span className="font-medium">{result.message}</span>
          </div>
          {result.details.length > 0 && (
            <div>
              <p className="text-sm text-[#94a3b8] mb-2">Details:</p>
              <ul className="space-y-1">
                {result.details.map((d, i) => (
                  <li key={i} className="text-xs text-[#cbd5e1] font-mono flex items-center gap-2">
                    <span className="text-green-500">&#10003;</span>
                    {d}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}