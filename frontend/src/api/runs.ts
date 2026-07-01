import { api } from './client'
import type { RunCreate, RunStatus, RunSummary } from './types'

const API_BASE = '/api/v1'

export const runsApi = {
  start: (body: RunCreate) => api.post<RunStatus>('/runs', body),
  current: () => api.get<RunStatus>('/runs/current'),
  stop: () => api.post<RunStatus>('/runs/current/stop'),
  list: (limit = 20) => api.get<RunSummary[]>(`/runs?limit=${limit}`),
  eventsUrl: (runId: number) => `${API_BASE}/runs/${runId}/events`,
}
