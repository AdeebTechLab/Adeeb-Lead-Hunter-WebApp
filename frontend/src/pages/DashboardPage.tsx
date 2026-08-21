import { ArrowUpRight, Ban, CalendarDays, CircleCheckBig, Flame, ListChecks, Percent, Target, UsersRound } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import LeadDrawer from '../components/LeadDrawer'
import Loader from '../components/Loader'
import StatusBadge from '../components/StatusBadge'
import { useAuth } from '../contexts/AuthContext'
import { useRefresh } from '../contexts/RefreshContext'
import type { Lead } from '../types'

type PeriodMode = 'all' | 'month' | 'custom'

type DashboardData = {
  stats: {
    total_leads: number
    hot_leads: number
    follow_ups: number
    completed_deals: number
    cancelled_deals: number
    conversion_rate: number
    new_this_week: number
    scope: 'workspace' | 'personal'
  }
  period: {
    mode: PeriodMode
    label: string
    from_date?: string | null
    to_date?: string | null
    trend_granularity: 'day' | 'month'
  }
  trend: { key: string; name: string; leads: number; completed: number; cancelled: number }[]
  pipeline: { name: string; value: number }[]
  services: { name: string; value: number }[]
  recent_leads: Lead[]
  top_leads: Lead[]
}

function isoToday() {
  const now = new Date()
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10)
}

