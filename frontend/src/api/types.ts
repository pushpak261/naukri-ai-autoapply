export interface RunStatus {
  run_id: number | null
  status: string
  phase: string
  dry_run: boolean
  jobs_found: number
  jobs_applied: number
  jobs_skipped: number
  jobs_failed: number
  daily_cap_remaining: number
  processed_count: number
  total_queued: number
  error?: string | null
}

export interface RunCreate {
  dry_run?: boolean
  cap?: number | null
  threshold?: number | null
}

export interface AgentEvent {
  id: string
  run_id: number
  type: string
  timestamp: string
  data: Record<string, unknown>
}

export interface JobCard {
  naukri_job_id: string
  title: string
  company: string
  location?: string
  experience?: string
  salary?: string
  status: string
  url?: string
  posted_date?: string
  skills?: string
  is_verified?: boolean | null
  company_rating?: number | null
  is_external_apply?: boolean | null
  external_apply_url?: string | null
  hiring_for?: string | null
  is_consultant_post?: boolean | null
  match_score?: number | null
  heuristic_score?: number | null
  match_reasoning?: string | null
  reason?: string | null
}

export interface RunSummary {
  id: number
  started_at: string
  ended_at: string
  keywords: string[]
  found: number
  applied: number
  skipped: number
  failed: number
  status: string
}

export interface ApplicationRecord {
  job_title: string
  company: string
  location: string
  match_score: number
  status: string
  applied_at: string
  url: string
  error_message: string
}

export interface ConfigSummary {
  keywords: string[]
  locations: string[]
  experience_min: number
  experience_max: number
  daily_cap: number
  match_score_threshold: number
  dry_run: boolean
  require_verified_job: boolean
  min_company_rating: number
  big_companies: string[]
  excluded_companies: string[]
  excluded_title_keywords: string[]
  ai_model: string
}
