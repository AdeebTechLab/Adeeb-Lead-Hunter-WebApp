import { CalendarDays, PhoneCall, UserRound } from 'lucide-react'
import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { api } from '../api'
import LeadDrawer from '../components/LeadDrawer'
import Loader from '../components/Loader'
import StatusBadge from '../components/StatusBadge'
import { useRefresh } from '../contexts/RefreshContext'
import type { Lead } from '../types'

const columns = ['Not Contacted', 'Contacted', 'Follow-up', 'Closed'] as const

export default function CrmPage() {
  const [leads, setLeads] = useState<Lead[] | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const { refreshKey } = useRefresh()

  function load() {
    api<{ items: Lead[] }>('/leads?page_size=100&sort_by=updated_at&sort_order=desc').then((data) => setLeads(data.items)).catch((error) => toast.error(error.message))
  }
  useEffect(load, [refreshKey])
  if (!leads) return <Loader />

  return (
    <>
      <div className="kanban-board">
        {columns.map((column) => {
          const items = leads.filter((lead) => lead.status === column)
          return (
            <section className="kanban-column" key={column}>
              <div className="kanban-title"><span>{column}</span><em>{items.length}</em></div>
              <div className="kanban-list">
                {items.map((lead) => (
                  <button className="kanban-card" key={lead.id} onClick={() => setSelected(lead.id || null)}>
                    <div className="kanban-card-top"><StatusBadge value={lead.priority} /><strong>{lead.lead_score}</strong></div>
                    <h3>{lead.business_name}</h3><p>{lead.recommended_service}</p>
                    <div className="kanban-meta"><span><UserRound size={14} />{lead.assigned_salesperson || 'Unassigned'}</span><span><PhoneCall size={14} />{lead.call_status || 'Pending'}</span>{lead.follow_up_date && <span><CalendarDays size={14} />{lead.follow_up_date}</span>}</div>
                  </button>
                ))}
              </div>
            </section>
          )
        })}
      </div>
      <LeadDrawer leadId={selected} onClose={() => setSelected(null)} onChanged={load} />
    </>
  )
}
