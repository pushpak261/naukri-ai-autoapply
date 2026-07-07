import { useState, useEffect } from 'react';
import { Clock, Play, CheckCircle, AlertTriangle } from 'lucide-react';
import StatusBadge from '../components/StatusBadge';
import { api, type RunLog } from '../lib/api';

export default function RunLogs() {
  const [logs, setLogs] = useState<RunLog[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.runLogs(50).then((data) => setLogs(data.items)).finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text">Run Logs</h1>
        <p className="text-secondary mt-1">History of all agent execution runs</p>
      </div>

      <div className="bg-surface rounded-xl border border-border overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
          </div>
        ) : logs.length === 0 ? (
          <div className="text-center py-16 text-muted">No runs recorded yet</div>
        ) : (
          <div className="divide-y divide-[#334155]">
            {logs.map((log) => (
              <div key={log.id} className="p-5 hover:bg-bg/50 transition-colors">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      {log.status === 'running' ? (
                        <Play className="w-4 h-4 text-blue-400" />
                      ) : log.status === 'completed' ? (
                        <CheckCircle className="w-4 h-4 text-green-400" />
                      ) : (
                        <AlertTriangle className="w-4 h-4 text-yellow-400" />
                      )}
                      <span className="text-sm font-medium text-text">
                        Run #{log.id}
                      </span>
                      <StatusBadge status={log.status} />
                    </div>
                    <p className="text-xs text-secondary mt-1">
                      <Clock className="w-3 h-3 inline mr-1" />
                      {log.started_at.slice(0, 19).replace('T', ' ')}
                      {log.ended_at ? ` — ${log.ended_at.slice(0, 19).replace('T', ' ')}` : ''}
                    </p>
                    <p className="text-xs text-muted mt-1">
                      Keywords: {log.keywords}
                    </p>
                  </div>
                  <div className="grid grid-cols-3 gap-4 text-center shrink-0">
                    <div>
                      <p className="text-lg font-bold text-primary">{log.found}</p>
                      <p className="text-[10px] text-muted">Found</p>
                    </div>
                    <div>
                      <p className="text-lg font-bold text-green-400">{log.applied}</p>
                      <p className="text-[10px] text-muted">Applied</p>
                    </div>
                    <div>
                      <p className="text-lg font-bold text-yellow-400">{log.skipped}</p>
                      <p className="text-[10px] text-muted">Skipped</p>
                    </div>
                  </div>
                </div>
                <div className="flex gap-4 mt-3 text-xs text-muted">
                  <span>Failed: {log.failed}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
