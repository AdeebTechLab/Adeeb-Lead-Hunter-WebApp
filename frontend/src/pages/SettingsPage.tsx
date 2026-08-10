import { Moon, Palette, Sun, UserRound } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { useTheme } from '../contexts/ThemeContext'

function maskCnic(value?: string) {
  if (!value) return ''
  return `${value.slice(0, 5)}-•••••••-${value.slice(-1)}`
}

export default function SettingsPage() {
  const { user } = useAuth()
  const { theme, toggle } = useTheme()
  return (
    <div className="settings-grid settings-grid-compact">
      <section className="card settings-card">
        <div className="settings-icon">{user?.profile_image_url ? <img src={user.profile_image_url} alt="" /> : <UserRound size={21} />}</div>
        <div><span className="eyebrow">Account</span><h2>{user?.name}</h2><p>{user?.email} · {user?.city}</p>{user?.cnic && <span className="setting-value">{maskCnic(user.cnic)}</span>}</div>
      </section>
      <section className="card settings-card">
        <div className="settings-icon"><Palette size={21} /></div>
        <div><span className="eyebrow">Appearance</span><h2>{theme === 'dark' ? 'Dark mode' : 'Light mode'}</h2><button className="button secondary" onClick={toggle}>{theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}Switch theme</button></div>
      </section>
    </div>
  )
}
