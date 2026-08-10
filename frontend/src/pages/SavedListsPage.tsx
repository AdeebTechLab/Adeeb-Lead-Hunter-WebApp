import { FolderKanban, Plus, Trash2, UserPlus, X } from 'lucide-react'
import { FormEvent, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { api } from '../api'
import EmptyState from '../components/EmptyState'
import LeadDrawer from '../components/LeadDrawer'
import Loader from '../components/Loader'
import StatusBadge from '../components/StatusBadge'
import { useRefresh } from '../contexts/RefreshContext'
import type { Lead } from '../types'

type SavedList = {
  id: string
  name: string
  description: string
  lead_count: number
  leads: Lead[]
  updated_at: string
}

export default function SavedListsPage() {
  const [lists, setLists] = useState<SavedList[] | null>(null)
  const [leads, setLeads] = useState<Lead[]>([])
  const [form, setForm] = useState({ name: '', description: '' })
  const [choices, setChoices] = useState<Record<string, string>>({})
  const [selectedLead, setSelectedLead] = useState<string | null>(null)
  const { refreshKey } = useRefresh()

  function load() {
    Promise.all([
      api<{ items: SavedList[] }>('/lists'),
      api<{ items: Lead[] }>('/leads?page_size=100&sort_by=lead_score&sort_order=desc'),
    ]).then(([listData, leadData]) => {
      setLists(listData.items)
      setLeads(leadData.items)
    }).catch((error) => toast.error(error.message))
  }

  useEffect(load, [refreshKey])

  async function create(event: FormEvent) {
    event.preventDefault()
    try {
      await api('/lists', { method: 'POST', body: JSON.stringify(form) })
      setForm({ name: '', description: '' })
      toast.success('Lead list created')
      load()
    } catch (error) { toast.error(error instanceof Error ? error.message : 'List creation failed') }
  }

  async function addLead(listId: string) {
    const leadId = choices[listId]
    if (!leadId) return toast.error('Select a lead')
    try {
      await api(`/lists/${listId}/leads`, { method: 'POST', body: JSON.stringify({ lead_id: leadId }) })
      toast.success('Lead added')
      load()
    } catch (error) { toast.error(error instanceof Error ? error.message : 'Add failed') }
  }

  async function removeLead(listId: string, leadId: string) {
    try { await api(`/lists/${listId}/leads/${leadId}`, { method: 'DELETE' }); load() }
    catch (error) { toast.error(error instanceof Error ? error.message : 'Remove failed') }
  }

  async function deleteList(listId: string) {
    try { await api(`/lists/${listId}`, { method: 'DELETE' }); toast.success('List deleted'); load() }
    catch (error) { toast.error(error instanceof Error ? error.message : 'Delete failed') }
  }

  if (!lists) return <Loader />

  return (
    <>
      <div className="stack-lg">
        <section className="card">
          <div className="card-header"><div><span className="eyebrow">Lead organization</span><h2>Create saved list</h2></div><FolderKanban size={20} /></div>
          <form className="saved-list-form" onSubmit={create}>
            <input required minLength={2} placeholder="List name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <input placeholder="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            <button className="button primary"><Plus size={16} />Create</button>
          </form>
        </section>

        {!lists.length ? <section className="card"><EmptyState title="Create your first saved list" /></section> : (
          <div className="saved-lists-grid">
            {lists.map((list) => (
              <section className="card saved-list-card" key={list.id}>
                <div className="card-header">
                  <div><span className="eyebrow">{list.lead_count} leads</span><h2>{list.name}</h2><p>{list.description || 'Qualified lead list'}</p></div>
                  <button className="icon-button small" onClick={() => deleteList(list.id)} title="Delete list"><Trash2 size={15} /></button>
                </div>
                <div className="list-add-row">
                  <select value={choices[list.id] || ''} onChange={(e) => setChoices({ ...choices, [list.id]: e.target.value })}>
                    <option value="">Select lead</option>
                    {leads.map((lead) => <option key={lead.id} value={lead.id}>{lead.business_name} · {lead.lead_score}</option>)}
                  </select>
                  <button className="button secondary" onClick={() => addLead(list.id)}><UserPlus size={15} />Add</button>
                </div>
                {!list.leads.length ? <EmptyState title="No leads in this list" /> : (
                  <div className="saved-list-leads">
                    {list.leads.map((lead) => (
                      <div key={lead.id}>
                        <button className="saved-lead-main" onClick={() => setSelectedLead(lead.id || null)}><div><strong>{lead.business_name}</strong><span>{lead.city} · {lead.recommended_service}</span></div><StatusBadge value={lead.priority} /></button>
                        <button className="icon-button small" onClick={() => removeLead(list.id, lead.id || '')}><X size={14} /></button>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            ))}
          </div>
        )}
      </div>
      <LeadDrawer leadId={selectedLead} onClose={() => setSelectedLead(null)} onChanged={load} />
    </>
  )
}
