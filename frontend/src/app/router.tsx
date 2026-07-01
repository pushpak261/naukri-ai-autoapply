import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
import { DashboardPage } from '@/features/dashboard/DashboardPage'
import { HistoryPage } from '@/features/history/HistoryPage'
import { JobsPage } from '@/features/jobs/JobsPage'
import { SettingsPage } from '@/features/settings/SettingsPage'
import { ToastContainer } from '@/components/ToastContainer'

const nav = [
  { to: '/', label: 'Dashboard' },
  { to: '/jobs', label: 'Live Jobs' },
  { to: '/history', label: 'History' },
  { to: '/settings', label: 'Settings' },
]

export function AppRouter() {
  return (
    <BrowserRouter>
      <div className="min-h-screen">
        <header className="border-b border-border bg-card">
          <div className="mx-auto flex max-w-7xl items-center gap-8 px-6 py-4">
            <span className="text-lg font-bold text-primary">Naukri AI Agent</span>
            <nav className="flex gap-1">
              {nav.map(({ to, label }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={to === '/'}
                  className={({ isActive }) =>
                    `rounded-md px-3 py-2 text-sm transition-colors ${
                      isActive
                        ? 'bg-primary text-primary-foreground'
                        : 'text-muted-foreground hover:text-foreground'
                    }`
                  }
                >
                  {label}
                </NavLink>
              ))}
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-6 py-8">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/jobs" element={<JobsPage />} />
            <Route path="/history" element={<HistoryPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>
        <ToastContainer />
      </div>
    </BrowserRouter>
  )
}
