import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Briefcase, FileCheck, History, Settings, User,
  BarChart3, Radar, ShieldAlert, Bot, Database, FileText, HardDrive, Activity,
  Sun, Moon, Zap, GitBranch, LineChart, Download, LogOut, LogIn,
  Users, Webhook,
} from 'lucide-react';
import { useTheme } from '../lib/ThemeContext';
import { useAuth } from '../lib/AuthContext';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard', end: true },
  { to: '/market-intelligence', icon: LineChart, label: 'Market Intel' },
  { to: '/analytics', icon: BarChart3, label: 'Analytics' },
  { to: '/skills-gap', icon: Radar, label: 'Skills Gap' },
  { to: '/autopilot', icon: Zap, label: 'Auto-Pilot' },
  { to: '/pipeline-debugger', icon: GitBranch, label: 'Pipeline' },
  { to: '/scam-detector', icon: ShieldAlert, label: 'Scam Detector' },
  { to: '/agent-control', icon: Bot, label: 'Agent Control' },
  { to: '/jobs', icon: Briefcase, label: 'Jobs' },
  { to: '/applications', icon: FileCheck, label: 'Applications' },
  { to: '/run-logs', icon: History, label: 'Run Logs' },
  { to: '/cache-explorer', icon: Database, label: 'Match Cache' },
  { to: '/log-viewer', icon: FileText, label: 'Log Viewer' },
  { to: '/backups', icon: HardDrive, label: 'Backups' },
  { to: '/config', icon: Settings, label: 'Configuration' },
  { to: '/resume', icon: User, label: 'Resume' },
  { to: '/accounts', icon: Users, label: 'Accounts' },
  { to: '/webhooks', icon: Webhook, label: 'Webhooks' },
];

export default function Layout() {
  const { theme, toggle } = useTheme();
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="flex h-screen bg-bg">
      <aside className="w-64 shrink-0 flex flex-col overflow-y-auto border-r bg-surface border-border">
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
        <nav className="flex-1 p-3 space-y-1" role="navigation" aria-label="Main navigation">
          {navItems.map(({ to, icon: Icon, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }: { isActive: boolean }) =>
                `nav-link ${isActive ? 'nav-link-active' : ''}`
              }
            >
              <Icon className="w-5 h-5 shrink-0" aria-hidden="true" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
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
