import { NavLink, Navigate, Outlet, useLocation } from 'react-router-dom'
import {
  FileText, LayoutDashboard, ListChecks, LogOut, ScrollText, Upload,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { Spinner } from './ui'

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/upload', label: 'Upload', icon: Upload },
  { to: '/documents', label: 'Documents', icon: FileText },
  { to: '/reports', label: 'Reports', icon: ListChecks },
  { to: '/logs', label: 'Audit log', icon: ScrollText },
]

export function ProtectedRoute() {
  const { user, loading } = useAuth()
  const location = useLocation()

  // Wait for the token check before deciding. Redirecting during the check
  // would bounce a logged-in user to /login on every page refresh.
  if (loading) return <Spinner label="Checking your session" />
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />
  return <Outlet />
}

export default function Layout() {
  const { user, logout } = useAuth()

  return (
    <div className="min-h-screen bg-paper">
      <header className="sticky top-0 z-10 border-b border-rule bg-surface">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded bg-accent">
              <FileText size={15} className="text-white" />
            </div>
            <span className="hidden text-sm font-semibold text-ink sm:block">
              Document Parser
            </span>
          </div>

          <nav className="flex flex-1 items-center gap-1 overflow-x-auto">
            {NAV.map(({ to, label, icon: Icon, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  `flex items-center gap-1.5 whitespace-nowrap rounded-md px-2.5 py-1.5 text-sm transition-colors ${
                    isActive
                      ? 'bg-accent-soft font-medium text-accent'
                      : 'text-ink-soft hover:bg-paper hover:text-ink'
                  }`
                }
              >
                <Icon size={15} />
                <span className="hidden md:inline">{label}</span>
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <p className="text-sm font-medium leading-tight text-ink">{user?.name}</p>
              <p className="text-xs capitalize text-ink-faint">{user?.role}</p>
            </div>
            <button
              onClick={logout}
              className="rounded-md p-2 text-ink-faint transition-colors hover:bg-paper hover:text-fail"
              title="Sign out"
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
