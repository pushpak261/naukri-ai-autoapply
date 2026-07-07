import { useState, useEffect, useRef, useCallback } from 'react';
import {
  Bot, Play, Square, RotateCcw, RefreshCw, Activity, Clock, Terminal,
  AlertCircle, CheckCircle, XCircle, Search, Download, Trash2, Pause,
  Wifi, WifiOff, Radio,
} from 'lucide-react';
import StatusBadge from '../components/StatusBadge';
import { api, type AgentStatus, type MetricsResponse } from '../lib/api';

type Notification = { type: 'success' | 'error' | 'info'; message: string };
type ActionType = 'start' | 'stop' | 'restart' | null;

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function downloadLogs(content: string) {
  const blob = new Blob([content], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `agent-logs-${new Date().toISOString().slice(0, 19)}.txt`;
  a.click();
  URL.revokeObjectURL(url);
}

function lineColor(line: string): string {
  if (/error|exception|traceback|fail|crash/i.test(line)) return '#ef4444';
  if (/warn|caution|careful/i.test(line)) return '#eab308';
  if (/info|ready|started|completed|done|success/i.test(line)) return '#22c55e';
  if (/applying|submitting|processing|running/i.test(line)) return '#38bdf8';
  return '#e2e8f0';
}

export default function AgentControl() {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [output, setOutput] = useState('');
  const [loading, setLoading] = useState(true);
  const [backendOnline, setBackendOnline] = useState(true);
  const [actionLoading, setActionLoading] = useState<ActionType>(null);
  const [notification, setNotification] = useState<Notification | null>(null);
  const [showStopConfirm, setShowStopConfirm] = useState(false);
  const [logSearch, setLogSearch] = useState('');
  const [autoScroll, setAutoScroll] = useState(true);
  const [useSSE, setUseSSE] = useState(true);
  const outputRef = useRef<HTMLPreElement>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval>>(undefined);
  const healthIntervalRef = useRef<ReturnType<typeof setInterval>>(undefined);
  const [uptime, setUptime] = useState<number | null>(null);
  const sseRef = useRef<EventSource | null>(null);

  const outputLines = output.split('\n').filter(Boolean);

  const filteredLines = logSearch
    ? outputLines.filter(l => l.toLowerCase().includes(logSearch.toLowerCase()))
    : outputLines;

  const notify = (type: Notification['type'], message: string) => {
    setNotification({ type, message });
    setTimeout(() => setNotification(null), 5000);
  };

  const checkHealth = useCallback(async () => {
    try {
      await api.health();
      setBackendOnline(true);
    } catch {
      setBackendOnline(false);
    }
  }, []);

  const fetchMetrics = useCallback(async () => {
    try {
      const m = await api.metrics();
      setMetrics(m);
    } catch { /* metrics are optional */ }
  }, []);

  const fetchStatus = useCallback(async () => {
    try {
      const s = await api.agent.status();
      setStatus(s);
      if (s.running && s.uptime_seconds != null) setUptime(s.uptime_seconds);
      return s;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      notify('error', `Failed to fetch status: ${msg}`);
      return null;
    }
  }, []);

  const fetchOutput = useCallback(async () => {
    try {
      const text = await api.agent.output(200);
      if (text && text !== 'Waiting for logs...\n') setOutput(text);
    } catch {
      // 404 is expected when agent isn't running
    }
  }, []);

  const connectSSE = useCallback(() => {
    if (sseRef.current) sseRef.current.close();
    const url = api.agent.outputStreamUrl();
    const es = new EventSource(url);
    sseRef.current = es;

    let buffer = '';
    es.onmessage = (event) => {
      if (event.data) {
        buffer += event.data + '\n';
        if (buffer.length > 50000) {
          buffer = buffer.slice(-25000);
        }
        setOutput(buffer);
      }
    };

    es.onerror = () => {
      es.close();
      sseRef.current = null;
      if (useSSE) {
        setTimeout(connectSSE, 3000);
      }
    };
  }, [useSSE]);

  const refreshAll = useCallback(async () => {
    const s = await fetchStatus();
    if (s?.running) {
      if (useSSE) {
        connectSSE();
      } else {
        await fetchOutput();
      }
    }
    await fetchMetrics();
  }, [fetchStatus, fetchOutput, fetchMetrics, useSSE, connectSSE]);

  // Initial load
  useEffect(() => {
    let mounted = true;
    checkHealth();
    fetchMetrics();
    fetchStatus().then(s => {
      if (!mounted) return;
      setLoading(false);
      if (s?.running) {
        if (useSSE) {
          connectSSE();
        } else {
          fetchOutput();
        }
      }
    });

    intervalRef.current = setInterval(async () => {
      const s = await fetchStatus();
      if (s?.running && !useSSE) await fetchOutput();
    }, useSSE ? 10000 : 3000);

    healthIntervalRef.current = setInterval(checkHealth, 15000);

    return () => {
      mounted = false;
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (healthIntervalRef.current) clearInterval(healthIntervalRef.current);
      if (sseRef.current) sseRef.current.close();
    };
  }, [fetchStatus, fetchOutput, checkHealth, fetchMetrics, useSSE, connectSSE]);

  // Auto-scroll
  useEffect(() => {
    if (autoScroll && outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [output, autoScroll]);

  // Uptime counter
  useEffect(() => {
    if (!status?.running) { setUptime(null); return; }
    const t = setInterval(() => setUptime(prev => (prev ?? 0) + 1), 1000);
    return () => clearInterval(t);
  }, [status?.running]);

  const handleStart = async () => {
    setActionLoading('start');
    setNotification(null);
    try {
      const result = await api.agent.start();
      notify('success', result.message || 'Agent started');
      setOutput('');
      await refreshAll();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      notify('error', `Failed to start agent: ${msg}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleStop = async () => {
    setShowStopConfirm(false);
    setActionLoading('stop');
    setNotification(null);
    try {
      const result = await api.agent.stop();
      notify('info', result.message || 'Agent stopped');
      if (sseRef.current) sseRef.current.close();
      setStatus(prev => prev ? { ...prev, running: false, pid: null, uptime_seconds: null } : null);
      setUptime(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      notify('error', `Failed to stop agent: ${msg}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleRestart = async () => {
    setActionLoading('restart');
    setNotification(null);
    try {
      if (status?.running) {
        if (sseRef.current) sseRef.current.close();
        await api.agent.stop();
        await new Promise(r => setTimeout(r, 500));
      }
      const result = await api.agent.start();
      notify('success', result.message || 'Agent restarted');
      setOutput('');
      await refreshAll();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      notify('error', `Failed to restart agent: ${msg}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleRefresh = async () => {
    setLoading(true);
    await refreshAll();
    setLoading(false);
  };

  if (loading && !status) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  const liveApplied = status?.jobs_applied ?? null;
  const liveSkipped = status?.jobs_skipped ?? null;
  const liveFound = status?.jobs_found ?? null;
  const liveFailed = status?.jobs_failed ?? null;

  const successRate = metrics && (metrics.jobs_applied + metrics.jobs_failed) > 0
    ? Math.round((metrics.jobs_applied / (metrics.jobs_applied + metrics.jobs_failed)) * 100)
    : null;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2" style={{ color: 'var(--color-text)' }}>
            <Bot className="w-6 h-6" style={{ color: 'var(--color-primary)' }} />
            Agent Command Center
          </h1>
          <p className="mt-1" style={{ color: 'var(--color-text-secondary)' }}>Start, stop, and monitor the job application agent in real-time</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setUseSSE(p => !p)}
            className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border transition-colors ${
              useSSE
                ? 'bg-primary/10 border-primary/30 text-primary'
                : 'bg-bg border-border text-muted'
            }`}
            title={useSSE ? 'Real-time streaming active' : 'Using polling mode'}
          >
            <Radio className="w-3 h-3" />
            {useSSE ? 'Live Stream' : 'Polling'}
          </button>
          <span className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border ${
            backendOnline
              ? 'bg-green-500/10 border-green-500/30 text-green-400'
              : 'bg-red-500/10 border-red-500/30 text-red-400'
          }`}>
            {backendOnline ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
            {backendOnline ? 'Connected' : 'Disconnected'}
          </span>
        </div>
      </div>

      {notification && (
        <div
          className={`flex items-center gap-3 px-4 py-3 rounded-lg border text-sm ${
            notification.type === 'success'
              ? 'bg-green-500/15 border-green-500/30 text-green-400'
              : notification.type === 'error'
              ? 'bg-red-500/15 border-red-500/30 text-red-400'
              : 'bg-blue-500/15 border-blue-500/30 text-blue-400'
          }`}
        >
          {notification.type === 'success' ? <CheckCircle className="w-4 h-4 shrink-0" /> :
           notification.type === 'error' ? <XCircle className="w-4 h-4 shrink-0" /> :
           <AlertCircle className="w-4 h-4 shrink-0" />}
          <span className="text-sm flex-1">{notification.message}</span>
          <button onClick={() => setNotification(null)} className="text-current opacity-60 hover:opacity-100">&times;</button>
        </div>
      )}

      {showStopConfirm && (
        <div className="bg-surface border border-red-500/30 rounded-xl p-5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-400" />
            <span className="text-sm text-text">Are you sure you want to stop the agent?</span>
          </div>
          <div className="flex gap-2">
            <button onClick={() => setShowStopConfirm(false)} className="px-3 py-1.5 bg-surface-hover hover:bg-surface-hover text-text rounded-lg text-sm transition-colors">Cancel</button>
            <button onClick={handleStop} className="px-3 py-1.5 bg-red-600 hover:bg-red-700 text-text rounded-lg text-sm transition-colors">Stop</button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        <div className="rounded-xl border p-5" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
          <h2 className="text-xs font-medium mb-3 flex items-center gap-1.5" style={{ color: 'var(--color-text-secondary)' }}>
            <Activity className="w-3.5 h-3.5" />
            Agent Status
          </h2>
          <div className="flex items-center gap-2 mb-3">
            <div className={`w-2.5 h-2.5 rounded-full ${status?.running ? 'bg-green-500 animate-pulse' : 'bg-gray-500'}`} />
            <span className="text-base font-semibold" style={{ color: 'var(--color-text)' }}>{status?.running ? 'Running' : 'Stopped'}</span>
            <StatusBadge status={status?.running ? 'running' : 'completed'} />
          </div>
          {status?.pid && <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>PID: {status.pid}</p>}
          {status?.started_at && <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>Started: {new Date(status.started_at).toLocaleString()}</p>}
          {uptime != null && (
            <p className="text-xs flex items-center gap-1 mt-1" style={{ color: 'var(--color-text-muted)' }}>
              <Clock className="w-3 h-3" /> Uptime: {formatUptime(uptime)}
            </p>
          )}
        </div>

        <div className="rounded-xl border p-5" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
          <h2 className="text-xs font-medium mb-3" style={{ color: 'var(--color-text-secondary)' }}>
            {status?.running ? 'Live Run Progress' : 'Jobs Processed'}
          </h2>
          <p className="text-2xl font-bold" style={{ color: 'var(--color-text)' }}>
            {status?.running ? (liveFound ?? 0) : (metrics?.jobs_applied ?? 0)}
          </p>
          <p className="text-xs mt-1" style={{ color: 'var(--color-text-muted)' }}>
            {status?.running
              ? `Searched: ${liveFound ?? 0} | Applied: ${liveApplied ?? 0} | Skipped: ${liveSkipped ?? 0}`
              : `Applied / ${metrics?.jobs_failed ?? 0} failed`}
          </p>
        </div>

        <div className="rounded-xl border p-5" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
          <h2 className="text-xs font-medium mb-3" style={{ color: 'var(--color-text-secondary)' }}>
            {status?.running ? 'Live Apply Outcomes' : 'Success Rate'}
          </h2>
          <p className={`text-2xl font-bold ${successRate != null && successRate >= 50 ? 'text-green-400' : successRate != null ? 'text-yellow-400' : ''}`} style={{ color: successRate == null && !status?.running ? 'var(--color-text-muted)' : undefined }}>
            {status?.running ? `${liveApplied ?? 0}` : (successRate != null ? `${successRate}%` : 'N/A')}
          </p>
          <p className="text-xs mt-1" style={{ color: 'var(--color-text-muted)' }}>
            {status?.running
              ? `Applied: ${liveApplied ?? 0} | Failed: ${liveFailed ?? 0}`
              : `${metrics?.total_runs ?? 0} total runs`}
          </p>
        </div>

        <div className="rounded-xl border p-5" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
          <h2 className="text-xs font-medium mb-3" style={{ color: 'var(--color-text-secondary)' }}>API Calls</h2>
          <p className="text-2xl font-bold" style={{ color: 'var(--color-primary)' }}>{metrics?.api_calls ?? 0}</p>
          <p className="text-xs mt-1" style={{ color: 'var(--color-text-muted)' }}>{metrics?.duration_seconds ? `${Math.round(metrics.duration_seconds / 60)} min runtime` : ''}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="rounded-xl border p-5" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
          <h2 className="text-sm font-medium mb-3 flex items-center gap-2" style={{ color: 'var(--color-text-secondary)' }}>
            <Clock className="w-4 h-4" />
            Last Run
          </h2>
          {status?.last_run ? (
            <div>
              <p className="text-sm" style={{ color: 'var(--color-text)' }}>{status.last_run.started_at.slice(0, 16).replace('T', ' ')}</p>
              <p className="text-xs mt-1" style={{ color: 'var(--color-text-muted)' }}>
                Found: {status.last_run.found} | Applied: {status.last_run.applied} | Skipped: {status.last_run.skipped} | Failed: {status.last_run.failed}
              </p>
              <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-muted)' }}>Keywords: {status.last_run.keywords}</p>
              <div className="mt-2"><StatusBadge status={status.last_run.status} /></div>
            </div>
          ) : (
            <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>No runs yet</p>
          )}
        </div>

        <div className="rounded-xl border p-5 lg:col-span-2" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
          <h2 className="text-sm font-medium mb-3" style={{ color: 'var(--color-text-secondary)' }}>Actions</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <button
              onClick={handleStart}
              disabled={status?.running || actionLoading !== null}
              className="flex items-center justify-center gap-2 px-3 py-2.5 bg-green-600 hover:bg-green-700 active:bg-green-800 disabled:bg-gray-700 disabled:cursor-not-allowed text-text rounded-lg transition-colors text-sm font-medium"
            >
              {actionLoading === 'start' ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              {actionLoading === 'start' ? 'Starting...' : 'Start'}
            </button>
            <button
              onClick={() => setShowStopConfirm(true)}
              disabled={!status?.running || actionLoading !== null}
              className="flex items-center justify-center gap-2 px-3 py-2.5 bg-red-600 hover:bg-red-700 active:bg-red-800 disabled:bg-gray-700 disabled:cursor-not-allowed text-text rounded-lg transition-colors text-sm font-medium"
            >
              {actionLoading === 'stop' ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Square className="w-4 h-4" />}
              {actionLoading === 'stop' ? 'Stopping...' : 'Stop'}
            </button>
            <button
              onClick={handleRestart}
              disabled={actionLoading !== null}
              className="flex items-center justify-center gap-2 px-3 py-2.5 bg-yellow-600 hover:bg-yellow-700 active:bg-yellow-800 disabled:bg-gray-700 disabled:cursor-not-allowed text-text rounded-lg transition-colors text-sm font-medium"
            >
              {actionLoading === 'restart' ? <RefreshCw className="w-4 h-4 animate-spin" /> : <RotateCcw className="w-4 h-4" />}
              {actionLoading === 'restart' ? 'Restarting...' : 'Restart'}
            </button>
            <button
              onClick={handleRefresh}
              disabled={loading}
              className="flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg transition-colors text-sm font-medium disabled:opacity-50"
              style={{ backgroundColor: 'var(--color-surface-hover)' }}
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
        </div>
      </div>

      <div className="rounded-xl border p-5" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <h2 className="text-lg font-semibold flex items-center gap-2" style={{ color: 'var(--color-text)' }}>
            <Terminal className="w-5 h-5" style={{ color: 'var(--color-primary)' }} />
            Live Output
            {useSSE && status?.running && (
              <span className="flex items-center gap-1.5 text-xs text-green-400 font-normal">
                <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                SSE
              </span>
            )}
          </h2>
          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex items-center gap-1.5 rounded-lg border px-2 py-1" style={{ backgroundColor: 'var(--color-bg)', borderColor: 'var(--color-border)' }}>
              <Search className="w-3.5 h-3.5 shrink-0" style={{ color: 'var(--color-text-muted)' }} />
              <input
                type="text"
                placeholder="Filter logs..."
                value={logSearch}
                onChange={e => setLogSearch(e.target.value)}
                className="bg-transparent border-none outline-none w-28 text-xs"
                style={{ color: 'var(--color-text)' }}
                aria-label="Filter logs"
              />
            </div>

            <button
              onClick={() => setAutoScroll(p => !p)}
              className={`p-1.5 rounded-lg border transition-colors ${
                autoScroll ? 'bg-primary/10 border-primary/30 text-primary' : 'bg-bg border-border text-muted'
              }`}
              title={autoScroll ? 'Auto-scroll on' : 'Auto-scroll off'}
            >
              {autoScroll ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}
            </button>

            {output && (
              <button onClick={() => downloadLogs(output)} className="p-1.5 rounded-lg border text-muted hover:text-text transition-colors" style={{ backgroundColor: 'var(--color-bg)', borderColor: 'var(--color-border)' }} title="Download logs">
                <Download className="w-3.5 h-3.5" />
              </button>
            )}

            {output && (
              <button onClick={() => setOutput('')} className="p-1.5 rounded-lg border text-muted hover:text-red-400 transition-colors" style={{ backgroundColor: 'var(--color-bg)', borderColor: 'var(--color-border)' }} title="Clear logs">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            )}

            {status?.running && (
              <span className="flex items-center gap-1.5 text-xs text-green-400">
                <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                Streaming
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between mb-2 text-xs" style={{ color: 'var(--color-text-muted)' }}>
          <span>
            {logSearch
              ? `${filteredLines.length} of ${outputLines.length} lines match`
              : `${outputLines.length} lines`}
          </span>
          <span>{status?.running ? (useSSE ? 'Real-time SSE' : 'Refreshing every 3s') : 'Agent stopped'}</span>
        </div>

        <pre
          ref={outputRef}
          className="bg-bg border border-border rounded-lg p-4 text-xs font-mono overflow-auto max-h-[500px] whitespace-pre-wrap leading-relaxed"
          style={{ color: output ? '#e2e8f0' : '#64748b' }}
          onWheel={() => { if (autoScroll) setAutoScroll(false); }}
          role="log"
          aria-label="Agent output log"
          aria-live="polite"
        >
          {output
            ? (logSearch ? filteredLines : outputLines).map((line, i) => (
                <span key={i} style={{ color: lineColor(line), display: 'block' }}>{line}</span>
              ))
            : status?.running
              ? 'Waiting for logs...'
              : 'No output yet. Start the agent to see live logs.'}
        </pre>

        {!autoScroll && outputLines.length > 0 && (
          <button
            onClick={() => { setAutoScroll(true); outputRef.current?.scrollTo(0, outputRef.current.scrollHeight); }}
            className="mt-2 text-xs text-primary hover:underline"
          >
            Auto-scroll paused — click to resume
          </button>
        )}
      </div>
    </div>
  );
}
