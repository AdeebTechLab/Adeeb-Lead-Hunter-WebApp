import { KeyRound, Moon, Palette, Sun, UserRound } from 'lucide-react'
import { FormEvent, useState } from 'react'
import toast from 'react-hot-toast'
import { api } from '../api'
import { useAuth } from '../contexts/AuthContext'
import { useTheme } from '../contexts/ThemeContext'

export default function SettingsPage() {
  const { user, refreshUser } = useAuth()
  const { theme, toggle } = useTheme()
  const [passwords, setPasswords] = useState({ current: '', next: '', confirm: '' })
  const [saving, setSaving] = useState(false)

  async function changePassword(event: FormEvent) {
    event.preventDefault()
    if (passwords.next !== passwords.confirm) return toast.error('New passwords do not match')
    setSaving(true)
    try {
      await api('/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({ current_password: passwords.current, new_password: passwords.next }),
      })
      setPasswords({ current: '', next: '', confirm: '' })
      await refreshUser()
      toast.success('Password changed')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Password change failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="settings-grid settings-grid-compact">
      <section className="card settings-card account-details-card">
        <div className="settings-icon">{user?.profile_image_url ? <img src={user.profile_image_url} alt="" /> : <UserRound size={21} />}</div>
        <div>
          <span className="eyebrow">Account</span>
          <h2>{user?.name}</h2>
          <p>{user?.email} · {user?.city}</p>
          {user?.cnic && <span className="setting-value">CNIC: {user.cnic}</span>}
          <span className="setting-value">Role: {user?.role === 'admin' ? 'Admin' : 'User'}</span>
          <small className="settings-note">Profile details and profile photo can only be changed by an administrator.</small>
        </div>
      </section>

      <section className="card settings-card">
        <div className="settings-icon"><Palette size={21} /></div>
        <div><span className="eyebrow">Appearance</span><h2>{theme === 'dark' ? 'Dark mode' : 'Light mode'}</h2><button className="button secondary" onClick={toggle}>{theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}Switch theme</button></div>
      </section>

      <section className="card password-card span-2">
        <div className="card-header"><div><span className="eyebrow">Security</span><h2>Change password</h2></div><KeyRound size={20} /></div>
        {user?.must_change_password && <div className="password-required-note">Your password was reset by an administrator. Set a new private password now.</div>}
        <form className="password-form" onSubmit={changePassword}>
          <label>Current password<input type="password" required value={passwords.current} onChange={(e) => setPasswords({ ...passwords, current: e.target.value })} /></label>
          <label>New password<input type="password" required minLength={8} value={passwords.next} onChange={(e) => setPasswords({ ...passwords, next: e.target.value })} /></label>
          <label>Confirm new password<input type="password" required minLength={8} value={passwords.confirm} onChange={(e) => setPasswords({ ...passwords, confirm: e.target.value })} /></label>
          <button className="button primary" disabled={saving}>{saving ? 'Changing' : 'Change password'}</button>
        </form>
      </section>
    </div>
  )
}