function isoMonthStart() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`
}

function isoMonth() {
  return isoMonthStart().slice(0, 7)
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [period, setPeriod] = useState<PeriodMode>('all')
  const [fromDate, setFromDate] = useState(isoMonthStart())
  const [toDate, setToDate] = useState(isoToday())
  const [monthValue, setMonthValue] = useState(isoMonth())
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { refreshKey } = useRefresh()
  const { user } = useAuth()

  const dashboardPath = useMemo(() => {
    const params = new URLSearchParams({ period })
    if (period === 'custom') {
      params.set('from_date', fromDate)
      params.set('to_date', toDate)
    }
    if (period === 'month') params.set('month', monthValue)
    return `/dashboard?${params.toString()}`
  }, [period, fromDate, toDate, monthValue])

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    api<DashboardData>(dashboardPath)
      .then((result) => { if (active) setData(result) })
      .catch((error) => { setError(error.message); toast.error(error.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [dashboardPath, refreshKey])

  if (!data && !error) return <Loader />
  if (!data && error) return <section className="card dashboard-error"><h2>Unable to load dashboard</h2><p>{error}</p><button type="button" onClick={() => window.location.reload()}>Retry</button></section>

  const dashboardData = data!

  const cards = [
    { label: 'Total leads', value: dashboardData.stats.total_leads, icon: UsersRound, note: `${dashboardData.stats.new_this_week} this week` },
    { label: 'Hot leads', value: dashboardData.stats.hot_leads, icon: Flame, note: 'Priority queue' },
    { label: 'Follow-ups', value: dashboardData.stats.follow_ups, icon: ListChecks, note: 'CRM pipeline' },
    { label: 'Completed', value: dashboardData.stats.completed_deals, icon: CircleCheckBig, note: 'Deals won' },
    { label: 'Cancelled', value: dashboardData.stats.cancelled_deals, icon: Ban, note: 'Deals not won' },
    { label: 'Conversion', value: `${dashboardData.stats.conversion_rate}%`, icon: Percent, note: 'Completed vs contacted' },
  ]

  return (
    <>
      <section className="card dashboard-period-card">
        <div className="dashboard-period-heading">
          <div><span className="eyebrow">Performance period</span><h2>{dashboardData.period.label}</h2></div>
          <div className="period-summary"><CalendarDays size={16} /><span>{dashboardData.period.from_date && dashboardData.period.to_date ? `${dashboardData.period.from_date} → ${dashboardData.period.to_date}` : 'All available records'}</span></div>
        </div>
        <div className="dashboard-period-controls" aria-busy={loading}>
          <div className="period-tabs" role="group" aria-label="Dashboard period">
            <button type="button" className={period === 'all' ? 'active' : ''} onClick={() => setPeriod('all')}>Overall</button>
            <button type="button" className={period === 'month' ? 'active' : ''} onClick={() => setPeriod('month')}>This month</button>
            <button type="button" className={period === 'custom' ? 'active' : ''} onClick={() => setPeriod('custom')}>Date range</button>
          </div>
          {period === 'month' && (
            <div className="month-picker-control"><label>Month<input type="month" value={monthValue} max={isoMonth()} onChange={(event) => setMonthValue(event.target.value)} /></label></div>
          )}
          {period === 'custom' && (
            <div className="date-range-controls">
              <label>From<input type="date" value={fromDate} max={toDate} onChange={(event) => setFromDate(event.target.value)} /></label>
              <span>to</span>
              <label>To<input type="date" value={toDate} min={fromDate} max={isoToday()} onChange={(event) => setToDate(event.target.value)} /></label>
            </div>
          )}
          {loading && <div className="dashboard-loading-line"><span /></div>}
        </div>
      </section>

      <div className="metric-grid dashboard-metrics">
        {cards.map(({ label, value, icon: Icon, note }) => (
          <article className="metric-card" key={label}>
            <div className="metric-icon"><Icon size={20} /></div>
            <span>{label}</span><strong>{value}</strong><small>{note}</small>
          </article>
        ))}
      </div>

      <div className="dashboard-grid">
        <section className="card chart-card span-2">
          <div className="card-header"><div><span className="eyebrow">{dashboardData.period.trend_granularity === 'month' ? 'Monthly trend' : 'Period trend'}</span><h2>Leads over time</h2></div></div>
          <div className="chart-box">
            {dashboardData.trend.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={dashboardData.trend} margin={{ left: -20, right: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="name" tickLine={false} axisLine={false} fontSize={11} />
                  <YAxis tickLine={false} axisLine={false} fontSize={11} allowDecimals={false} />
                  <Tooltip />
                  <Line type="monotone" dataKey="leads" stroke="var(--accent)" strokeWidth={3} dot={false} />
                  <Line type="monotone" dataKey="completed" stroke="var(--success)" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : <div className="chart-empty">No leads in this period</div>}
          </div>
        </section>

        <section className="card priority-card">
          <div className="card-header"><div><span className="eyebrow">Priority</span><h2>Top prospects</h2></div><Target size={20} /></div>
          <div className="priority-list">
            {dashboardData.top_leads.map((lead) => (
              <button key={lead.id} onClick={() => setSelected(lead.id || null)}>
                <div className={`mini-score score-${lead.priority.toLowerCase()}`}>{lead.lead_score}</div>
                <div><strong>{lead.business_name}</strong><span>{lead.city} · {lead.recommended_service}{user?.role === 'admin' && lead.created_by_name ? ` · ${lead.created_by_name}` : ''}</span></div>
                <ArrowUpRight size={16} />
              </button>
            ))}
            {!dashboardData.top_leads.length && <div className="small-empty">No prospects in this period</div>}
          </div>
        </section>

        <section className="card chart-card span-2">
          <div className="card-header"><div><span className="eyebrow">Pipeline</span><h2>Lead progress</h2></div></div>
          <div className="chart-box compact-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={dashboardData.pipeline} margin={{ left: -20, right: 8 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" tickLine={false} axisLine={false} fontSize={10} />
                <YAxis tickLine={false} axisLine={false} fontSize={10} allowDecimals={false} />
                <Tooltip cursor={{ fill: 'rgba(255,142,1,.08)' }} />
                <Bar dataKey="value" fill="var(--accent)" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="card span-3">
          <div className="card-header"><div><span className="eyebrow">Recent</span><h2>Latest leads in period</h2></div></div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Business</th><th>City</th>{user?.role === 'admin' && <th>Created by</th>}<th>Score</th><th>Service</th><th>Status</th></tr></thead>
              <tbody>{dashboardData.recent_leads.map((lead) => <tr key={lead.id} onClick={() => setSelected(lead.id || null)}><td><strong>{lead.business_name}</strong><span>{lead.category}</span></td><td>{lead.city}</td>{user?.role === 'admin' && <td>{lead.created_by_name || 'Former user'}</td>}<td><StatusBadge value={lead.lead_score} /></td><td>{lead.recommended_service}</td><td><StatusBadge value={lead.status} /></td></tr>)}</tbody>
            </table>
          </div>
        </section>
      </div>
      <LeadDrawer leadId={selected} onClose={() => setSelected(null)} />
    </>
  )
}
