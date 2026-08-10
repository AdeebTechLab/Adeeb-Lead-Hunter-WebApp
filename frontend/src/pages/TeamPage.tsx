import { Plus, ShieldCheck } from 'lucide-react'
import { FormEvent, useCallback, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { api } from '../api'
import EmptyState from '../components/EmptyState'
import Loader from '../components/Loader'
import ProfileImagePicker from '../components/ProfileImagePicker'
import StatusBadge from '../components/StatusBadge'
import { useAuth } from '../contexts/AuthContext'
import { useRefresh } from '../contexts/RefreshContext'
import type { User, UserRole } from '../types'

function roleLabel(role: UserRole) {
  return role === 'salesperson' ? 'User' : role.charAt(0).toUpperCase() + role.slice(1)
}

export default function TeamPage() {
  const { user } = useAuth()
  const { refreshKey } = useRefresh()
  const [items, setItems] = useState<User[] | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [profileImage, setProfileImage] = useState<File | null>(null)
  const [pickerReset, setPickerReset] = useState(0)
  const onProfileChange = useCallback((file: File | null) => setProfileImage(file), [])
  const [form, setForm] = useState({ name: '', email: '', password: '', cnic: '', city: '', role: 'salesperson' as UserRole })

  function load() { api<{ items: User[] }>('/users').then((data) => setItems(data.items)).catch((error) => toast.error(error.message)) }
  useEffect(load, [refreshKey])

  if (!user) return <Loader />
  if (user.role === 'salesperson') return <section className="card access-card"><ShieldCheck size={34} /><h2>Manager access required</h2></section>
  if (!items) return <Loader />

  async function create(event: FormEvent) {
    event.preventDefault()
    try {
      const body = new FormData()
      Object.entries(form).forEach(([key, value]) => body.append(key, String(value)))
      if (profileImage) body.append('profile_image', profileImage)
      await api('/users', { method: 'POST', body })
      toast.success('Team member added')
      setShowForm(false)
      setForm({ name: '', email: '', password: '', cnic: '', city: '', role: 'salesperson' })
      setProfileImage(null)
      setPickerReset((value) => value + 1)
      load()
    } catch (error) { toast.error(error instanceof Error ? error.message : 'User creation failed') }
  }

  async function updateRole(id: string, role: UserRole) {
    try { await api(`/users/${id}`, { method: 'PATCH', body: JSON.stringify({ role }) }); load(); toast.success('Role updated') }
    catch (error) { toast.error(error instanceof Error ? error.message : 'Update failed') }
  }

  return (
    <div className="stack-lg">
      <section className="card">
        <div className="card-header"><div><span className="eyebrow">Access control</span><h2>Team & roles</h2></div>{user.role === 'admin' && <button className="button primary" onClick={() => setShowForm((value) => !value)}><Plus size={16} />Add user</button>}</div>
        {showForm && (
          <form className="team-user-form" onSubmit={create}>
            <div className="form-grid team-fields">
              <label>Name<input placeholder="Full name" required minLength={2} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
              <label>Email<input type="email" placeholder="name@company.com" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
              <label>CNIC<input placeholder="35202-1234567-1" required value={form.cnic} onChange={(e) => setForm({ ...form, cnic: e.target.value })} /></label>
              <label>City<input placeholder="Lahore" required minLength={2} value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} /></label>
              <label>Temporary password<input type="password" minLength={8} placeholder="Minimum 8 characters" required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
              <label>Role<select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as UserRole })}><option value="salesperson">User</option><option value="manager">Manager</option><option value="admin">Admin</option></select></label>
            </div>
            <ProfileImagePicker onChange={onProfileChange} resetKey={pickerReset} />
            <div className="form-actions"><button type="button" className="button secondary" onClick={() => setShowForm(false)}>Cancel</button><button className="button primary">Create account</button></div>
          </form>
        )}
        {!items.length ? <EmptyState /> : <div className="table-wrap"><table><thead><tr><th>User</th><th>City</th><th>Role</th><th>Status</th><th>Joined</th></tr></thead><tbody>{items.map((member) => <tr key={member.id}><td><div className="user-cell"><div className="avatar light-avatar">{member.profile_image_url ? <img src={member.profile_image_url} alt="" /> : member.name.slice(0, 1).toUpperCase()}</div><div><strong>{member.name}</strong><span>{member.email}</span></div></div></td><td>{member.city || '—'}</td><td>{user.role === 'admin' ? <select value={member.role} onChange={(e) => updateRole(member.id, e.target.value as UserRole)}><option value="salesperson">User</option><option value="manager">Manager</option><option value="admin">Admin</option></select> : <StatusBadge value={roleLabel(member.role)} />}</td><td><StatusBadge value={member.active ? 'Active' : 'Disabled'} /></td><td>{new Date(member.created_at).toLocaleDateString()}</td></tr>)}</tbody></table></div>}
      </section>
    </div>
  )
}
