import { create } from 'zustand'
import type { AgentEvent, JobCard, RunStatus } from '@/api/types'

interface RunStore {
  runId: number | null
  phase: string
  status: string
  counters: Partial<RunStatus>
  jobs: Map<string, JobCard>
  expandedJobId: string | null
  toasts: Array<{ id: string; message: string; type: 'info' | 'error' | 'success' }>
  setRunId: (id: number | null) => void
  applyEvent: (event: AgentEvent) => void
  setExpandedJobId: (id: string | null) => void
  addToast: (message: string, type?: 'info' | 'error' | 'success') => void
  removeToast: (id: string) => void
  reset: () => void
}

export const useRunStore = create<RunStore>((set, get) => ({
  runId: null,
  phase: 'idle',
  status: 'idle',
  counters: {},
  jobs: new Map(),
  expandedJobId: null,
  toasts: [],

  setRunId: (id) => set({ runId: id }),

  applyEvent: (event) => {
    const { type, data } = event

    if (type === 'counters_updated') {
      set({
        phase: String(data.phase || get().phase),
        counters: {
          jobs_found: Number(data.jobs_found ?? 0),
          jobs_applied: Number(data.jobs_applied ?? 0),
          jobs_skipped: Number(data.jobs_skipped ?? 0),
          jobs_failed: Number(data.jobs_failed ?? 0),
          daily_cap_remaining: Number(data.daily_cap_remaining ?? 0),
          processed_count: Number(data.processed_count ?? 0),
          total_queued: Number(data.total_queued ?? 0),
        },
      })
      return
    }

    if (type === 'job_updated' && data.naukri_job_id) {
      const id = String(data.naukri_job_id)
      const jobs = new Map(get().jobs)
      const existing = jobs.get(id)
      jobs.set(id, {
        naukri_job_id: id,
        title: String(data.title || existing?.title || ''),
        company: String(data.company || existing?.company || ''),
        location: data.location != null ? String(data.location) : existing?.location,
        experience: data.experience != null ? String(data.experience) : existing?.experience,
        salary: data.salary != null ? String(data.salary) : existing?.salary,
        status: String(data.status || existing?.status || ''),
        url: data.url != null ? String(data.url) : existing?.url,
        posted_date: data.posted_date != null ? String(data.posted_date) : existing?.posted_date,
        skills: data.skills != null ? String(data.skills) : existing?.skills,
        is_verified: data.is_verified as boolean | null | undefined ?? existing?.is_verified,
        company_rating: data.company_rating as number | null | undefined ?? existing?.company_rating,
        is_external_apply:
          data.is_external_apply as boolean | null | undefined ?? existing?.is_external_apply,
        external_apply_url:
          data.external_apply_url != null
            ? String(data.external_apply_url)
            : existing?.external_apply_url,
        hiring_for:
          data.hiring_for != null ? String(data.hiring_for) : existing?.hiring_for,
        is_consultant_post:
          data.is_consultant_post as boolean | null | undefined ?? existing?.is_consultant_post,
        match_score: data.match_score as number | null | undefined ?? existing?.match_score,
        heuristic_score: data.heuristic_score as number | null | undefined ?? existing?.heuristic_score,
        match_reasoning: data.match_reasoning != null ? String(data.match_reasoning) : existing?.match_reasoning,
        reason: data.reason != null ? String(data.reason) : existing?.reason,
      })
      set({ jobs })
      return
    }

    if (type === 'login_started') set({ phase: 'logging_in', status: 'running' })
    if (type === 'search_started') set({ phase: 'searching' })
    if (type === 'run_started') set({ status: 'running', phase: 'starting' })
    if (type === 'run_completed') {
      set({ status: 'completed', phase: 'completed' })
      get().addToast('Run completed', 'success')
    }
    if (type === 'run_interrupted') {
      set({ status: 'interrupted', phase: 'interrupted' })
      get().addToast('Run interrupted', 'info')
    }
    if (type === 'login_failed') {
      set({ status: 'error', phase: 'error' })
      get().addToast('Login failed — check the Chromium window', 'error')
    }
    if (type === 'run_error') {
      set({ status: 'error', phase: 'error' })
      get().addToast(String(data.message || 'Run error'), 'error')
    }
  },

  setExpandedJobId: (id) => set({ expandedJobId: id }),

  addToast: (message, type = 'info') => {
    const id = crypto.randomUUID()
    set({ toasts: [...get().toasts, { id, message, type }] })
    setTimeout(() => get().removeToast(id), 5000)
  },

  removeToast: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),

  reset: () =>
    set({
      runId: null,
      phase: 'idle',
      status: 'idle',
      counters: {},
      jobs: new Map(),
      expandedJobId: null,
    }),
}))
