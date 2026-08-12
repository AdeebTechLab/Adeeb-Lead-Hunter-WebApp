import { Copy, ExternalLink, Facebook, Globe2, Instagram, Linkedin, Mail, MapPinned, Phone, RefreshCw, SearchCheck, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { api } from '../api'
import type { Lead } from '../types'
import StatusBadge from './StatusBadge'

function displayValue(value: unknown) {
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (Array.isArray(value)) return value.length ? value.join(', ') : '—'
  return String(value ?? '—')
}

export default function LeadDrawer({ leadId, onClose, onChanged }: { leadId: string | null; onClose: () => void; onChanged?: () => void }) {
  const [lead, setLead] = useState<Lead | null>(null)
  const [loading, setLoading] = useState(false)
  const [auditing, setAuditing] = useState(false)
  const [enriching, setEnriching] = useState(false)
  const [tab, setTab] = useState<'overview' | 'audit' | 'outreach' | 'crm'>('overview')
  const [form, setForm] = useState<Record<string, string>>({})

  function loadLead() {
    if (!leadId) return
    setLoading(true)
    api<Lead>(`/leads/${leadId}`)
      .then((data) => {
        setLead(data)
        setForm({
          status: data.status || 'Not Contacted',
          assigned_salesperson: data.assigned_salesperson || '',
          call_status: data.call_status || 'Pending',
          proposal_status: data.proposal_status || 'Not sent',
          deal_status: data.deal_status || 'Open',
          follow_up_date: data.follow_up_date || '',
          last_contact_date: data.last_contact_date || '',
          notes: data.notes || '',
          meeting_notes: data.meeting_notes || '',
          tags: (data.tags || []).join(', '),
        })
      })
      .catch((error) => toast.error(error.message))
      .finally(() => setLoading(false))
  }

  useEffect(loadLead, [leadId])

  if (!leadId) return null

  async function audit() {
    setAuditing(true)
    try {
      const data = await api<Record<string, unknown>>(`/leads/${leadId}/audit`, { method: 'POST' })
      setLead((current) => (current ? { ...current, ...data } as Lead : current))
      setTab('audit')
      toast.success('Business audit completed')
      onChanged?.()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Audit failed')
    } finally {
      setAuditing(false)
    }
  }

  async function enrichContact() {
    setEnriching(true)
    try {
      const data = await api<{ lead: Lead; notes: string[] }>(`/leads/${leadId}/enrich-contact`, { method: 'POST' })
      setLead(data.lead)
      toast.success(data.lead.phone || data.lead.email ? 'Contact details refreshed' : 'Contact sources checked')
      if (data.notes.length) toast(data.notes[0])
      onChanged?.()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Contact enrichment failed')
    } finally {
      setEnriching(false)
    }
  }

  async function saveCrm() {
    try {
      const payload = { ...form, tags: (form.tags || '').split(',').map((item) => item.trim()).filter(Boolean) }
      const updated = await api<Lead>(`/leads/${leadId}`, { method: 'PATCH', body: JSON.stringify(payload) })
      setLead(updated)
      toast.success('CRM updated')
      onChanged?.()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Update failed')
    }
  }

  function copy(value: string) {
    navigator.clipboard.writeText(value)
    toast.success('Copied')
  }

  const auditData = (lead?.audit || {}) as Record<string, unknown>
  const socialData = (auditData.social_media || {}) as Record<string, unknown>
  const contactVerification = (auditData.contact_verification || {}) as Record<string, unknown>
  const flatAudit = Object.entries(auditData).filter(([key, value]) => !['checked_at', 'final_url', 'website_age_note', 'social_media', 'contact_verification'].includes(key) && typeof value !== 'object')

  return (
    <div className="drawer-layer">
      <button className="drawer-overlay" onClick={onClose} aria-label="Close lead" />
      <aside className="lead-drawer">
        <div className="drawer-header">
          <div>
            <span className="eyebrow">{lead?.category}</span>
            <h2>{lead?.business_name || 'Lead'}</h2>
          </div>
          <button className="icon-button" onClick={onClose}><X size={19} /></button>
        </div>
        {loading || !lead ? <div className="drawer-loading">Loading…</div> : (
          <>
            <div className="lead-score-strip">
              <div className={`score-ring score-${lead.priority.toLowerCase()}`}>{lead.lead_score}</div>
              <div><StatusBadge value={lead.priority} /><strong>{lead.recommended_service}</strong><span>{lead.score_profile?.label || `${lead.priority} lead`}</span></div>
              <div className="lead-strip-actions">
                <button className="button secondary compact" onClick={enrichContact} disabled={enriching}><SearchCheck size={15} className={enriching ? 'spin' : ''} /> Contact</button>
                <button className="button secondary compact" onClick={audit} disabled={auditing}><RefreshCw size={15} className={auditing ? 'spin' : ''} /> Audit</button>
              </div>
            </div>
            <div className="drawer-tabs">
              {(['overview', 'audit', 'outreach', 'crm'] as const).map((item) => <button key={item} className={tab === item ? 'active' : ''} onClick={() => setTab(item)}>{item}</button>)}
            </div>
            <div className="drawer-body themed-scrollbar">
              {tab === 'overview' && (
                <div className="stack-lg">
                  <p className="summary-box">{lead.business_summary}</p>
                  <div className="score-explanation">
                    <div><strong>{lead.lead_score}/100 · {lead.score_profile?.label || lead.priority}</strong><span>{lead.score_profile?.meaning || 'Score reflects opportunity, evidence and contactability.'}</span></div>
                    <p>{lead.score_profile?.action}</p>
                    {lead.score_breakdown && <div className="score-breakdown"><span>Opportunity <strong>{lead.score_breakdown.opportunity_signal}/60</strong></span><span>Contactability <strong>{lead.score_breakdown.contactability}/20</strong></span><span>Engagement <strong>{lead.score_breakdown.engagement_signal}/20</strong></span></div>}
                  </div>
                  <div className="info-grid">
                    <div><span>City</span><strong>{lead.city}</strong></div>
                    <div><span>Status</span><StatusBadge value={lead.status} /></div>
                    <div><span>Created by</span><strong>{lead.created_by_name || 'Former user'}</strong></div>
                    <div><span>Phone</span><strong>{lead.phone || 'Not published'}</strong></div>
                    <div><span>Email</span><strong>{lead.email || 'Not published'}</strong></div>
                    <div><span>Contact status</span><strong>{lead.contact_status || 'Research needed'}</strong></div>
                    <div><span>Confidence</span><strong>{lead.contact_confidence || 'Low'}</strong></div>
                  </div>
                  <div className="link-list contact-link-list">
                    {lead.phone && <a className="primary-contact" href={`tel:${lead.phone}`}><Phone size={16} />Call {lead.phone}</a>}
                    {lead.email && <a href={`mailto:${lead.email}`}><Mail size={16} />Email</a>}
                    {lead.website && <a href={lead.website} target="_blank" rel="noreferrer"><Globe2 size={16} />Website<ExternalLink size={14} /></a>}
                    {lead.google_business_url && <a href={lead.google_business_url} target="_blank" rel="noreferrer"><MapPinned size={16} />Google Maps<ExternalLink size={14} /></a>}
                    {!lead.google_business_url && lead.contact_search_url && <a href={lead.contact_search_url} target="_blank" rel="noreferrer"><MapPinned size={16} />Find contact on Maps<ExternalLink size={14} /></a>}
                    {lead.source_url && <a href={lead.source_url} target="_blank" rel="noreferrer">Source<ExternalLink size={14} /></a>}
                  </div>
                  {!!lead.contact_sources?.length && <div className="source-proof"><span>Contact sources</span><strong>{lead.contact_sources.join(' · ')}</strong><small>Verify the decision-maker before outreach. The system does not invent missing numbers.</small></div>}
                  <div>
                    <h3>Qualification reasons</h3>
                    <ul className="reason-list">{lead.score_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
                  </div>
                  {!!lead.competitor_insights?.length && <div>
                    <h3>Competitor insights</h3>
                    <div className="competitor-list">{lead.competitor_insights.map((competitor) => <div key={competitor.id}><div><strong>{competitor.business_name}</strong><span>{competitor.lead_score}/100 · {competitor.recommended_service}</span></div><StatusBadge value={competitor.priority} /></div>)}</div>
                  </div>}
                </div>
              )}
              {tab === 'audit' && (
                <div className="stack-lg">
                  {!Object.keys(auditData).length ? <div className="summary-box">Run the business audit to verify website, contact and social-presence signals.</div> : (
                    <div className="audit-grid">
                      {flatAudit.map(([key, value]) => <div key={key}><span>{key.replaceAll('_', ' ')}</span><strong>{displayValue(value)}</strong></div>)}
                    </div>
                  )}
                  {!!Object.keys(contactVerification).length && <div className="audit-section"><h3>Contact verification</h3><div className="audit-grid">{Object.entries(contactVerification).map(([key, value]) => <div key={key}><span>{key.replaceAll('_', ' ')}</span><strong>{displayValue(value)}</strong></div>)}</div></div>}
                  {!!Object.keys(socialData).length && <div className="audit-section">
                    <h3>Social media activity</h3>
                    <div className="audit-grid">{Object.entries(socialData).map(([key, value]) => <div key={key} className={['activity_explanation', 'recommended_action', 'verification_status'].includes(key) ? 'wide' : ''}><span>{key.replaceAll('_', ' ')}</span><strong>{displayValue(value)}</strong></div>)}</div>
                    <div className="social-links">
                      {lead.facebook && <a href={lead.facebook} target="_blank" rel="noreferrer"><Facebook size={15} />Facebook</a>}
                      {lead.instagram && <a href={lead.instagram} target="_blank" rel="noreferrer"><Instagram size={15} />Instagram</a>}
                      {lead.linkedin && <a href={lead.linkedin} target="_blank" rel="noreferrer"><Linkedin size={15} />LinkedIn</a>}
                    </div>
                  </div>}
                </div>
              )}
              {tab === 'outreach' && (
                <div className="stack-lg outreach-stack">
                  <div className="outreach-contact-bar">
                    <div><strong>Contact now</strong><span>{lead.phone || lead.email || 'Verify a public contact first'}</span></div>
                    {lead.phone && <a className="button primary compact" href={`tel:${lead.phone}`}><Phone size={15} />Call</a>}
                    {!lead.phone && lead.contact_search_url && <a className="button secondary compact" href={lead.contact_search_url} target="_blank" rel="noreferrer"><MapPinned size={15} />Find contact</a>}
                  </div>
                  {Object.entries(lead.outreach || {}).map(([key, value]) => (
                    <div className={`message-card ${key === 'cold_call' ? 'featured-script' : ''}`} key={key}>
                      <div><strong>{key.replaceAll('_', ' ')}</strong><button className="icon-button small" onClick={() => copy(String(value))}><Copy size={15} /></button></div>
                      <pre>{value}</pre>
                    </div>
                  ))}
                </div>
              )}
              {tab === 'crm' && (
                <div className="form-grid crm-form">
                  <label>Status<select value={form.status} onChange={(e) => { const status = e.target.value; setForm({ ...form, status, deal_status: status === 'Completed' ? 'Won' : status === 'Cancel' ? 'Lost' : form.deal_status }) }}><option>Not Contacted</option><option>Contacted</option><option>Follow-up</option><option>Cancel</option><option>Completed</option></select></label>
                  <label>Assigned salesperson<input value={form.assigned_salesperson} onChange={(e) => setForm({ ...form, assigned_salesperson: e.target.value })} /></label>
                  <label>Call status<select value={form.call_status} onChange={(e) => setForm({ ...form, call_status: e.target.value })}><option>Pending</option><option>Connected</option><option>No answer</option><option>Not interested</option><option>Callback</option></select></label>
                  <label>Proposal<select value={form.proposal_status} onChange={(e) => setForm({ ...form, proposal_status: e.target.value })}><option>Not sent</option><option>Draft</option><option>Sent</option><option>Accepted</option><option>Rejected</option></select></label>
                  <label>Deal<select value={form.deal_status} onChange={(e) => { const deal = e.target.value; setForm({ ...form, deal_status: deal, status: deal === 'Won' ? 'Completed' : deal === 'Lost' ? 'Cancel' : (form.status === 'Completed' || form.status === 'Cancel' ? 'Follow-up' : form.status) }) }}><option>Open</option><option>Won</option><option>Lost</option></select></label>
                  <label>Follow-up date<input type="date" value={form.follow_up_date} onChange={(e) => setForm({ ...form, follow_up_date: e.target.value })} /></label>
                  <label>Last contact<input type="date" value={form.last_contact_date} onChange={(e) => setForm({ ...form, last_contact_date: e.target.value })} /></label>
                  <label className="full">Tags<input placeholder="priority, city, niche" value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} /></label>
                  <label className="full">Notes<textarea rows={4} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></label>
                  <label className="full">Meeting notes<textarea rows={4} value={form.meeting_notes} onChange={(e) => setForm({ ...form, meeting_notes: e.target.value })} /></label>
                  <button className="button primary full" onClick={saveCrm}>Save CRM</button>
                </div>
              )}
            </div>
          </>
        )}
      </aside>
    </div>
  )
}
