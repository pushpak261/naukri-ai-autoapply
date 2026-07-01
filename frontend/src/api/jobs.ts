import { api } from './client'
import type { ApplicationRecord, ConfigSummary } from './types'

export interface JobListResponse {
  items: Array<{
    id?: number
    naukri_job_id: string
    title: string
    company: string
    location: string
    experience: string
    salary: string
    url: string
    posted_date: string
    skills: string
    status?: string | null
    match_score?: number | null
    match_reasoning?: string | null
    applied_at?: string | null
  }>
  total: number
  offset: number
  limit: number
}

export const jobsApi = {
  list: (offset = 0, limit = 50, status?: string) => {
    const params = new URLSearchParams({ offset: String(offset), limit: String(limit) })
    if (status) params.set('status', status)
    return api.get<JobListResponse>(`/jobs?${params}`)
  },
  recentApplications: (limit = 20) =>
    api.get<ApplicationRecord[]>(`/applications/recent?limit=${limit}`),
  configSummary: () => api.get<ConfigSummary>('/config/summary'),
}
