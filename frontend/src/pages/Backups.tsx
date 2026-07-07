import { useState, useEffect } from 'react';
import { HardDrive, Plus, RefreshCw, Database } from 'lucide-react';
import { api, type BackupItem } from '../lib/api';

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function Backups() {
  const [backups, setBackups] = useState<BackupItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);

  useEffect(() => { fetchBackups(); }, []);

  const fetchBackups = async () => {
    setLoading(true);
    try {
      const r = await api.backups.list();
      setBackups(r.items);
    } catch {} finally { setLoading(false); }
  };

  const handleCreate = async () => {
    setCreating(true);
    await api.backups.create();
    await fetchBackups();
    setCreating(false);
  };

  const totalSize = backups.reduce((s, b) => s + b.size, 0);

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
          <HardDrive className="w-6 h-6 text-primary" />
          Database Backups
        </h1>
        <p className="text-secondary mt-1">Manage and create database backups</p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="bg-surface rounded-xl border border-border p-5 text-center">
          <p className="text-2xl font-bold text-text">{backups.length}</p>
          <p className="text-xs text-secondary mt-1">Total Backups</p>
        </div>
        <div className="bg-surface rounded-xl border border-border p-5 text-center">
          <p className="text-2xl font-bold text-primary">{formatSize(totalSize)}</p>
          <p className="text-xs text-secondary mt-1">Total Size</p>
        </div>
        <div className="bg-surface rounded-xl border border-border p-5 text-center">
          <p className="text-2xl font-bold text-green-400">{backups.length > 0 ? backups[backups.length - 1].created.slice(0, 10) : 'N/A'}</p>
          <p className="text-xs text-secondary mt-1">Latest Backup</p>
        </div>
      </div>

      <div className="bg-surface rounded-xl border border-border p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-text flex items-center gap-2">
            <Database className="w-5 h-5 text-primary" />
            Backup Files
          </h2>
          <div className="flex gap-2">
            <button onClick={fetchBackups} className="flex items-center gap-1.5 px-3 py-2 bg-surface-hover hover:bg-surface-hover text-text rounded-lg text-sm transition-colors">
              <RefreshCw className="w-4 h-4" />
              Refresh
            </button>
            <button onClick={handleCreate} disabled={creating} className="flex items-center gap-1.5 px-4 py-2 bg-primary hover:bg-primary-hover disabled:bg-gray-700 text-text disabled:text-muted rounded-lg text-sm font-medium transition-colors">
              <Plus className="w-4 h-4" />
              {creating ? 'Creating...' : 'Create Backup'}
            </button>
          </div>
        </div>

        {backups.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-secondary border-b border-border">
                  <th className="text-left py-2 px-3">Name</th>
                  <th className="text-right py-2 px-3">Size</th>
                  <th className="text-left py-2 px-3">Created</th>
                </tr>
              </thead>
              <tbody>
                {backups.map((b) => (
                  <tr key={b.name} className="border-b border-border/50 hover:bg-surface-hover/30">
                    <td className="py-2 px-3 text-text font-mono text-xs">{b.name}</td>
                    <td className="py-2 px-3 text-right text-secondary">{formatSize(b.size)}</td>
                    <td className="py-2 px-3 text-secondary text-xs">
                      {new Date(b.created).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-8 text-muted">No backups found. Create one to get started.</div>
        )}
      </div>
    </div>
  );
}
