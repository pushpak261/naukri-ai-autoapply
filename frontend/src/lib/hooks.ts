import { useQuery } from '@tanstack/react-query';
import { api, type StatsResponse, type SessionStatus, type MetricsResponse } from './api';

export function useDashboard() {
  const stats = useQuery<StatsResponse>({
    queryKey: ['stats', 7],
    queryFn: () => api.stats(7),
    refetchInterval: 30_000,
  });

  const session = useQuery<SessionStatus>({
    queryKey: ['session', 'status'],
    queryFn: () => api.session.status(),
    refetchInterval: 15_000,
  });

  const metrics = useQuery<MetricsResponse>({
    queryKey: ['metrics'],
    queryFn: () => api.metrics(),
    refetchInterval: 60_000,
  });

  return { stats, session, metrics };
}
