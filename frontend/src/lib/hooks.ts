import { useQuery } from '@tanstack/react-query';
import { api, type StatsResponse, type SessionStatus, type MetricsResponse } from './api';

export function useDashboard() {
  const stats = useQuery<StatsResponse>({
    queryKey: ['stats', 7],
    queryFn: () => api.stats(7),
    refetchInterval: 60_000, // Reduced from 30s to 60s
    staleTime: 30_000, // Consider data fresh for 30s
  });

  const session = useQuery<SessionStatus>({
    queryKey: ['session', 'status'],
    queryFn: () => api.session.status(),
    refetchInterval: 60_000, // Reduced from 15s to 60s
    staleTime: 30_000,
  });

  const metrics = useQuery<MetricsResponse>({
    queryKey: ['metrics'],
    queryFn: () => api.metrics(),
    refetchInterval: 120_000, // Reduced from 60s to 120s
    staleTime: 60_000,
  });

  return { stats, session, metrics };
}
