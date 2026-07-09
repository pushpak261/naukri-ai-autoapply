/**
 * App Registry — single source of truth for every navigable tab in the UI.
 *
 * Each entry describes one tab:
 *   - id          : stable, unique key (used for RBAC permission checks)
 *   - label       : display name shown in the sidebar
 *   - path        : react-router route path
 *   - icon        : lucide-react icon name (imported by consumers)
 *   - group       : 'main' items appear directly in the sidebar;
 *                   'others' items are grouped under the collapsible "Others" section
 *   - description : one-line summary of what the tab does
 *   - requiredRoles: roles allowed to see/access this tab.
 *                    Empty array = all authenticated users.
 *                    When you wire up RBAC, filter the registry against the
 *                    logged-in user's roles before rendering the nav.
 */

export type AppRole =
  | 'admin'
  | 'manager'
  | 'analyst'
  | 'user';

export type AppGroup = 'main' | 'others';

export interface AppEntry {
  id: string;
  label: string;
  path: string;
  /** lucide-react icon identifier (string key). Layout imports and resolves this. */
  iconName: string;
  group: AppGroup;
  description: string;
  /**
   * Roles that are permitted to access this app.
   * Empty array means all authenticated roles are allowed.
   * Populate per-entry to enforce role-based access control.
   */
  requiredRoles: AppRole[];
  /** If true the NavLink uses `end` matching (exact path only). */
  end?: boolean;
}

// ---------------------------------------------------------------------------
// Registry
// ---------------------------------------------------------------------------

export const APP_REGISTRY: AppEntry[] = [
  // ── Main group ────────────────────────────────────────────────────────────
  {
    id: 'dashboard',
    label: 'Dashboard',
    path: '/',
    iconName: 'LayoutDashboard',
    group: 'main',
    description: 'Live overview of agent activity, stats, and current run progress.',
    requiredRoles: [],
    end: true,
  },
  {
    id: 'market-intelligence',
    label: 'Market Intel',
    path: '/market-intelligence',
    iconName: 'LineChart',
    group: 'main',
    description: 'Job-market trends, salary benchmarks, and demand signals.',
    requiredRoles: [],
  },
  {
    id: 'skills-gap',
    label: 'Skills Gap',
    path: '/skills-gap',
    iconName: 'Radar',
    group: 'main',
    description: 'Compare your skill set against target roles and surface gaps.',
    requiredRoles: [],
  },
  {
    id: 'autopilot',
    label: 'Auto-Pilot',
    path: '/autopilot',
    iconName: 'Zap',
    group: 'main',
    description: 'Configure and launch fully automated apply runs.',
    requiredRoles: [],
  },
  {
    id: 'agent-control',
    label: 'Agent Control',
    path: '/agent-control',
    iconName: 'Bot',
    group: 'main',
    description: 'Start, pause, stop, and monitor the underlying browser agent.',
    requiredRoles: [],
  },
  {
    id: 'applications',
    label: 'Applications',
    path: '/applications',
    iconName: 'FileCheck',
    group: 'main',
    description: 'Full history of every job application submitted by the agent.',
    requiredRoles: [],
  },
  {
    id: 'run-logs',
    label: 'Run Logs',
    path: '/run-logs',
    iconName: 'History',
    group: 'main',
    description: 'Per-run summaries, timelines, and outcome breakdowns.',
    requiredRoles: [],
  },
  {
    id: 'cache-explorer',
    label: 'Match Cache',
    path: '/cache-explorer',
    iconName: 'Database',
    group: 'main',
    description: 'Inspect and manage the job-match score cache.',
    requiredRoles: [],
  },
  {
    id: 'config',
    label: 'Configuration',
    path: '/config',
    iconName: 'Settings',
    group: 'main',
    description: 'Search preferences, filters, and apply-run settings.',
    requiredRoles: [],
  },
  {
    id: 'resume',
    label: 'Resume',
    path: '/resume',
    iconName: 'User',
    group: 'main',
    description: 'View and manage the resume used for applications.',
    requiredRoles: [],
  },
  {
    id: 'screening-questions',
    label: 'Screening Q&A',
    path: '/screening-questions',
    iconName: 'HelpCircle',
    group: 'main',
    description: 'Review and tune auto-answers to employer screening questions.',
    requiredRoles: [],
  },

  // ── Others group ──────────────────────────────────────────────────────────
  {
    id: 'analytics',
    label: 'Analytics',
    path: '/analytics',
    iconName: 'BarChart3',
    group: 'others',
    description: 'Deep-dive charts and metrics across all application activity.',
    requiredRoles: [],
  },
  {
    id: 'pipeline-debugger',
    label: 'Pipeline',
    path: '/pipeline-debugger',
    iconName: 'GitBranch',
    group: 'others',
    description: 'Visualise and debug the agent pipeline DAG step-by-step.',
    requiredRoles: [],
  },
  {
    id: 'scam-detector',
    label: 'Scam Detector',
    path: '/scam-detector',
    iconName: 'ShieldAlert',
    group: 'others',
    description: 'Analyse job listings for red flags and fraudulent patterns.',
    requiredRoles: [],
  },
  {
    id: 'jobs',
    label: 'Jobs',
    path: '/jobs',
    iconName: 'Briefcase',
    group: 'others',
    description: 'Browse and search the raw job feed fetched by the agent.',
    requiredRoles: [],
  },
  {
    id: 'log-viewer',
    label: 'Log Viewer',
    path: '/log-viewer',
    iconName: 'FileText',
    group: 'others',
    description: 'Real-time and historical file-level log output.',
    requiredRoles: [],
  },
  {
    id: 'backups',
    label: 'Backups',
    path: '/backups',
    iconName: 'HardDrive',
    group: 'others',
    description: 'Manage database snapshots and restore points.',
    requiredRoles: [],
  },
  {
    id: 'accounts',
    label: 'Accounts',
    path: '/accounts',
    iconName: 'Users',
    group: 'others',
    description: 'Manage Naukri accounts and credential configurations.',
    requiredRoles: ['admin', 'manager'],
  },
  {
    id: 'webhooks',
    label: 'Webhooks',
    path: '/webhooks',
    iconName: 'Webhook',
    group: 'others',
    description: 'Configure outbound webhook endpoints for event notifications.',
    requiredRoles: ['admin'],
  },
];

// ---------------------------------------------------------------------------
// Derived helpers
// ---------------------------------------------------------------------------

/** All apps in display order, optionally filtered by the current user's roles. */
export function getAccessibleApps(userRoles: AppRole[] = []): AppEntry[] {
  return APP_REGISTRY.filter(
    (app) =>
      app.requiredRoles.length === 0 ||
      app.requiredRoles.some((r) => userRoles.includes(r)),
  );
}

/** Returns apps belonging to a specific group. */
export function getAppsByGroup(group: AppGroup, userRoles: AppRole[] = []): AppEntry[] {
  return getAccessibleApps(userRoles).filter((app) => app.group === group);
}

/** Look up a single entry by its stable id. */
export function getAppById(id: string): AppEntry | undefined {
  return APP_REGISTRY.find((app) => app.id === id);
}
