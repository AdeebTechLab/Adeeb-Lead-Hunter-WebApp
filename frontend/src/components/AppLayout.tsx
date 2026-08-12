import {
  Bell,
  Bot,
  ChartNoAxesCombined,
  ChevronLeft,
  FolderKanban,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  RefreshCw,
  Search,
  Settings,
  Sun,
  Target,
  Users,
  Workflow,
  X,
} from 'lucide-react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { useAuth } from '../contexts/AuthContext'
import { useRefresh } from '../contexts/RefreshContext'
import { useTheme } from '../contexts/ThemeContext'

type NavItem = { label: string; path: string; icon: typeof LayoutDashboard; admin?: boolean; badge?: boolean }

const navItems: NavItem[] = [
  { label: 'Dashboard', path: '/', icon: LayoutDashboard },
  { label: 'Lead Hunter', path: '/hunter', icon: Search },
  { label: 'Qualified Leads', path: '/leads', icon: Target },
  { label: 'Saved Lists', path: '/lists', icon: FolderKanban },
  { label: 'CRM Pipeline', path: '/crm', icon: Workflow },
  { label: 'Analytics', path: '/analytics', icon: ChartNoAxesCombined },
  { label: 'Notifications', path: '/notifications', icon: Bell, badge: true },
  { label: 'Team', path: '/team', icon: Users, admin: true },
  { label: 'Settings', path: '/settings', icon: Settings },
]

function roleLabel(role?: string) {
  if (!role) return ''
  return role === 'admin' ? 'Admin' : 'User'
}

export default function AppLayout() {
  const { user, logout } = useAuth()
  const { theme, toggle } = useTheme()
  const { refresh } = useRefresh()
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(false)
  const [unread, setUnread] = useState(0)

  useEffect(() => {
    let active = true
    const loadUnread = () => api<{ unread: number }>('/notifications')
      .then((data) => { if (active) setUnread(data.unread) })
      .catch(() => undefined)
    loadUnread()
    const timer = window.setInterval(loadUnread, 20000)
    return () => { active = false; window.clearInterval(timer) }
  }, [location.pathname])

  useEffect(() => setMobileOpen(false), [location.pathname])

  const pageTitle = useMemo(() => {
    const path = location.pathname
    if (path.startsWith('/leads/')) return 'Lead Details'
    return navItems.find((item) => item.path === path)?.label || 'Dashboard'
  }, [location.pathname])

  const visibleItems = navItems.filter((item) => !item.admin || user?.role === 'admin')

  return (
    <div className={`app-shell ${collapsed ? 'sidebar-collapsed' : ''}`}>
      {mobileOpen && <button className="sidebar-overlay" onClick={() => setMobileOpen(false)} aria-label="Close menu" />}
      <aside className={`sidebar ${mobileOpen ? 'sidebar-mobile-open' : ''}`}>
        <div className="brand-row">
          <div className="brand-mark"><Bot size={22} /></div>
          <div className="brand-copy">
            <strong>Adeeb Lead Hunter</strong>
            <span>AI Sales Intelligence</span>
          </div>
          <button className="icon-button sidebar-close" onClick={() => setMobileOpen(false)} aria-label="Close menu"><X size={18} /></button>
        </div>

        <nav className="sidebar-nav">
          {visibleItems.map(({ label, path, icon: Icon, badge }) => (
            <NavLink key={path} to={path} end={path === '/'} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <Icon size={19} />
              <span>{label}</span>
              {badge && unread > 0 && <em className="nav-badge">{Math.min(unread, 9)}</em>}
            </NavLink>
          ))}
          <button type="button" className="nav-link logout-link" onClick={logout}>
            <LogOut size={19} />
            <span>Logout</span>
          </button>
        </nav>

        <div className="sidebar-profile">
          <div className="avatar">
            {user?.profile_image_url ? <img src={user.profile_image_url} alt="" /> : user?.name?.slice(0, 1).toUpperCase()}
          </div>
          <div className="profile-copy">
            <strong>{user?.name}</strong>
            <span>{roleLabel(user?.role)}</span>
          </div>
          <button className="icon-button on-dark profile-collapse" onClick={() => setCollapsed((value) => !value)} aria-label="Toggle sidebar" title="Toggle sidebar">
            <ChevronLeft size={17} />
          </button>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div className="topbar-title">
            <button className="icon-button mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Open menu"><Menu size={20} /></button>
            <div>
              <h1>{pageTitle}</h1>
              <span>Pakistan sales workspace</span>
            </div>
          </div>
          <div className="topbar-actions">
            <button className="icon-button" onClick={refresh} title="Refresh"><RefreshCw size={18} /></button>
            <button className="icon-button" onClick={toggle} title="Toggle theme">{theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}</button>
            <NavLink className="icon-button notification-button" to="/notifications" title="Notifications">
              <Bell size={18} />
              {unread > 0 && <span>{Math.min(unread, 9)}</span>}
            </NavLink>
          </div>
        </header>
        <section className="page-content"><Outlet /></section>
      </main>
    </div>
  )
}
