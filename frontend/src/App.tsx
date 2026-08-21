import { Navigate, Route, Routes } from 'react-router-dom'
import AppLayout from './components/AppLayout'
import Loader from './components/Loader'
import { useAuth } from './contexts/AuthContext'
import AnalyticsPage from './pages/AnalyticsPage'
import AuthPage from './pages/AuthPage'
import CrmPage from './pages/CrmPage'
import DashboardPage from './pages/DashboardPage'
import LeadHunterPage from './pages/LeadHunterPage'
import LeadsPage from './pages/LeadsPage'
import NotificationsPage from './pages/NotificationsPage'
import SavedListsPage from './pages/SavedListsPage'
import SettingsPage from './pages/SettingsPage'
import TeamPage from './pages/TeamPage'

function ProtectedLayout() {
  const { user, loading } = useAuth()
  if (loading) return <Loader label="Loading workspace" />
  if (!user) return <Navigate to="/login" replace />
  return <AppLayout />
}

export default function App() {
  const { user } = useAuth()
  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <AuthPage mode="login" />} />
      <Route path="/signup" element={user ? <Navigate to="/" replace /> : <AuthPage mode="signup" />} />
      <Route element={<ProtectedLayout />}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/hunter" element={<LeadHunterPage />} />
        <Route path="/leads" element={<LeadsPage />} />
        <Route path="/leads/:leadId" element={<LeadsPage />} />
        <Route path="/lists" element={<SavedListsPage />} />
        <Route path="/crm" element={<CrmPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/notifications" element={<NotificationsPage />} />
        <Route path="/team" element={<TeamPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
