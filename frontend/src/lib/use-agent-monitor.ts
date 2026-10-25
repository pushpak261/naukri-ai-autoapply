import { useCallback, useEffect, useRef, useState } from 'react';
import { api, type AgentStatus, type MultiAgentStatus, type MetricsResponse, type StatsResponse } from './api';
import { boundAgentLog } from './agent-control';

/** One cancellable monitor per view; late responses from an old view are ignored. */
export function useAgentMonitor(parallel: boolean, logPlatform: 'naukri' | 'linkedin', useSSE: boolean, platform: 'naukri' | 'linkedin') {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [multiStatus, setMultiStatus] = useState<MultiAgentStatus | null>(null);
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [applicationStats, setApplicationStats] = useState<StatsResponse | null>(null);
  const [output, setOutput] = useState('');
  const [loading, setLoading] = useState(true);
  const [backendOnline, setBackendOnline] = useState(false);
  const [statusError, setStatusError] = useState('');
  const [streamConnected, setStreamConnected] = useState(false);
  const refreshRef = useRef<() => Promise<void>>(async () => {});
  const disconnectRef = useRef<() => void>(() => {});
  const refresh = useCallback(() => refreshRef.current(), []);
  const disconnect = useCallback(() => disconnectRef.current(), []);

  useEffect(() => {
    let active = true;
    let polling = false;
    let timer: ReturnType<typeof setTimeout>;
    let stream: EventSource | null = null;
    let streamPid: number | null = null;
    let lastPid: number | null = null;
    let lastMetrics = 0;
    let streamRetryAt = 0;
    let pending = '';
    let frame: number | null = null;
    const close = () => {
      stream?.close();
      stream = null;
      streamPid = null;
      if (frame != null) cancelAnimationFrame(frame);
      frame = null;
      pending = '';
      if (active) setStreamConnected(false);
    };
    disconnectRef.current = close;
    setOutput('');
    setApplicationStats(null);
    setLoading(true);
    setStatusError('');
    setStreamConnected(false);

    const poll = async () => {
      if (!active || polling) return;
      polling = true;
      try {
        const [single, multi] = await Promise.all([api.agent.status(), api.multi.status()]);
        if (!active) return;
        setStatus(single);
        setMultiStatus(multi);
        setBackendOnline(true);
        setStatusError('');
        const viewed = parallel ? multi.agents[logPlatform] : single;
        const pid = viewed.running ? viewed.pid : null;
        if (pid !== lastPid) { close(); lastPid = pid; }
        if (useSSE && viewed.running && pid != null && Date.now() >= streamRetryAt) {
          if (!stream || streamPid !== pid) {
            close();
            setOutput('');
            // The stream supplies its own atomic history; do not race it with a snapshot.
            const next = new EventSource(parallel
              ? api.multi.outputStreamUrl(logPlatform, 50000) : api.agent.outputStreamUrl(50000));
            stream = next;
            streamPid = pid;
            next.onopen = () => { if (active && stream === next) setStreamConnected(true); };
            next.onmessage = event => {
              if (!active || stream !== next || !event.data) return;
              pending = (pending + event.data + '\n').slice(-2_000_000);
              if (frame == null) frame = requestAnimationFrame(() => {
                frame = null;
                const batch = pending;
                pending = '';
                if (active && stream === next) setOutput(previous => boundAgentLog(previous + batch));
              });
            };
            next.onerror = () => {
              if (stream === next) { streamRetryAt = Date.now() + 10_000; close(); }
            };
          }
        } else close();
        // Polling also retrieves the final lines after a run exits or streaming fails.
        if (!stream) {
          const text = parallel ? await api.multi.output(logPlatform, 50000) : await api.agent.output(50000);
          if (!active) return;
          setOutput(boundAgentLog(text));
        }
        if (Date.now() - lastMetrics > 30_000) {
          lastMetrics = Date.now();
          const results = await Promise.allSettled([api.metrics(), api.stats(7, parallel ? logPlatform : platform)]);
          if (!active) return;
          setMetrics(results[0].status === 'fulfilled' ? results[0].value : null);
          setApplicationStats(results[1].status === 'fulfilled' ? results[1].value : null);
        }
      } catch (error) {
        if (active) {
          setBackendOnline(false);
          setStatusError(error instanceof Error ? error.message : 'Unable to load agent status.');
          close();
        }
      } finally {
        polling = false;
        if (active) setLoading(false);
      }
    };
    refreshRef.current = async () => {
      // An action must refresh after an older in-flight poll has settled.
      while (active && polling) await new Promise(resolve => setTimeout(resolve, 20));
      await poll();
    };
    const tick = async () => {
      await poll();
      if (active) timer = setTimeout(tick, 3000);
    };
    void tick();
    return () => {
      active = false;
      clearTimeout(timer);
      close();
      refreshRef.current = async () => {};
      disconnectRef.current = () => {};
    };
  }, [parallel, logPlatform, useSSE, platform]);

  return { status, setStatus, multiStatus, setMultiStatus, metrics, applicationStats, output, setOutput,
    loading, backendOnline, statusError, streamConnected, refresh, disconnect };
}
