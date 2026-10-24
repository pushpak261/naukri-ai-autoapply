import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useAgentMonitor } from '../lib/use-agent-monitor';
import { summarizeAgentStart } from '../lib/agent-control';
import {
  Bot, Play, Square, RotateCcw, RefreshCw, Activity, Clock, Terminal,
  AlertCircle, CheckCircle, XCircle, Search, Download, Trash2, Pause,
  Wifi, WifiOff, Radio, Globe,
} from 'lucide-react';
import StatusBadge from '../components/StatusBadge';
import { api } from '../lib/api';

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
  a.download = `agent-logs-${new Date().toISOString().slice(0, 19).replaceAll(':', '-')}.txt`;
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
  const [actionLoading, setActionLoading] = useState<ActionType>(null);
  const actionRef = useRef(false);
  const [notification, setNotification] = useState<Notification | null>(null);
  const [showStopConfirm, setShowStopConfirm] = useState(false);
  const [logSearch, setLogSearch] = useState('');
  const [autoScroll, setAutoScroll] = useState(true);
  const [useSSE, setUseSSE] = useState(true);
  const [platform, setPlatform] = useState<'naukri' | 'linkedin'>('naukri');
  const [parallelMode, setParallelMode] = useState(false);
  const [target100, setTarget100] = useState(false);
  const [logPlatform, setLogPlatform] = useState<'naukri' | 'linkedin'>('naukri');
  const outputRef = useRef<HTMLPreElement>(null);
  const monitor = useAgentMonitor(parallelMode, logPlatform, useSSE, platform);
  const { status, multiStatus, metrics, applicationStats, output, setOutput, loading, backendOnline, statusError, streamConnected } = monitor;
  const viewedPlatform = (parallelMode ? logPlatform : platform) === 'linkedin' ? 'LinkedIn' : 'Naukri';
  const [now, setNow] = useState(Date.now());
  const uptimeFor = (agent: {running: boolean; started_at?: string | null; uptime_seconds?: number | null} | null | undefined) => {
    if (!agent?.running) return null;
    const started = agent.started_at ? Date.parse(agent.started_at) : NaN;
    return Number.isFinite(started) ? Math.max(0, Math.floor((now - started) / 1000)) : agent.uptime_seconds ?? null;
  };
  const uptime = uptimeFor(status);
  const multiUptime = { naukri: uptimeFor(multiStatus?.agents.naukri), linkedin: uptimeFor(multiStatus?.agents.linkedin) };
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (status?.running && status.platform) setPlatform(status.platform);
    if (status?.running && status.platform === 'naukri' && status.target_progress?.target === 100) setTarget100(true);
    if (!parallelMode && multiStatus && Object.values(multiStatus.agents).some(agent => agent.running && agent.pid !== status?.pid)) setParallelMode(true);
  }, [status, multiStatus, parallelMode]);
  const notify = (type: Notification['type'], message: string) => setNotification({ type, message });
  const outputLines = useMemo(() => output.split('\n').filter(Boolean), [output]);
  const filteredLines = useMemo(() => logSearch ? outputLines.filter(line => line.toLowerCase().includes(logSearch.toLowerCase())) : outputLines, [outputLines, logSearch]);
  const MAX_RENDER = 5000;
  const displayLines = filteredLines.slice(-MAX_RENDER);
  const scrollToBottom = useCallback(() => {
    setAutoScroll(true);
    if (outputRef.current) outputRef.current.scrollTop = outputRef.current.scrollHeight;
  }, []);
  const toggleAutoScroll = () => { if (autoScroll) setAutoScroll(false); else scrollToBottom(); };
  const handleScroll = () => {
    const node = outputRef.current;
    if (node) setAutoScroll(node.scrollHeight - node.scrollTop - node.clientHeight < 35);
  };
  useEffect(() => {
    if (autoScroll && outputRef.current) outputRef.current.scrollTop = outputRef.current.scrollHeight;
  }, [output, autoScroll]);

  const handleStart = async () => {
    if (actionRef.current || statusError) return;
    actionRef.current = true;
    setActionLoading('start');
    setNotification(null);
    try {
      if (parallelMode) {
        const result = await api.multi.start();
        const summary = summarizeAgentStart(result.agents);
        notify(summary.type, summary.message);
        await monitor.refresh();

      } else {
        const result = await api.agent.start(platform, platform === 'naukri' && target100 ? 100 : 0);
        notify(result.status === 'started' ? 'success' : 'info', result.message || 'Agent start request completed');
        await monitor.refresh();
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      notify('error', `Failed to start agent: ${msg}`);
    } finally {
      actionRef.current = false;
      setActionLoading(null);
    }
  };

  const handleStop = async () => {
    if (actionRef.current) return;
    actionRef.current = true;
    setShowStopConfirm(false);
    setActionLoading('stop');
    setNotification(null);
    try {
      if (parallelMode) {
        await api.multi.stop();
        notify('info', 'Stopped parallel agents');
        monitor.disconnect();
        await monitor.refresh();
      } else {
        const result = await api.agent.stop();
        notify('info', result.message || 'Agent stopped');
        monitor.disconnect();
        await monitor.refresh();
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      notify('error', `Failed to stop agent: ${msg}`);
    } finally {
      actionRef.current = false;
      setActionLoading(null);
    }
  };

  const handleRestart = async () => {
    if (actionRef.current || statusError) return;
    actionRef.current = true;
    setActionLoading('restart');
    setNotification(null);
    try {
      if (parallelMode) {
        if (multiAnyRunning) {
          monitor.disconnect();
          await api.multi.stop();
          await new Promise(r => setTimeout(r, 500));
        }
        const result = await api.multi.start();
        const summary = summarizeAgentStart(result.agents);
        notify(summary.type, summary.message);
        await monitor.refresh();

      } else {
        if (status?.running) {
          monitor.disconnect();
          await api.agent.stop();
          await new Promise(r => setTimeout(r, 500));
        }
        const result = await api.agent.start(platform, platform === 'naukri' && target100 ? 100 : 0);
        notify(result.status === 'started' ? 'success' : 'info', result.message || 'Agent restart request completed');
        await monitor.refresh();
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      notify('error', `Failed to restart agent: ${msg}`);
    } finally {
      actionRef.current = false;
      setActionLoading(null);
    }
  };

  const handleRefresh = async () => { await monitor.refresh(); };

  const handleStopPlatform = async (target: 'naukri' | 'linkedin') => {
    if (actionRef.current) return;
    actionRef.current = true;
    setActionLoading('stop');
    setShowStopConfirm(false);
    try {
      await api.multi.stop(target);
      notify('info', `Stopped ${target === 'linkedin' ? 'LinkedIn' : 'Naukri'}`);
      await monitor.refresh();
    } catch (err) {
      notify('error', `Failed to stop ${target}: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      actionRef.current = false;
      setActionLoading(null);
    }
  };

  const successRate = applicationStats && (applicationStats.total_applied + applicationStats.total_failed) > 0
    ? Math.round((applicationStats.total_applied / (applicationStats.total_applied + applicationStats.total_failed)) * 100)
    : null;

  const multiAnyRunning =
    !!multiStatus && (multiStatus.agents.naukri.running || multiStatus.agents.linkedin.running);
  const bothRunning =
    !!multiStatus && multiStatus.agents.naukri.running && multiStatus.agents.linkedin.running;

  const handleModeChange = (mode: boolean) => {
    if (mode === parallelMode || actionRef.current) return;
    setShowStopConfirm(false);
    monitor.disconnect();
    setParallelMode(mode);
    setOutput('');
  };

  return (
      <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2" style={{ color: 'var(--color-text)' }}>
            <Bot className="w-6 h-6" style={{ color: 'var(--color-primary)' }} />
            Agent Command Center
          </h1>
          <p className="mt-1" style={{ color: 'var(--color-text-secondary)' }}>Start, stop, and monitor the job application agent in real-time</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => setUseSSE(p => !p)}
            className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border transition-colors ${
              useSSE
                ? 'bg-[#38bdf8]/10 border-[var(--color-primary)]/30 text-[var(--color-primary)]'
                : 'bg-[var(--color-bg)] border-[var(--color-border)] text-[var(--color-text-muted)]'
            }`}
            title={streamConnected ? 'Real-time streaming active' : 'Polling while the live stream is unavailable or disabled'}
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

      {statusError && <div role="alert" className="notice-error"><p>Agent status is unavailable: {statusError}</p><button onClick={handleRefresh}>Retry status</button></div>}
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
        <div className="bg-[var(--color-surface)] border border-red-500/30 rounded-xl p-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-400" />
            <span className="text-sm text-[var(--color-text)]">Are you sure you want to stop the agent?</span>
          </div>
          <div className="flex gap-2">
            <button onClick={() => setShowStopConfirm(false)} className="px-3 py-1.5 bg-[var(--color-surface-hover)] hover:bg-[var(--color-border)] text-[var(--color-text)] rounded-lg text-sm transition-colors">Cancel</button>
            <button onClick={handleStop} disabled={actionLoading !== null} className="px-3 py-1.5 bg-red-600 hover:bg-red-700 text-[var(--color-text)] rounded-lg text-sm transition-colors">Stop</button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <div className="rounded-xl border p-5" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
          <h2 className="text-xs font-medium mb-3 flex items-center gap-1.5" style={{ color: 'var(--color-text-secondary)' }}>
            <Activity className="w-3.5 h-3.5" />
            Agent Status
          </h2>
          {parallelMode ? (
            <div className="space-y-3">
              {(['naukri', 'linkedin'] as const).map(p => {
                const a = multiStatus?.agents[p];
                return (
                  <div key={p} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className={`w-2.5 h-2.5 rounded-full ${a?.running ? 'bg-green-500 animate-pulse' : 'bg-gray-500'}`} />
                      <span className="text-sm font-medium capitalize" style={{ color: 'var(--color-text)' }}>{p}</span>
                      <StatusBadge status={a?.running ? 'running' : 'stopped'} />
                    </div>
                    <div className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                      {a?.pid ? `PID ${a.pid}` : '—'}
                      {multiUptime[p] != null && ` · ${formatUptime(multiUptime[p]!)}`}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2 mb-3">
                <div className={`w-2.5 h-2.5 rounded-full ${status?.running ? 'bg-green-500 animate-pulse' : 'bg-gray-500'}`} />
                <span className="text-base font-semibold" style={{ color: 'var(--color-text)' }}>{statusError || loading ? 'Unknown' : status?.running ? 'Running' : 'Stopped'}</span>
                <StatusBadge status={statusError || loading ? 'unknown' : status?.running ? 'running' : 'stopped'} />
              </div>
              {status?.pid && <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>PID: {status.pid}</p>}
              {status?.started_at && <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>Started: {new Date(status.started_at).toLocaleString()}</p>}
              {uptime != null && (
                <p className="text-xs flex items-center gap-1 mt-1" style={{ color: 'var(--color-text-muted)' }}>
                  <Clock className="w-3 h-3" /> Uptime: {formatUptime(uptime)}
                </p>
              )}
            </>
          )}
        </div>

        <div className="rounded-xl border p-5" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
          <h2 className="text-xs font-medium mb-3" style={{ color: 'var(--color-text-secondary)' }}>{viewedPlatform} applications submitted</h2>
          <p className="text-2xl font-bold" style={{ color: 'var(--color-text)' }}>{applicationStats?.total_applied ?? '—'}</p>
          <p className="text-xs mt-1" style={{ color: 'var(--color-text-muted)' }}>Applied / {applicationStats?.total_failed ?? '—'} failed</p>
        </div>

        <div className="rounded-xl border p-5" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
          <h2 className="text-xs font-medium mb-3" style={{ color: 'var(--color-text-secondary)' }}>{viewedPlatform} Submission Rate</h2>
          <p className={`text-2xl font-bold ${successRate != null && successRate >= 50 ? 'text-green-400' : successRate != null ? 'text-yellow-400' : ''}`} style={{ color: successRate == null ? 'var(--color-text-muted)' : undefined }}>
            {successRate != null ? `${successRate}%` : 'N/A'}
          </p>
          <p className="text-xs mt-1" style={{ color: 'var(--color-text-muted)' }}>{metrics?.total_runs ?? '—'} total runs across both platforms</p>
        </div>

        <div className="rounded-xl border p-5" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
          <h2 className="text-xs font-medium mb-3" style={{ color: 'var(--color-text-secondary)' }}>API Calls · Both platforms</h2>
          <p className="text-2xl font-bold" style={{ color: 'var(--color-primary)' }}>{metrics?.api_calls ?? 0}</p>
          <p className="text-xs mt-1" style={{ color: 'var(--color-text-muted)' }}>{metrics?.duration_seconds ? `${Math.round(metrics.duration_seconds / 60)} min runtime` : ''}</p>
        </div>
      </div>

      {!parallelMode && platform === 'naukri' && status?.target_progress && <section className="rounded-xl border p-5 space-y-2" style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-surface)' }} aria-label="Run application target">
        <h2 className="font-semibold">This run’s application target</h2>
        <p className="text-2xl font-bold">{status.target_progress.submitted} / {status.target_progress.target} verified submissions</p>
        <progress className="w-full" value={status.target_progress.submitted} max={status.target_progress.target} aria-label="Verified submission progress" />
        <p className="text-sm text-[var(--color-text-secondary)]">{status.target_progress.reason || status.target_progress.state}</p>
        {!status.running && status.target_progress.submitted < status.target_progress.target && <p role="status" className="text-sm text-amber-400">Run stopped before its target. Review the live output; this run is not complete.</p>}
      </section>}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="rounded-xl border p-5" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
          <h2 className="text-sm font-medium mb-3 flex items-center gap-2" style={{ color: 'var(--color-text-secondary)' }}>
            <Clock className="w-4 h-4" />
            Last Naukri Run
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
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-3">
            <h2 className="text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>Actions</h2>
            <div className="flex items-center gap-2 flex-wrap">
              <div className="flex items-center gap-1 p-0.5 rounded-lg border" style={{ backgroundColor: 'var(--color-bg)', borderColor: 'var(--color-border)' }}>
                <button
                  disabled={actionLoading !== null} onClick={() => handleModeChange(false)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                    !parallelMode
                      ? 'bg-[#38bdf8]/15 text-[var(--color-primary)]'
                      : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]'
                  }`}
                >
                  Single
                </button>
                <button
                  disabled={actionLoading !== null} onClick={() => handleModeChange(true)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                    parallelMode
                      ? 'bg-[#a855f7]/15 text-[#a855f7]'
                      : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]'
                  }`}
                >
                  <Globe className="w-3 h-3" />
                  Parallel
                </button>
              </div>
              {!parallelMode && (
                <div className="flex items-center gap-1 p-0.5 rounded-lg border" style={{ backgroundColor: 'var(--color-bg)', borderColor: 'var(--color-border)' }}>
                  <button
                    disabled={actionLoading !== null || !!status?.running} onClick={() => setPlatform('naukri')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                      platform === 'naukri'
                        ? 'bg-[#38bdf8]/15 text-[var(--color-primary)]'
                        : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]'
                    }`}
                  >
                    Naukri
                  </button>
                  <button
                    disabled={actionLoading !== null || !!status?.running} onClick={() => setPlatform('linkedin')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                      platform === 'linkedin'
                        ? 'bg-[#0077b5]/15 text-[#0077b5]'
                        : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]'
                    }`}
                  >
                    <Globe className="w-3 h-3" />
                    LinkedIn
                  </button>
                </div>
              )}
            </div>
          </div>
          {!parallelMode && platform === 'naukri' && <label className="mb-4 flex items-start gap-2 text-sm">
            <input type="checkbox" checked={target100} disabled={status?.running || actionLoading !== null} onChange={event => setTarget100(event.target.checked)} className="mt-1" />
            <span><strong>Target 100 verified applications this run</strong><span className="block text-xs text-[var(--color-text-muted)]">Naukri Apply forms only. Skips and failures do not count. Up to three discovery passes and six hours; blocked or exhausted runs remain marked incomplete.</span></span>
          </label>}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <button
              onClick={handleStart}
              disabled={(parallelMode ? bothRunning : status?.running) || actionLoading !== null || loading || !!statusError}
              className="flex items-center justify-center gap-2 px-3 py-2.5 bg-green-600 hover:bg-green-700 active:bg-green-800 disabled:bg-gray-700 disabled:cursor-not-allowed text-[var(--color-text)] rounded-lg transition-colors text-sm font-medium"
            >
              {actionLoading === 'start' ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              {actionLoading === 'start' ? 'Starting...' : parallelMode ? 'Start Both' : 'Start'}
            </button>
            <button
              onClick={() => setShowStopConfirm(true)}
              disabled={(!statusError && (parallelMode ? !multiAnyRunning : !status?.running)) || actionLoading !== null || loading}
              className="flex items-center justify-center gap-2 px-3 py-2.5 bg-red-600 hover:bg-red-700 active:bg-red-800 disabled:bg-gray-700 disabled:cursor-not-allowed text-[var(--color-text)] rounded-lg transition-colors text-sm font-medium"
            >
              {actionLoading === 'stop' ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Square className="w-4 h-4" />}
              {actionLoading === 'stop' ? 'Stopping...' : parallelMode ? 'Stop Both' : 'Stop'}
            </button>
            <button
              onClick={handleRestart}
              disabled={actionLoading !== null || loading || !!statusError}
              className="flex items-center justify-center gap-2 px-3 py-2.5 bg-yellow-600 hover:bg-yellow-700 active:bg-yellow-800 disabled:bg-gray-700 disabled:cursor-not-allowed text-[var(--color-text)] rounded-lg transition-colors text-sm font-medium"
            >
              {actionLoading === 'restart' ? <RefreshCw className="w-4 h-4 animate-spin" /> : <RotateCcw className="w-4 h-4" />}
              {actionLoading === 'restart' ? 'Restarting...' : parallelMode ? 'Restart Both' : 'Restart'}
            </button>
            <button
              onClick={handleRefresh}
              disabled={loading || actionLoading !== null}
              className="flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg transition-colors text-sm font-medium disabled:opacity-50"
              style={{ backgroundColor: 'var(--color-surface-hover)' }}
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
          {parallelMode && <div className="flex gap-2 mt-3">
            {(['naukri', 'linkedin'] as const).map(target => <button key={target}
              onClick={() => handleStopPlatform(target)}
              disabled={!multiStatus?.agents[target].running || actionLoading !== null || loading}
              className="px-3 py-2 rounded-lg border text-sm disabled:opacity-40"
              style={{ borderColor: 'var(--color-border)' }}>
              Stop {target === 'linkedin' ? 'LinkedIn' : 'Naukri'}
            </button>)}
          </div>}
        </div>
      </div>

      <div className="rounded-xl border p-5" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <h2 className="text-lg font-semibold flex items-center gap-2" style={{ color: 'var(--color-text)' }}>
            <Terminal className="w-5 h-5" style={{ color: 'var(--color-primary)' }} />
            Live Output
            {streamConnected && (parallelMode ? multiAnyRunning : status?.running) && (
              <span className="flex items-center gap-1.5 text-xs text-green-400 font-normal">
                <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                SSE
              </span>
            )}
          </h2>
          <div className="flex items-center gap-2 flex-wrap">
            {parallelMode && (
              <div className="flex items-center gap-1 p-0.5 rounded-lg border" style={{ backgroundColor: 'var(--color-bg)', borderColor: 'var(--color-border)' }}>
                {(['naukri', 'linkedin'] as const).map(p => (
                  <button
                    key={p}
                    onClick={() => setLogPlatform(p)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium capitalize transition-colors ${
                      logPlatform === p
                        ? 'bg-[#a855f7]/15 text-[#a855f7]'
                        : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]'
                    }`}
                  >
                    {p}
                    {multiStatus?.agents[p].running && (
                      <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                    )}
                  </button>
                ))}
              </div>
            )}

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
              onClick={toggleAutoScroll}
              className={`p-1.5 rounded-lg border transition-colors ${
                autoScroll ? 'bg-[#38bdf8]/10 border-[var(--color-primary)]/30 text-[var(--color-primary)]' : 'bg-[var(--color-bg)] border-[var(--color-border)] text-[var(--color-text-muted)]'
              }`}
              title={autoScroll ? 'Auto-scroll enabled (Click to pause)' : 'Auto-scroll paused (Click to resume)'}
            >
              {autoScroll ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}
            </button>

            {output && (
              <button onClick={() => downloadLogs(output)} className="p-1.5 rounded-lg border text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors" style={{ backgroundColor: 'var(--color-bg)', borderColor: 'var(--color-border)' }} title="Download logs">
                <Download className="w-3.5 h-3.5" />
              </button>
            )}

            {output && (
              <button onClick={() => setOutput('')} className="p-1.5 rounded-lg border text-[var(--color-text-muted)] hover:text-red-400 transition-colors" style={{ backgroundColor: 'var(--color-bg)', borderColor: 'var(--color-border)' }} title="Clear logs">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            )}

            {(parallelMode ? multiAnyRunning : status?.running) && (
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
              ? `${displayLines.length}${filteredLines.length > MAX_RENDER ? '+' : ''} of ${outputLines.length} lines match`
              : `${outputLines.length} lines`}
          </span>
          <span>{(parallelMode ? multiAnyRunning : status?.running) ? (streamConnected ? 'Real-time SSE' : 'Refreshing every 3s') : 'Agent stopped'}</span>
        </div>

        <pre
          ref={outputRef}
          className="bg-[var(--color-bg)] border border-[var(--color-border)] rounded-lg p-4 text-xs font-mono overflow-auto max-h-[500px] whitespace-pre-wrap break-words leading-relaxed focus:outline-none focus:ring-1 focus:ring-[#38bdf8]/30"
          style={{ color: output ? '#e2e8f0' : '#64748b' }}
          onScroll={handleScroll}
          tabIndex={0}
          role="log"
          aria-label="Agent output log"
          aria-live="polite"
        >
          {output ? (
            logSearch ? (
              displayLines.map((line, i) => (
                <span key={i} style={{ color: lineColor(line), display: 'block' }}>{line}</span>
              ))
            ) : (
              output
            )
          ) : (parallelMode ? multiAnyRunning : status?.running) ? (
            'Waiting for logs...'
          ) : (
            'No output yet. Start the agent to see live logs.'
          )}
        </pre>

        {!autoScroll && outputLines.length > 0 && (
          <button
            onClick={scrollToBottom}
            className="mt-2 text-xs text-[var(--color-primary)] hover:text-[var(--color-text)] hover:underline flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#38bdf8]/10 border border-[var(--color-primary)]/30 font-medium transition-colors"
          >
            <span>↓ Auto-scroll paused — click to jump to bottom & resume</span>
          </button>
        )}
      </div>
    </div>
  );
}

