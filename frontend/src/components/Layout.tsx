import { useState, useEffect } from 'react';
import { NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom';
import {
  LayoutDashboard, Briefcase, FileCheck, History, Settings, User,
  BarChart3, Radar, ShieldAlert, Bot, Database, FileText, HardDrive, Activity,
  Sun, Moon, Zap, LineChart, Download, LogOut, LogIn,
  Users, Webhook, Globe, Trash2, Filter, Menu, X,
} from 'lucide-react';
import { useTheme } from '../lib/ThemeContext';
import { useAuth } from '../lib/AuthContext';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard', end: true },
  { to: '/job-inspector', icon: Filter, label: 'Job Inspector' },
  { to: '/market-intelligence', icon: LineChart, label: 'Market Intel' },
  { to: '/analytics', icon: BarChart3, label: 'Analytics' },
  { to: '/skills-gap', icon: Radar, label: 'Skills Gap' },
  { to: '/autopilot', icon: Zap, label: 'Auto-Pilot' },
  { to: '/scam-detector', icon: ShieldAlert, label: 'Scam Detector' },
  { to: '/agent-control', icon: Bot, label: 'Agent Control' },
  { to: '/linkedin', icon: Globe, label: 'LinkedIn' },
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
  { to: '/clear-data', icon: Trash2, label: 'Clear Data' },
];

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="flex-1 p-3 space-y-1 overflow-y-auto" role="navigation" aria-label="Main navigation">
      {navItems.map(({ to, icon: Icon, label, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          onClick={onNavigate}
          className={({ isActive }: { isActive: boolean }) =>
            `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
              isActive ? 'bg-[#38bdf8]/10 text-[#38bdf8]' : 'hover:bg-[#334155] hover:text-white'
            }`
          }
          style={({ isActive }: { isActive: boolean }) => ({
            color: isActive ? 'var(--color-primary)' : 'var(--color-text-secondary)',
            backgroundColor: isActive ? 'rgba(56, 189, 248, 0.1)' : undefined,
          } satisfies React.CSSProperties)}
        >
          <Icon className="w-5 h-5 shrink-0" aria-hidden="true" />
          <span className="truncate">{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}

function SidebarFooter() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <div className="p-4 border-t space-y-2 shrink-0" style={{ borderColor: 'var(--color-border)' }}>
      {user && (
        <div className="flex items-center gap-2 text-xs px-1" style={{ color: 'var(--color-text-secondary)' }}>
          <User className="w-3.5 h-3.5 shrink-0" />
          <span className="truncate">{user.email}</span>
        </div>
      )}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--color-text-muted)' }}>
          <Download className="w-3 h-3" />
          <span>v3.0.0</span>
        </div>
        {user ? (
          <button
            onClick={async () => { await logout(); navigate('/login', { replace: true }); }}
            className="flex items-center gap-1.5 text-xs py-1 px-2 rounded transition-colors hover:text-red-400"
            style={{ color: 'var(--color-text-muted)' }}
            title="Sign out"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span>Sign out</span>
          </button>
        ) : (
          <button
            onClick={() => navigate('/login')}
            className="flex items-center gap-1.5 text-xs py-1 px-2 rounded transition-colors hover:text-[#38bdf8]"
            style={{ color: 'var(--color-text-muted)' }}
            title="Sign in"
          >
            <LogIn className="w-3.5 h-3.5" />
            <span>Sign in</span>
          </button>
        )}
      </div>
    </div>
  );
}

export default function Layout() {
  const { theme, toggle } = useTheme();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();

  // Close mobile sidebar on route change
  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  return (
    <div className="flex h-screen overflow-hidden" style={{ backgroundColor: 'var(--color-bg)' }}>
      {/* Desktop sidebar */}
      <aside
        className="hidden lg:flex w-64 shrink-0 flex-col border-r"
        style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
      >
        <div className="p-5 border-b shrink-0" style={{ borderColor: 'var(--color-border)' }}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Activity className="w-6 h-6" style={{ color: 'var(--color-primary)' }} />
              <h1 className="text-lg font-semibold" style={{ color: 'var(--color-text)' }}>Naukri Agent</h1>
            </div>
            <button
              onClick={toggle}
              className="p-1.5 rounded-lg transition-colors hover:bg-[#334155]/50"
              style={{ color: 'var(--color-text-secondary)' }}
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
              title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
            >
              {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
          </div>
          <p className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>AI Job Application Dashboard</p>
        </div>
        <NavLinks />
        <SidebarFooter />
      </aside>

      {/* Mobile / tablet drawer */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-50 lg:hidden flex">
          <div
            className="fixed inset-0 bg-black/70 backdrop-blur-sm transition-opacity"
            onClick={() => setSidebarOpen(false)}
            aria-hidden="true"
          />
          <aside
            className="relative w-72 max-w-[85vw] h-full flex flex-col border-r shadow-2xl z-10 animate-in slide-in-from-left duration-200"
            style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
          >
            <div className="flex items-center justify-between p-4 border-b shrink-0" style={{ borderColor: 'var(--color-border)' }}>
              <div className="flex items-center gap-2">
                <Activity className="w-6 h-6" style={{ color: 'var(--color-primary)' }} />
                <h1 className="text-base font-semibold" style={{ color: 'var(--color-text)' }}>Naukri Agent</h1>
              </div>
              <button
                onClick={() => setSidebarOpen(false)}
                className="p-2 rounded-lg transition-colors hover:bg-[#334155]/50"
                style={{ color: 'var(--color-text-secondary)' }}
                aria-label="Close navigation"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <NavLinks onNavigate={() => setSidebarOpen(false)} />
            <SidebarFooter />
          </aside>
        </div>
      )}

      {/* Main content area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Mobile / tablet top bar */}
        <header
          className="sticky top-0 z-20 flex items-center justify-between px-4 py-3 border-b lg:hidden shrink-0"
          style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
        >
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-2 -ml-2 rounded-lg transition-colors hover:bg-[#334155]/50"
            style={{ color: 'var(--color-text)' }}
            aria-label="Open navigation"
          >
            <Menu className="w-6 h-6" />
          </button>
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5" style={{ color: 'var(--color-primary)' }} />
            <span className="font-semibold text-sm" style={{ color: 'var(--color-text)' }}>Naukri Agent</span>
          </div>
          <button
            onClick={toggle}
            className="p-2 -mr-2 rounded-lg transition-colors hover:bg-[#334155]/50"
            style={{ color: 'var(--color-text-secondary)' }}
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
          >
            {theme === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
          </button>
        </header>

        <main className="flex-1 overflow-auto" style={{ backgroundColor: 'var(--color-bg)' }}>
          <div className="max-w-7xl mx-auto p-3.5 sm:p-6">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
