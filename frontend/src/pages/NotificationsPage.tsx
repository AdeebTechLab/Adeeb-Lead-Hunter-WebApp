import { Bell, CheckCheck, Flame, PhoneCall } from 'lucide-react'
import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import EmptyState from '../components/EmptyState'
import Loader from '../components/Loader'
import { useRefresh } from '../contexts/RefreshContext'
import type { NotificationItem } from '../types'

export default function NotificationsPage() {
  const [items, setItems] = useState<NotificationItem[] | null>(null)
  const { refreshKey, refresh } = useRefresh()
  const navigate = useNavigate()
  function load() { api<{ items: NotificationItem[] }>('/notifications').then((data) => setItems(data.items)).catch((error) => toast.error(error.message)) }
  useEffect(load, [refreshKey])
  if (!items) return <Loader />

  async function open(item: NotificationItem) {
    if (!item.read) await api(`/notifications/${item.id}`, { method: 'PATCH', body: JSON.stringify({ read: true }) })
    refresh()
    navigate(item.link || '/notifications')
  }
  async function readAll() {
    await api('/notifications/read-all', { method: 'POST' })
    refresh()
    toast.success('Notifications cleared')
  }

  return (
    <section className="card">
      <div className="card-header"><div><span className="eyebrow">Inbox</span><h2>Notifications</h2></div><button className="button secondary" onClick={readAll}><CheckCheck size={16} />Mark all read</button></div>
      {!items.length ? <EmptyState /> : <div className="notification-list">{items.map((item) => <button key={item.id} className={item.read ? 'read' : ''} onClick={() => open(item)}><div className="notification-icon">{item.kind === 'lead' ? <Flame size={18} /> : item.kind === 'followup' ? <PhoneCall size={18} /> : <Bell size={18} />}</div><div><strong>{item.title}</strong><p>{item.message}</p><span>{new Date(item.created_at).toLocaleString()}</span></div>{!item.read && <i />}</button>)}</div>}
    </section>
  )
}
