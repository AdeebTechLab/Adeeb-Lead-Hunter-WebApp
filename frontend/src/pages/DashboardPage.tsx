import { ArrowUpRight, Flame, ListChecks, Percent, Target, UsersRound } from 'lucide-react'
import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import LeadDrawer from '../components/LeadDrawer'
import Loader from '../components/Loader'
import StatusBadge from '../components/StatusBadge'
import { useRefresh } from '../contexts/RefreshContext'
import type { Lead } from '../types'

type DashboardData = {
  stats: { total_leads: number; hot_leads: number; follow_ups: number; conversion_rate: number; new_this_week: number }
  pipeline: { name: string; value: number }[]
  services: { name: string; value: number }[]
  recent_leads: Lead[]
  top_leads: Lead[]
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const { refreshKey } = useRefresh()

  useEffect(() => {
    api<DashboardData>('/dashboard').then(setData).catch((error) => toast.error(error.message))
  }, [refreshKey])

  if (!data) return <Loader />

  const cards = [
    { label: 'Total leads', value: data.stats.total_leads, icon: UsersRound, note: `${data.stats.new_this_week} this week` },
    { label: 'Hot leads', value: data.stats.hot_leads, icon: Flame, note: 'Priority queue' },
    { label: 'Follow-ups', value: data.stats.follow_ups, icon: ListChecks, note: 'CRM pipeline' },
    { label: 'Conversion', value: `${data.stats.conversion_rate}%`, icon: Percent, note: 'Won vs contacted' },
  ]

  return (
    <>
      <div className="metric-grid">
        {cards.map(({ label, value, icon: Icon, note }) => (
          <article className="metric-card" key={label}>
            <div className="metric-icon"><Icon size={20} /></div>
            <span>{label}</span><strong>{value}</strong><small>{note}</small>
          </article>
        ))}
      </div>
      <div className="dashboard-grid">
        <section className="card chart-card span-2">
          <div className="card-header"><div><span className="eyebrow">Pipeline</span><h2>Lead progress</h2></div></div>
          <div className="chart-box">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.pipeline} margin={{ left: -20, right: 8 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" tickLine={false} axisLine={false} fontSize={11} />
                <YAxis tickLine={false} axisLine={false} fontSize={11} allowDecimals={false} />
                <Tooltip cursor={{ fill: 'rgba(255,142,1,.08)' }} />
                <Bar dataKey="value" fill="var(--accent)" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
        <section className="card priority-card">
          <div className="card-header"><div><span className="eyebrow">Priority</span><h2>Top prospects</h2></div><Target size={20} /></div>
          <div className="priority-list">
            {data.top_leads.map((lead) => (
              <button key={lead.id} onClick={() => setSelected(lead.id || null)}>
                <div className={`mini-score score-${lead.priority.toLowerCase()}`}>{lead.lead_score}</div>
                <div><strong>{lead.business_name}</strong><span>{lead.city} · {lead.recommended_service}</span></div>
                <ArrowUpRight size={16} />
              </button>
            ))}
          </div>
        </section>
        <section className="card span-3">
          <div className="card-header"><div><span className="eyebrow">Recent</span><h2>Latest leads</h2></div></div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Business</th><th>City</th><th>Score</th><th>Service</th><th>Status</th></tr></thead>
              <tbody>{data.recent_leads.map((lead) => <tr key={lead.id} onClick={() => setSelected(lead.id || null)}><td><strong>{lead.business_name}</strong><span>{lead.category}</span></td><td>{lead.city}</td><td><StatusBadge value={lead.lead_score} /></td><td>{lead.recommended_service}</td><td><StatusBadge value={lead.status} /></td></tr>)}</tbody>
            </table>
          </div>
        </section>
      </div>
      <LeadDrawer leadId={selected} onClose={() => setSelected(null)} />
    </>
  )
}
