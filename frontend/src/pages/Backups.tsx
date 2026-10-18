import { useState, useEffect } from 'react';
import { HardDrive, Plus, RefreshCw, Database, Download, Upload, AlertTriangle } from 'lucide-react';
import { api, downloadExport, type BackupItem } from '../lib/api';
import { queryClient } from '../lib/query-client';

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function Backups() {
  const [backups, setBackups] = useState<BackupItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [restoring, setRestoring] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => { fetchBackups(); }, []);

  const fetchBackups = async () => {
    setLoading(true);
    try {
      const r = await api.backups.list();
      setBackups(r.items);
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Could not load backups. Please retry.' });
    } finally { setLoading(false); }
  };

  const handleCreate = async () => {
    setCreating(true);
    setMessage(null);
    try {
      await api.backups.create();
      await fetchBackups();
      setMessage({ type: 'success', text: 'Backup created successfully' });
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Backup failed' });
    }
    setCreating(false);
  };

  const handleRestore = async (name: string) => {
    if (!confirm(`Restore database from "${name}"? The current database will be backed up first.`)) return;
    setRestoring(name);
    setMessage(null);
    try {
      const r = await api.backups.restore(name);
      await queryClient.invalidateQueries();
      await fetchBackups();
      setMessage({ type: 'success', text: r.message });
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Restore failed' });
    }
    setRestoring(null);
  };

  const handleFullExport = async () => {
    setExporting(true);
    try {
      await downloadExport('/export/full', `naukri_agent_export_${new Date().toISOString().slice(0, 10)}.json`);
      setMessage({ type: 'success', text: 'Full export downloaded' });
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Export failed' });
    }
    setExporting(false);
  };

  const handleFullImport = async () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      setImporting(true);
      setMessage(null);
      try {
        const text = await file.text();
        const data = JSON.parse(text);
        const r = await api.importFull(data);
        await queryClient.invalidateQueries();
        setMessage({ type: 'success', text: r.message });
      } catch (err) {
        setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Import failed' });
      }
      setImporting(false);
    };
    input.click();
  };

  const totalSize = backups.reduce((s, b) => s + b.size, 0);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[var(--color-primary)]" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--color-text)] flex items-center gap-2">
          <HardDrive className="w-6 h-6 text-[var(--color-primary)]" />
          Database Backups & Data
        </h1>
        <p className="text-[var(--color-text-secondary)] mt-1">Manage backups, export/import all data</p>
      </div>

      {message && (
        <div className={`flex items-center gap-2 p-3 rounded-lg text-sm ${
          message.type === 'success' ? 'bg-green-500/10 text-green-400 border border-green-500/30' : 'bg-red-500/10 text-red-400 border border-red-500/30'
        }`}>
          {message.type === 'success' ? <Download className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
          {message.text}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-5 text-center">
          <p className="text-2xl font-bold text-[var(--color-text)]">{backups.length}</p>
          <p className="text-xs text-[var(--color-text-secondary)] mt-1">Total Backups</p>
        </div>
        <div className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-5 text-center">
          <p className="text-2xl font-bold text-[var(--color-primary)]">{formatSize(totalSize)}</p>
          <p className="text-xs text-[var(--color-text-secondary)] mt-1">Total Size</p>
        </div>
        <div className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-5 text-center">
          <p className="text-2xl font-bold text-green-400">{backups.length > 0 ? backups[backups.length - 1].created.slice(0, 10) : 'N/A'}</p>
          <p className="text-xs text-[var(--color-text-secondary)] mt-1">Latest Backup</p>
        </div>
      </div>

      <div className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-4">
          <h2 className="text-lg font-semibold text-[var(--color-text)] flex items-center gap-2">
            <Database className="w-5 h-5 text-[var(--color-primary)]" />
            Backup Files
          </h2>
          <div className="flex flex-wrap gap-2 w-full sm:w-auto">
            <button onClick={handleFullExport} disabled={exporting}
              className="flex items-center gap-1.5 px-3 py-2 bg-[var(--color-surface-hover)] hover:bg-[var(--color-border)] text-[var(--color-text)] rounded-lg text-sm transition-colors disabled:opacity-50">
              <Download className="w-4 h-4" />
              {exporting ? 'Exporting...' : 'Export All'}
            </button>
            <button onClick={handleFullImport} disabled={importing}
              className="flex items-center gap-1.5 px-3 py-2 bg-[var(--color-surface-hover)] hover:bg-[var(--color-border)] text-[var(--color-text)] rounded-lg text-sm transition-colors disabled:opacity-50">
              <Upload className="w-4 h-4" />
              {importing ? 'Importing...' : 'Import'}
            </button>
            <button onClick={fetchBackups} className="flex items-center gap-1.5 px-3 py-2 bg-[var(--color-surface-hover)] hover:bg-[var(--color-border)] text-[var(--color-text)] rounded-lg text-sm transition-colors">
              <RefreshCw className="w-4 h-4" />
              Refresh
            </button>
            <button onClick={handleCreate} disabled={creating} className="flex items-center gap-1.5 px-4 py-2 bg-[#38bdf8] hover:bg-[#7dd3fc] disabled:bg-gray-700 text-[var(--color-text)] disabled:text-[var(--color-text-muted)] rounded-lg text-sm font-medium transition-colors">
              <Plus className="w-4 h-4" />
              {creating ? 'Creating...' : 'Create Backup'}
            </button>
          </div>
        </div>

        {backups.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[640px]">
              <thead>
                <tr className="text-[var(--color-text-secondary)] border-b border-[var(--color-border)]">
                  <th className="text-left py-2 px-3">Name</th>
                  <th className="text-right py-2 px-3">Size</th>
                  <th className="text-left py-2 px-3">Created</th>
                  <th className="text-center py-2 px-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {backups.map((b) => (
                  <tr key={b.name} className="border-b border-[var(--color-border)]/50 hover:bg-[var(--color-surface-hover)]/30">
                    <td className="py-2 px-3 text-[var(--color-text)] font-mono text-xs">{b.name}</td>
                    <td className="py-2 px-3 text-right text-[var(--color-text-secondary)]">{formatSize(b.size)}</td>
                    <td className="py-2 px-3 text-[var(--color-text-secondary)] text-xs">
                      {new Date(b.created).toLocaleString()}
                    </td>
                    <td className="py-2 px-3 text-center">
                      <button
                        onClick={() => handleRestore(b.name)}
                        disabled={restoring === b.name}
                        className="px-3 py-1.5 text-xs bg-yellow-500/10 text-yellow-400 hover:bg-yellow-500/20 rounded-lg transition-colors disabled:opacity-50 flex items-center gap-1 mx-auto"
                      >
                        {restoring === b.name ? <RefreshCw className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
                        Restore
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-8 text-[var(--color-text-muted)]">No backups found. Create one to get started.</div>
        )}
      </div>
    </div>
  );
}

