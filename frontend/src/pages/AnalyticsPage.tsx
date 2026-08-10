import { CircleDollarSign, Gauge, Target, Trophy } from 'lucide-react'
import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import Loader from '../components/Loader'
import { useRefresh } from '../contexts/RefreshContext'

type Analytics = {
  priorities: { name: string; value: number }[]
  statuses: { name: string; value: number }[]
  cities: { name: string; value: number }[]
  average_score: number
  won: number
  lost: number
  open: number
}

export default function AnalyticsPage() {
  const [data, setData] = useState<Analytics | null>(null)
  const { refreshKey } = useRefresh()
  useEffect(() => { api<Analytics>('/analytics').then(setData).catch((error) => toast.error(error.message)) }, [refreshKey])
  if (!data) return <Loader />

  const cards = [
    { label: 'Average score', value: data.average_score, icon: Gauge },
    { label: 'Open deals', value: data.open, icon: Target },
    { label: 'Won deals', value: data.won, icon: Trophy },
    { label: 'Lost deals', value: data.lost, icon: CircleDollarSign },
  ]

  return (
    <div className="stack-lg">
      <div className="metric-grid">{cards.map(({ label, value, icon: Icon }) => <article className="metric-card" key={label}><div className="metric-icon"><Icon size={20} /></div><span>{label}</span><strong>{value}</strong><small>Current workspace</small></article>)}</div>
      <div className="analytics-grid">
        <section className="card"><div className="card-header"><div><span className="eyebrow">Quality</span><h2>Lead priority</h2></div></div><div className="chart-box"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={data.priorities} dataKey="value" nameKey="name" innerRadius={55} outerRadius={90} paddingAngle={4}>{data.priorities.map((_, index) => <Cell key={index} fill={['#ff8e01', '#6f7d8b', '#c5ccd2'][index]} />)}</Pie><Tooltip /></PieChart></ResponsiveContainer></div><div className="legend-row">{data.priorities.map((item) => <span key={item.name}><i />{item.name} {item.value}</span>)}</div></section>
        <section className="card"><div className="card-header"><div><span className="eyebrow">Geography</span><h2>Leads by city</h2></div></div><div className="chart-box"><ResponsiveContainer width="100%" height="100%"><BarChart data={data.cities} layout="vertical" margin={{ left: 15 }}><CartesianGrid strokeDasharray="3 3" horizontal={false} /><XAxis type="number" hide /><YAxis dataKey="name" type="category" tickLine={false} axisLine={false} width={90} fontSize={11} /><Tooltip /><Bar dataKey="value" fill="#ff8e01" radius={[0, 8, 8, 0]} /></BarChart></ResponsiveContainer></div></section>
        <section className="card span-2"><div className="card-header"><div><span className="eyebrow">Pipeline</span><h2>Status distribution</h2></div></div><div className="chart-box wide"><ResponsiveContainer width="100%" height="100%"><BarChart data={data.statuses}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="name" tickLine={false} axisLine={false} fontSize={11} /><YAxis allowDecimals={false} tickLine={false} axisLine={false} fontSize={11} /><Tooltip /><Bar dataKey="value" fill="#222d38" radius={[8, 8, 0, 0]} /></BarChart></ResponsiveContainer></div></section>
      </div>
    </div>
  )
}
