import { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Briefcase, FileCheck, History, Settings, User,
  BarChart3, Radar, ShieldAlert, Bot, Database, FileText, HardDrive, Activity,
  Sun, Moon, Zap, GitBranch, LineChart, Download, LogOut, LogIn,
  Users, Webhook, HelpCircle, ChevronDown, ChevronRight, MoreHorizontal,
} from 'lucide-react';
import { useTheme } from '../lib/ThemeContext';
import { useAuth } from '../lib/AuthContext';
import { getAppsByGroup, type AppEntry } from '../registry/appRegistry';

// ---------------------------------------------------------------------------
// Icon resolver — maps iconName strings from the registry to Lucide components
// ---------------------------------------------------------------------------
const ICON_MAP: Record<string, React.ComponentType<{ className?: string; 'aria-hidden'?: boolean | 'true' | 'false' }>> = {
  LayoutDashboard,
  Briefcase,
  FileCheck,
  History,
  Settings,
  User,
  BarChart3,
  Radar,
  ShieldAlert,
  Bot,
  Database,
  FileText,
  HardDrive,
  Activity,
  Zap,
  GitBranch,
  LineChart,
  Users,
  Webhook,
  HelpCircle,
};

function NavItem({ app }: { app: AppEntry }) {
  const Icon = ICON_MAP[app.iconName] ?? MoreHorizontal;
  return (
    <NavLink
      key={app.path}
      to={app.path}
      end={app.end}
      title={app.description}
      className={({ isActive }: { isActive: boolean }) =>
        `nav-link ${isActive ? 'nav-link-active' : ''}`
      }
    >
      <Icon className="w-5 h-5 shrink-0" aria-hidden="true" />
      <span>{app.label}</span>
    </NavLink>
  );
}

export default function Layout() {
  const { theme, toggle } = useTheme();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [othersOpen, setOthersOpen] = useState(false);

  // Pass empty roles for now — swap in real user roles when RBAC is wired up
  const mainApps = getAppsByGroup('main', []);
  const othersApps = getAppsByGroup('others', []);

  return (
    <div className="flex h-screen bg-bg">
      <aside className="w-64 shrink-0 flex flex-col overflow-y-auto border-r bg-surface border-border">
        {/* ── Header ───────────────────────────────────────────────────── */}
        <div className="p-5 border-b border-border">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Activity className="w-6 h-6 text-primary" />
              <h1 className="text-lg font-semibold text-text">Naukri Agent</h1>
            </div>
            <button
              onClick={toggle}
              className="p-1.5 rounded-lg transition-colors text-secondary hover:bg-surface-hover hover:text-text"
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
              title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
            >
              {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
          </div>
          <p className="text-xs mt-1 text-secondary">AI Job Application Dashboard</p>
        </div>

        {/* ── Navigation ───────────────────────────────────────────────── */}
        <nav className="flex-1 p-3 space-y-1" role="navigation" aria-label="Main navigation">
          {/* Main tabs */}
          {mainApps.map((app) => (
            <NavItem key={app.id} app={app} />
          ))}

          {/* Others section */}
          {othersApps.length > 0 && (
            <div className="pt-2">
              {/* Section divider + toggle */}
              <button
                onClick={() => setOthersOpen((v) => !v)}
                className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-semibold uppercase tracking-wider transition-colors text-secondary hover:bg-surface-hover hover:text-text"
                aria-expanded={othersOpen}
                aria-controls="others-nav-section"
              >
                <span className="flex items-center gap-2">
                  <MoreHorizontal className="w-4 h-4" />
                  Others
                </span>
                {othersOpen
                  ? <ChevronDown className="w-3.5 h-3.5" />
                  : <ChevronRight className="w-3.5 h-3.5" />
                }
              </button>

              {/* Collapsible items */}
              {othersOpen && (
                <div
                  id="others-nav-section"
                  className="mt-1 space-y-1 pl-1 border-l-2 border-border ml-2"
                >
                  {othersApps.map((app) => (
                    <NavItem key={app.id} app={app} />
                  ))}
                </div>
              )}
            </div>
          )}
        </nav>

        {/* ── Footer ───────────────────────────────────────────────────── */}
        <div className="p-4 border-t border-border space-y-2">
          {user && (
            <div className="flex items-center gap-2 text-xs px-1 text-secondary">
              <User className="w-3 h-3 shrink-0" />
              <span className="truncate">{user.email}</span>
            </div>
          )}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs text-muted">
              <Download className="w-3 h-3" />
              <span>v3.0.0</span>
            </div>
            {user ? (
              <button
                onClick={async () => { await logout(); navigate('/login', { replace: true }); }}
                className="flex items-center gap-1.5 text-xs transition-colors text-muted hover:text-danger"
                title="Sign out"
              >
                <LogOut className="w-3 h-3" />
                <span>Sign out</span>
              </button>
            ) : (
              <button
                onClick={() => navigate('/login')}
                className="flex items-center gap-1.5 text-xs transition-colors text-muted hover:text-primary"
                title="Sign in"
              >
                <LogIn className="w-3 h-3" />
                <span>Sign in</span>
              </button>
            )}
          </div>
        </div>
      </aside>

      <main className="flex-1 overflow-auto bg-bg">
        <div className="max-w-7xl mx-auto p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
