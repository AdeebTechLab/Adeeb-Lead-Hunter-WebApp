import { Ban, KeyRound, Pencil, Play, ShieldCheck, Trash2, X } from 'lucide-react'
import { FormEvent, useCallback, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { api } from '../api'
import EmptyState from '../components/EmptyState'
import Loader from '../components/Loader'
import ProfileImagePicker from '../components/ProfileImagePicker'
import StatusBadge from '../components/StatusBadge'
import { useAuth } from '../contexts/AuthContext'
import { useRefresh } from '../contexts/RefreshContext'
import type { User } from '../types'

type EditForm = { name: string; email: string; cnic: string; city: string }

function emptyForm(): EditForm {
  return { name: '', email: '', cnic: '', city: '' }
}

export default function TeamPage() {
  const { user, refreshUser } = useAuth()
  const { refreshKey, refresh } = useRefresh()
  const [items, setItems] = useState<User[] | null>(null)
  const [selected, setSelected] = useState<User | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [form, setForm] = useState<EditForm>(emptyForm())
  const [profileImage, setProfileImage] = useState<File | null>(null)
  const [pickerReset, setPickerReset] = useState(0)
  const [temporaryPassword, setTemporaryPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const onProfileChange = useCallback((file: File | null) => setProfileImage(file), [])

  function load() {
    if (user?.role !== 'admin') return
    api<{ items: User[] }>('/users')
      .then((data) => setItems(data.items))
      .catch((error) => toast.error(error.message))
  }

  useEffect(load, [refreshKey, user?.role])

  if (!user) return <Loader />
  if (user.role !== 'admin') return <section className="card access-card"><ShieldCheck size={34} /><h2>Admin access required</h2></section>
  if (!items) return <Loader />

  async function openMember(memberId: string) {
    setLoadingDetail(true)
    try {
      const member = await api<User>(`/users/${memberId}`)
      setSelected(member)
      setForm({ name: member.name, email: member.email, cnic: member.cnic, city: member.city })
      setTemporaryPassword('')
      setProfileImage(null)
      setPickerReset((value) => value + 1)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not load user')
    } finally {
      setLoadingDetail(false)
    }
  }

  function closeModal() {
    setSelected(null)
    setTemporaryPassword('')
    setProfileImage(null)
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!selected) return
    setSaving(true)
    try {
      const body = new FormData()
      body.append('name', form.name.trim())
      body.append('email', form.email.trim())
      body.append('cnic', form.cnic.trim())
      body.append('city', form.city.trim())
      if (profileImage) body.append('profile_image', profileImage)
      const updated = await api<User>(`/users/${selected.id}`, { method: 'PATCH', body })
      setSelected(updated)
      setForm({ name: updated.name, email: updated.email, cnic: updated.cnic, city: updated.city })
      setProfileImage(null)
      setPickerReset((value) => value + 1)
      if (user?.id === updated.id) await refreshUser()
      toast.success('User details updated')
      load()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Update failed')
    } finally {
      setSaving(false)
    }
  }

  async function resetPassword() {
    if (!selected || selected.role === 'admin') return
    if (temporaryPassword.length < 8) return toast.error('Temporary password must be at least 8 characters')
    try {
      await api(`/users/${selected.id}/reset-password`, {
        method: 'POST',
        body: JSON.stringify({ temporary_password: temporaryPassword }),
      })
      setTemporaryPassword('')
      toast.success('Temporary password set')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Password reset failed')
    }
  }

  async function toggleSuspension(member: User) {
    if (member.role === 'admin') return
    const action = member.active ? 'suspend' : 'activate'
    try {
      await api(`/users/${member.id}/${action}`, { method: 'POST' })
      toast.success(member.active ? 'User suspended' : 'User activated')
      load()
      if (selected?.id === member.id) await openMember(member.id)
      refresh()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Status update failed')
    }
  }

  async function deleteMember(member: User) {
    if (member.role === 'admin') return
    if (!window.confirm(`Delete ${member.name}? Their existing leads will remain in the CRM.`)) return
    try {
      await api(`/users/${member.id}`, { method: 'DELETE' })
      toast.success('User deleted')
      if (selected?.id === member.id) closeModal()
      load()
      refresh()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Delete failed')
    }
  }

  return (
    <>
      <section className="card">
        <div className="card-header"><div><span className="eyebrow">Workspace access</span><h2>Team</h2></div></div>
        {!items.length ? <EmptyState /> : (
          <div className="table-wrap">
            <table className="team-table">
              <thead><tr><th>User</th><th>City</th><th>Role</th><th>Leads</th><th>Status</th><th>Joined</th><th>Actions</th></tr></thead>
              <tbody>{items.map((member) => (
                <tr key={member.id} onClick={() => openMember(member.id)}>
                  <td><div className="user-cell"><div className="avatar light-avatar">{member.profile_image_url ? <img src={member.profile_image_url} alt="" /> : member.name.slice(0, 1).toUpperCase()}</div><div><strong>{member.name}</strong><span>{member.email}</span></div></div></td>
                  <td>{member.city || '—'}</td>
                  <td><StatusBadge value={member.role === 'admin' ? 'Admin' : 'User'} /></td>
                  <td>{member.lead_count ?? 0}</td>
                  <td><StatusBadge value={member.active ? 'Active' : 'Suspended'} /></td>
                  <td>{new Date(member.created_at).toLocaleDateString()}</td>
                  <td>
                    <div className="team-actions" onClick={(event) => event.stopPropagation()}>
                      <button className="icon-button small" onClick={() => openMember(member.id)} title="View and edit"><Pencil size={15} /></button>
                      {member.role !== 'admin' && <button className="icon-button small" onClick={() => toggleSuspension(member)} title={member.active ? 'Suspend user' : 'Activate user'}>{member.active ? <Ban size={15} /> : <Play size={15} />}</button>}
                      {member.role !== 'admin' && <button className="icon-button small danger-icon" onClick={() => deleteMember(member)} title="Delete user"><Trash2 size={15} /></button>}
                    </div>
                  </td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </section>

      {(selected || loadingDetail) && (
        <div className="team-modal-layer">
          <button className="team-modal-overlay" onClick={closeModal} aria-label="Close user details" />
          <section className="team-modal card" role="dialog" aria-modal="true" aria-label="User details">
            {loadingDetail && !selected ? <Loader /> : selected && (
              <>
                <div className="card-header team-modal-header">
                  <div><span className="eyebrow">Team member</span><h2>{selected.name}</h2></div>
                  <button className="icon-button" onClick={closeModal}><X size={18} /></button>
                </div>

                <div className="member-summary">
                  <div className="avatar member-avatar">{selected.profile_image_url ? <img src={selected.profile_image_url} alt="" /> : selected.name.slice(0, 1).toUpperCase()}</div>
                  <div><strong>{selected.email}</strong><span>{selected.role === 'admin' ? 'Administrator' : 'User'} · {selected.active ? 'Active' : 'Suspended'}</span></div>
                  <div className="member-stats"><span>Leads <strong>{selected.lead_count ?? 0}</strong></span><span>Contacted <strong>{selected.contacted_count ?? 0}</strong></span><span>Completed <strong>{selected.completed_count ?? 0}</strong></span></div>
                </div>

                <form className="team-edit-form" onSubmit={save}>
                  <div className="form-grid team-edit-fields">
                    <label>Full name<input required minLength={2} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
                    <label>Email<input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
                    <label>CNIC<input required value={form.cnic} onChange={(e) => setForm({ ...form, cnic: e.target.value })} /></label>
                    <label>City<input required minLength={2} value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} /></label>
                    <label>Role<input value={selected.role === 'admin' ? 'Admin' : 'User'} disabled /></label>
                    <label>Joined<input value={new Date(selected.created_at).toLocaleString()} disabled /></label>
                  </div>
                  <ProfileImagePicker onChange={onProfileChange} resetKey={pickerReset} />
                  <div className="form-actions"><button className="button primary" disabled={saving}>{saving ? 'Saving' : 'Save changes'}</button></div>
                </form>

                {selected.role !== 'admin' && (
                  <div className="admin-user-tools">
                    <div>
                      <span className="eyebrow">Password recovery</span>
                      <h3>Set temporary password</h3>
                      <p>The user should change this password after signing in.</p>
                    </div>
                    <div className="temporary-password-row">
                      <input type="text" minLength={8} placeholder="Temporary password" value={temporaryPassword} onChange={(e) => setTemporaryPassword(e.target.value)} />
                      <button className="button secondary" type="button" onClick={resetPassword}><KeyRound size={15} />Reset password</button>
                    </div>
                    <div className="member-admin-actions">
                      <button className="button secondary" type="button" onClick={() => toggleSuspension(selected)}>{selected.active ? <Ban size={15} /> : <Play size={15} />}{selected.active ? 'Suspend user' : 'Activate user'}</button>
                      <button className="button secondary danger-button" type="button" onClick={() => deleteMember(selected)}><Trash2 size={15} />Delete user</button>
                    </div>
                  </div>
                )}
                {selected.role === 'admin' && <div className="protected-role-note"><ShieldCheck size={17} /><span>Administrator role, suspension and deletion are protected.</span></div>}
              </>
            )}
          </section>
        </div>
      )}
    </>
  )
}
