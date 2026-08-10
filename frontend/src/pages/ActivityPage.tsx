import { Activity, Clock3, RefreshCw, UserRound } from 'lucide-react'
import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { api } from '../api'
import EmptyState from '../components/EmptyState'
import Loader from '../components/Loader'
import { useRefresh } from '../contexts/RefreshContext'

type ActivityItem = { id: string; user_name: string; action: string; entity: string; detail: string; created_at: string }

export default function ActivityPage() {
  const [items, setItems] = useState<ActivityItem[] | null>(null)
  const { refreshKey, refresh } = useRefresh()
  useEffect(() => { api<{ items: ActivityItem[] }>('/activity').then((data) => setItems(data.items)).catch((error) => toast.error(error.message)) }, [refreshKey])
  if (!items) return <Loader />
  return (
    <section className="card">
      <div className="card-header"><div><span className="eyebrow">Workspace history</span><h2>Activity logs</h2></div><button className="button secondary" onClick={refresh}><RefreshCw size={16} />Refresh</button></div>
      {!items.length ? <EmptyState /> : <div className="activity-list">{items.map((item) => <article key={item.id}><div className="activity-icon"><Activity size={17} /></div><div><strong>{item.action} · {item.entity}</strong><p>{item.detail || 'Workspace activity'}</p><span><UserRound size={13} />{item.user_name}<Clock3 size={13} />{new Date(item.created_at).toLocaleString()}</span></div></article>)}</div>}
    </section>
  )
}
