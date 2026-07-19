const BASE_URL = '/api';

// ---------------------------------------------------------------------------
// JWT access token management
// ---------------------------------------------------------------------------
let accessToken: string | null = null;
let refreshPromise: Promise<string | null> | null = null;
let refreshWaiters: Array<() => void> = [];

export function setAuthToken(token: string | null) {
  accessToken = token;
}

export function getAuthToken(): string | null {
  return accessToken;
}

/** Wait for any in-flight token refresh to complete, then return the token. */
async function waitForRefresh(): Promise<string | null> {
  if (!refreshPromise) return accessToken;
  await new Promise<void>((resolve) => refreshWaiters.push(resolve));
  return accessToken;
}

async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    try {
      const res = await fetch(`${BASE_URL}/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!res.ok) {
        accessToken = null;
        return null;
      }
      const data = await res.json();
      accessToken = data.access_token;
      return data.access_token;
    } catch {
      accessToken = null;
      return null;
    } finally {
      refreshPromise = null;
      refreshWaiters.forEach((r) => r());
      refreshWaiters = [];
    }
  })();
  return refreshPromise;
}

// ---------------------------------------------------------------------------
// Base fetch helpers
// ---------------------------------------------------------------------------

async function fetchJSON<T>(url: string, options?: RequestInit, skipAuth = false): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers as Record<string, string> | undefined),
  };

  // If a token refresh is in-flight, wait for it before sending this request
  let token = accessToken;
  if (refreshPromise) {
    token = await waitForRefresh();
  }

  // No token yet but auth is required – proactively refresh so we never
  // send a request that will 401 (avoids noisy 401 logs on page load).
  if (!token && !skipAuth) {
    token = await refreshAccessToken();
  }

  if (token && !skipAuth) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  let res = await fetch(`${BASE_URL}${url}`, {
    ...options,
    headers,
    credentials: 'include',
  });

  // On 401, attempt token refresh and retry once
  if (res.status === 401 && !skipAuth) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      headers['Authorization'] = `Bearer ${newToken}`;
      res = await fetch(`${BASE_URL}${url}`, {
        ...options,
        headers,
        credentials: 'include',
      });
    }
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function fetchFormData<T>(url: string, formData: FormData): Promise<T> {
  const headers: Record<string, string> = {};

  let token = accessToken;
  if (refreshPromise) {
    token = await waitForRefresh();
  }
  if (!token) {
    token = await refreshAccessToken();
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  let res = await fetch(`${BASE_URL}${url}`, {
    method: 'POST',
    body: formData,
    headers,
    credentials: 'include',
  });
  if (res.status === 401) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      headers['Authorization'] = `Bearer ${newToken}`;
      res = await fetch(`${BASE_URL}${url}`, {
        method: 'POST',
        body: formData,
        headers,
        credentials: 'include',
      });
    }
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function fetchText(url: string): Promise<string> {
  const headers: Record<string, string> = {};

  let token = accessToken;
  if (refreshPromise) {
    token = await waitForRefresh();
  }
  if (!token) {
    token = await refreshAccessToken();
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  let res = await fetch(`${BASE_URL}${url}`, { headers, credentials: 'include' });
  if (res.status === 401) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      headers['Authorization'] = `Bearer ${newToken}`;
      res = await fetch(`${BASE_URL}${url}`, { headers, credentials: 'include' });
    }
  }
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.text();
}

export interface StatsResponse {
  stats: { total: number; applied: number; skipped: number; failed: number };
  today_applied: number;
  total_jobs_found: number;
  total_applied: number;
  total_skipped: number;
  total_failed: number;
  recent_applications: RecentApplication[];
  recent_runs: RunLog[];
  daily_cap: number;
  match_threshold: number;
}

export interface RecentApplication {
  job_title: string;
  company: string;
  location: string;
  match_score: number;
  status: string;
  applied_at: string;
  url: string;
  error_message: string;
}

export interface RunLog {
  id: number;
  started_at: string;
  ended_at: string;
  keywords: string;
  found: number;
  applied: number;
  skipped: number;
  failed: number;
  status: string;
}

export interface JobItem {
  id: number;
  naukri_job_id: string;
  title: string;
  company: string;
  location: string;
  experience: string;
  salary: string;
  skills: string;
  url: string;
  posted_date: string;
  openings: number;
  has_company_logo: boolean;
  source: string;
  scraped_at: string;
  application_status: string | null;
  match_score: number | null;
}

export interface JobDetail extends JobItem {
  description: string;
  application: {
    match_score: number;
    status: string;
    match_reasoning: string;
    matching_skills: string;
    missing_skills: string;
    error_message: string;
    applied_at: string;
  } | null;
}

export interface ApplicationItem {
  id: number;
  job_id: number;
  job_title: string;
  company: string;
  location: string;
  url: string;
  match_score: number;
  status: string;
  source: string;
  match_reasoning: string;
  matching_skills: string;
  missing_skills: string;
  error_message: string;
  applied_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
}

export interface ConfigResponse {
  naukri: { email: string; has_password: boolean; use_otp_login: boolean; mobile_number: string };
  ai: { use_gemini: boolean; enable_matching: boolean; has_api_key: boolean; model: string; fallback_model: string | null; abort_on_quota: boolean; temperature: number; max_output_tokens: number };
  resume: { path: string };
  search: { keywords: string[]; locations: string[]; experience_min: number; experience_max: number; salary_min: number; freshness: number; max_pages: number; sort_by: string; enable_heuristics: boolean };
  application: { daily_cap: number; match_score_threshold: number; max_retries?: number; answer_questions_with_pdf: boolean; delay_between_applies_min: number; delay_between_applies_max: number; skip_external_apply: boolean; dry_run: boolean; enable_project_indexer: boolean };
  profile: { current_ctc: string; expected_ctc: string; notice_period: string; current_location: string; preferred_locations: string[]; total_experience: string };
  logging: { level: string; log_to_file: boolean };
  notifications?: { email_notifications_enabled: boolean; email_recipient: string; notify_on_apply: boolean; notify_on_failure: boolean; notify_on_scam: boolean; notify_on_match: boolean };
  rate_limits?: { rate_limit_capacity: number; rate_limit_refill_rate: number };
}

export interface StatusInfo {
  value: string;
  label: string;
  color: string;
}

export interface CompanyDistribution {
  company: string;
  count: number;
}

export interface LocationDistribution {
  location: string;
  count: number;
}

export interface KeywordPerformance {
  keyword: string;
  found: number;
  applied: number;
  skipped: number;
  failed: number;
}

export interface DailyTimeline {
  date: string;
  applied: number;
  skipped: number;
  failed: number;
  total: number;
}

export interface SuccessRateTrend {
  date: string;
  total: number;
  applied: number;
  success_rate: number;
}

export interface AgentStatus {
  running: boolean;
  pid: number | null;
  started_at: string | null;
  uptime_seconds: number | null;
  last_run: RunLog | null;
  platform?: 'naukri' | 'linkedin' | null;
}

export interface MatchCacheEntry {
  key: string;
  resume_hash: string;
  job_id: string;
  score: number;
  should_apply: boolean;
  matching_skills: string[];
  missing_skills: string[];
  reasoning: string;
}

export interface MatchCacheStats {
  total_entries: number;
  avg_score: number;
  would_apply: number;
  would_skip: number;
}

export interface MetricsResponse {
  total_runs: number;
  jobs_applied: number;
  jobs_failed: number;
  api_calls: number;
  duration_seconds: number;
}

export interface LogFile {
  name: string;
  path: string;
  size: number;
  modified: string;
  type: string;
}

export interface LogContent {
  content: string;
  total_lines: number;
  showing: number;
  name: string;
}

export interface SessionStatus {
  exists: boolean;
  valid: boolean;
  cookie_count: number;
  last_modified: string;
  message: string;
}

export interface BackupItem {
  name: string;
  size: number;
  created: string;
}

// New types for the innovative features

export interface SalaryBenchmark {
  title: string;
  company: string;
  location: string;
  low: number;
  high: number;
  avg: number;
  raw: string;
}

export interface SkillDemandItem {
  skill: string;
  count: number;
  avg_score: number;
  max_score: number;
}

export interface CompetitorCompany {
  company: string;
  avg_match_score: number;
  application_count: number;
}

export interface WinRateBracket {
  bracket: string;
  total: number;
  applied: number;
  success_rate: number;
}

export interface AutopilotConfig {
  enabled: boolean;
  schedule: { type: string; time: string; days: string[] };
  throttle: { top_tier_daily: number; startup_daily: number; default_daily: number };
  priority_rules: { condition: string; action: string; enabled: boolean }[];
  company_blacklist: string[];
  company_whitelist: string[];
  tier_map: Record<string, string>;
}

export interface ScamAnalysisItem {
  job_id: number;
  job_title: string;
  company: string;
  location: string;
  skills: string;
  score: number;
  raw_score: number;
  category: string;
  reasons: string[];
}

export interface ScamAnalysisResponse {
  risk_distribution: { name: string; value: number; color: string }[];
  score_distribution: ScamAnalysisItem[];
  highest_risk: ScamAnalysisItem[];
  summary: {
    total_jobs: number;
    avg_score: number;
    safe_count: number;
    moderate_count: number;
    suspicious_count: number;
  };
}

export interface ResumeOptimizationItem {
  skill: string;
  matching: number;
  missing: number;
  total: number;
  matchRate: number;
}

export interface KeywordDensityItem {
  keyword: string;
  count: number;
  avgInListings: number;
  yourCount: number;
  gap: number;
}

export interface SkillBreakdownItem {
  name: string;
  count: number;
  color: string;
}

export interface ResumeOptimizationResponse {
  resume: { exists: boolean; name: string; email: string; skills_count: number; total_experience_years: number };
  skills_data: ResumeOptimizationItem[];
  keyword_density: KeywordDensityItem[];
  skill_breakdown: SkillBreakdownItem[];
  ats: { score: number; label: string };
  summary: { total_applications: number; total_jobs: number; total_skills_analyzed: number; has_resume: boolean };
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  email: string;
}

export interface MeResponse {
  email: string;
  is_logged_in: boolean;
  naukri_configured: boolean;
}

export const SSE_BASE = BASE_URL;

export const api = {
  auth: {
    login: (email: string, password: string) =>
      fetchJSON<LoginResponse>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      }, true),
    register: (email: string, password: string) =>
      fetchJSON<LoginResponse>('/auth/register', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      }, true),
    checkRegistered: () =>
      fetchJSON<{ registered: boolean; email: string }>('/auth/register/check', {}, true),
    logout: () =>
      fetchJSON<{ status: string; message: string }>('/auth/logout', { method: 'POST' }, true),
    me: () =>
      fetchJSON<MeResponse>('/auth/me'),
  },
  health: () => fetchJSON<{ status: string }>('/health'),
  stats: (days = 7) => fetchJSON<StatsResponse>(`/stats?days=${days}`),
  jobs: (page = 1, perPage = 20, search = '', status = '', sort = 'newest', matchScoreMin = 0, matchScoreMax = 100, source = '') =>
    fetchJSON<PaginatedResponse<JobItem>>(`/jobs?page=${page}&per_page=${perPage}&search=${encodeURIComponent(search)}&status=${encodeURIComponent(status)}&sort=${sort}&match_score_min=${matchScoreMin}&match_score_max=${matchScoreMax}&source=${encodeURIComponent(source)}`),
  job: (id: number) => fetchJSON<JobDetail>(`/jobs/${id}`),
  applications: (page = 1, perPage = 20, status = '', sort = 'newest', source = '') =>
    fetchJSON<PaginatedResponse<ApplicationItem>>(`/applications?page=${page}&per_page=${perPage}&status=${encodeURIComponent(status)}&sort=${sort}&source=${encodeURIComponent(source)}&_t=${Date.now()}`),
  runLogs: (limit = 20) => fetchJSON<{ items: RunLog[] }>(`/run-logs?limit=${limit}`),
  runJobs: (runId: number) => fetchJSON<{ items: ApplicationItem[]; run: RunLog }>(`/run-logs/${runId}/jobs`),
  config: () => fetchJSON<ConfigResponse>('/config'),
  updateConfig: (data: Record<string, unknown>) =>
    fetchJSON<{ status: string; message: string }>('/config', { method: 'PUT', body: JSON.stringify(data) }),
  resumeProfile: () => fetchJSON<{ exists: boolean; profile: Record<string, unknown> | null }>('/resume-profile'),
  applicationStatuses: () => fetchJSON<{ statuses: StatusInfo[] }>('/application-statuses'),

  resume: {
    upload: (file: File) => {
      const fd = new FormData();
      fd.append('file', file);
      return fetchFormData<{ status: string; profile: Record<string, unknown>; file_path: string }>('/resume/upload', fd);
    },
    saveProfile: (data: Record<string, unknown>) =>
      fetchJSON<{ status: string; profile: Record<string, unknown> }>('/resume/profile', { method: 'PUT', body: JSON.stringify(data) }),
  },

  analytics: {
    companyDistribution: (limit = 15) => fetchJSON<{ items: CompanyDistribution[] }>(`/analytics/company-distribution?limit=${limit}`),
    locationDistribution: () => fetchJSON<{ items: LocationDistribution[] }>('/analytics/location-distribution'),
    keywordPerformance: () => fetchJSON<{ items: KeywordPerformance[] }>('/analytics/keyword-performance'),
    dailyTimeline: (days = 30) => fetchJSON<{ items: DailyTimeline[] }>(`/analytics/daily-timeline?days=${days}`),
    successRateTrend: (days = 30) => fetchJSON<{ items: SuccessRateTrend[] }>(`/analytics/success-rate-trend?days=${days}`),
  },

  agent: {
    start: (platform: 'naukri' | 'linkedin' = 'naukri') =>
      fetchJSON<{ status: string; message: string; pid?: number; command?: string }>(`/agent/start?platform=${platform}`, { method: 'POST' }),
    stop: () => fetchJSON<{ status: string; message: string }>('/agent/stop', { method: 'POST' }),
    status: () => fetchJSON<AgentStatus>('/agent/status'),
    output: (lines = 50) => fetchText(`/agent/output?lines=${lines}`),
    outputStreamUrl: () => `${SSE_BASE}/agent/output/stream`,
  },

  cache: {
    matchCache: (search = '') => fetchJSON<{ items: MatchCacheEntry[]; total: number }>(`/cache/match-cache?search=${encodeURIComponent(search)}`),
    matchCacheStats: () => fetchJSON<MatchCacheStats>('/cache/match-cache/stats'),
    clearMatchCache: () => fetchJSON<{ status: string; message: string }>('/cache/match-cache', { method: 'DELETE' }),
  },

  metrics: () => fetchJSON<MetricsResponse>('/metrics'),

  logs: {
    list: () => fetchJSON<{ items: LogFile[] }>('/logs'),
    read: (logPath: string, maxLines = 200) => fetchJSON<LogContent>(`/logs/read?log_path=${encodeURIComponent(logPath)}&max_lines=${maxLines}`),
  },

  session: {
    status: () => fetchJSON<SessionStatus>('/session/status'),
    clear: () => fetchJSON<{ status: string; message: string }>('/session', { method: 'DELETE' }),
  },

  scamAnalysis: () => fetchJSON<ScamAnalysisResponse>('/scam-detector/analysis'),
  resumeOptimization: () => fetchJSON<ResumeOptimizationResponse>('/resume-optimization/analysis'),

  pipelineJobs: (source = '') =>
    fetchJSON<PipelineJobsResponse>(`/pipeline/jobs?source=${encodeURIComponent(source)}`),
  pipelineDebug: (source = '') =>
    fetchJSON<PipelineDebugResponse>(`/pipeline/debug?source=${encodeURIComponent(source)}`),

  // ---- New feature endpoints ----

  marketIntel: {
    salaryBenchmarks: () => fetchJSON<{ items: SalaryBenchmark[]; summary: { total_listings: number; average_market_ctc: number; min_market_ctc: number; max_market_ctc: number } }>('/market-intel/salary-benchmarks'),
    skillDemand: () => fetchJSON<{ items: SkillDemandItem[] }>('/market-intel/skill-demand'),
    competitorCompanies: () => fetchJSON<{ items: CompetitorCompany[] }>('/market-intel/competitor-companies'),
    winRatePrediction: () => fetchJSON<{ items: WinRateBracket[] }>('/market-intel/win-rate-prediction'),
  },

  autopilot: {
    config: () => fetchJSON<AutopilotConfig>('/autopilot/config'),
    updateConfig: (data: Record<string, unknown>) =>
      fetchJSON<{ status: string; message: string }>('/autopilot/config', { method: 'PUT', body: JSON.stringify(data) }),
    blacklist: () => fetchJSON<{ blacklist: string[]; whitelist: string[] }>('/autopilot/blacklist'),
    addToBlacklist: (company: string) =>
      fetchJSON<{ status: string; company: string; blacklist: string[] }>('/autopilot/blacklist', { method: 'POST', body: JSON.stringify({ company }) }),
    removeFromBlacklist: (company: string) =>
      fetchJSON<{ status: string; company: string; blacklist: string[] }>('/autopilot/blacklist', { method: 'DELETE', body: JSON.stringify({ company }) }),
    addToWhitelist: (company: string) =>
      fetchJSON<{ status: string; company: string; whitelist: string[] }>('/autopilot/whitelist', { method: 'POST', body: JSON.stringify({ company }) }),
    removeFromWhitelist: (company: string) =>
      fetchJSON<{ status: string; company: string; whitelist: string[] }>('/autopilot/whitelist', { method: 'DELETE', body: JSON.stringify({ company }) }),
  },

  exportData: {
    applicationsCsv: () => `${SSE_BASE}/export/applications/csv`,
    jobsCsv: () => `${SSE_BASE}/export/jobs/csv`,
    statsJson: () => `${SSE_BASE}/export/stats/json`,
    full: () => `${SSE_BASE}/export/full`,
  },

  // ---- Accounts (Feature 12) ----
  accounts: {
    list: () => fetchJSON<{ items: AccountItem[] }>('/accounts'),
    create: (data: { email: string; password: string; name?: string; is_primary?: boolean }) =>
      fetchJSON<{ status: string; account: AccountItem }>('/accounts', { method: 'POST', body: JSON.stringify(data) }),
    update: (id: number, data: Record<string, unknown>) =>
      fetchJSON<{ status: string; account: AccountItem }>(`/accounts/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    delete: (id: number) =>
      fetchJSON<{ status: string; message: string }>(`/accounts/${id}`, { method: 'DELETE' }),
    activate: (id: number) =>
      fetchJSON<{ status: string; message: string; account: AccountItem }>(`/accounts/${id}/activate`, { method: 'POST' }),
  },

  // ---- Webhooks (Feature 9) ----
  webhooks: {
    list: () => fetchJSON<{ items: WebhookItem[] }>('/webhooks'),
    create: (data: { name: string; url: string; secret?: string; events?: string }) =>
      fetchJSON<{ status: string; webhook: WebhookItem }>('/webhooks', { method: 'POST', body: JSON.stringify(data) }),
    update: (id: number, data: Record<string, unknown>) =>
      fetchJSON<{ status: string; webhook: WebhookItem }>(`/webhooks/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    delete: (id: number) =>
      fetchJSON<{ status: string }>(`/webhooks/${id}`, { method: 'DELETE' }),
    test: (id: number) =>
      fetchJSON<{ status: string; result: Record<string, unknown> }>(`/webhooks/${id}/test`, { method: 'POST' }),
  },

  // ---- Application Retry & Sync (Features 3 & 6) ----
  applicationsExtra: {
    retry: (appId: number) =>
      fetchJSON<{ status: string; message: string; app_id: number; retry_count: number }>(`/applications/${appId}/retry`, { method: 'POST' }),
    retryAllFailed: () =>
      fetchJSON<{ status: string; message: string; count: number }>('/applications/retry-all-failed', { method: 'POST' }),
    syncStatus: () =>
      fetchJSON<{ status: string; message: string; synced_count: number; synced_at: string }>('/applications/sync-status', { method: 'POST' }),
    getSyncStatus: () =>
      fetchJSON<{ items: SyncStatusItem[] }>('/applications/sync-status'),
  },

  // ---- Import (Feature 5) ----
  importFull: (data: Record<string, unknown>) =>
    fetchJSON<{ status: string; message: string; counts: Record<string, number> }>('/import/full', { method: 'POST', body: JSON.stringify(data) }),

  // ---- LinkedIn Config ----
  linkedinConfig: {
    get: () => fetchJSON<LinkedInConfig>('/config/linkedin'),
    update: (data: Record<string, unknown>) =>
      fetchJSON<{ status: string; message: string }>('/config/linkedin', { method: 'PUT', body: JSON.stringify(data) }),
  },

  // ---- Sessions (Feature 2) ----
  sessions: {
    list: () => fetchJSON<{ items: SessionFileItem[] }>('/sessions/list'),
    clear: (account?: string) =>
      fetchJSON<{ status: string; message: string }>(`/session${account ? `?account=${encodeURIComponent(account)}` : ''}`, { method: 'DELETE' }),
  },

  // ---- Backup Restore (Feature 11) ----
  backups: {
    list: () => fetchJSON<{ items: BackupItem[] }>('/backups'),
    create: () => fetchJSON<{ status: string; message: string }>('/backups/create', { method: 'POST' }),
    restore: (name: string) =>
      fetchJSON<{ status: string; message: string }>(`/backups/restore?name=${encodeURIComponent(name)}`, { method: 'POST' }),
  },

  // ---- Clear All Data ----
  clearAll: () =>
    fetchJSON<{ status: string; message: string; details: string[] }>('/data/clear-all', { method: 'DELETE' }),
};

// New types for the features above
export interface AccountItem {
  id: number;
  email: string;
  name: string;
  is_active: boolean;
  is_primary: boolean;
  has_password?: boolean;
  created_at: string;
  last_used_at: string | null;
}

export interface WebhookItem {
  id: number;
  name: string;
  url: string;
  events: string[];
  is_active: boolean;
  failure_count: number;
  last_triggered_at: string | null;
  created_at: string;
}

export interface SyncStatusItem {
  id: number;
  title: string;
  company: string;
  naukri_status: string;
  last_synced: string | null;
}

export interface SessionFileItem {
  name: string;
  file: string;
  size: number;
  modified: string;
}

export interface PipelineStage {
  id: string;
  label: string;
  description: string;
  count: number;
  jobs: PipelineJobItem[];
}

export interface PipelineJobItem {
  id: number;
  naukri_job_id: string;
  title: string;
  company: string;
  location: string;
  experience: string;
  salary: string;
  skills: string;
  url: string;
  posted_date: string;
  openings: number;
  has_company_logo: boolean;
  source: string;
  scraped_at: string;
  stage: string;
  filter_reason: string | null;
}

export interface PipelineJobsResponse {
  stages: PipelineStage[];
  summary: Record<string, number>;
}

// ---- Pipeline Debug types ----

export interface PipelineDebugItem {
  id: number;
  title: string;
  company: string;
  location: string;
  experience: string;
  salary: string;
  skills: string;
  url: string;
  posted_date: string;
  openings: number;
  source: string;
  scraped_at: string;
  filter_reason: string | null;
  filter_category: string | null;
  scam_details: string[] | null;
}

export interface PipelineDebugResponse {
  summary: {
    total_scraped: number;
    passed_all_filters: number;
    filtered_out: number;
  };
  filter_breakdown: Record<string, number>;
  filter_labels: Record<string, string>;
  pre_filter: PipelineDebugItem[];
  post_filter: PipelineDebugItem[];
  filtered_out: PipelineDebugItem[];
}

export interface LinkedInConfig {
  configured: boolean;
  email: string;
  has_password: boolean;
  two_factor_code: boolean;
  ai: {
    use_gemini: boolean;
    has_api_key: boolean;
    model: string;
    enable_matching: boolean;
  };
  resume: {
    path: string;
    exists: boolean;
  };
  search: {
    keywords: string[];
    locations: string[];
    work_type: string;
    freshness: string;
    max_pages: number;
    sort_by: string;
  };
  application: {
    daily_cap: number;
    match_score_threshold: number;
    easy_apply_only: boolean;
    dry_run: boolean;
  };
}
