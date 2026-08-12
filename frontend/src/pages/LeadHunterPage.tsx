import { AlertTriangle, Cloud, ExternalLink, Globe2, Mail, MapPin, MapPinned, Phone, Search, Sparkles } from 'lucide-react'
import { FormEvent, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { api } from '../api'
import EmptyState from '../components/EmptyState'
import StatusBadge from '../components/StatusBadge'
import type { Lead, ProviderOption } from '../types'

const niches = [
  'Restaurant', 'Cafe', 'Bakery', 'Real Estate', 'Property Dealer', 'Hospital', 'Clinic', 'Dental Clinic',
  'Medical Laboratory', 'Pharmacy', 'Physiotherapy', 'Veterinarian', 'Beauty Salon', 'Spa', 'School',
  'Academy', 'College', 'University', 'Tuition Center', 'Coaching Center', 'Daycare', 'Gym', 'Fitness Center',
  'Hotel', 'Guest House', 'Travel Agency', 'Law Firm', 'Car Dealership', 'Auto Workshop', 'Software House',
  'Digital Marketing Agency', 'Accountant', 'Architect', 'Construction Company', 'Insurance', 'Bank',
  'Supermarket', 'Grocery Store', 'Clothing Store', 'Boutique', 'Electronics Store', 'Furniture Store',
  'Wedding Hall', 'Event Planner', 'Photographer', 'Courier', 'Logistics', 'Coworking Space', 'Any Local Business',
]
const provinces = ['Punjab', 'Sindh', 'Khyber Pakhtunkhwa', 'Balochistan', 'Islamabad Capital Territory', 'Gilgit-Baltistan', 'Azad Jammu and Kashmir']

type SearchResponse = {
  items: Lead[]
  count: number
  excluded_existing: number
  provider: string
  cached: boolean
  attribution?: string | null
  warnings: string[]
}

type ProviderResponse = { default: string; providers: ProviderOption[]; contact_enrichment?: { tomtom: boolean; website: boolean; google: boolean } }

export default function LeadHunterPage() {
  const [form, setForm] = useState({ keyword: 'Restaurant', city: 'Lahore', province: 'Punjab', provider: 'auto', limit: 12 })
  const [items, setItems] = useState<Lead[]>([])
  const [meta, setMeta] = useState<Omit<SearchResponse, 'items' | 'count' | 'excluded_existing'> | null>(null)
  const [providers, setProviders] = useState<ProviderOption[]>([])
  const [contactEnrichment, setContactEnrichment] = useState({ tomtom: false, website: true, google: false })
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [loading, setLoading] = useState(false)
  const [importing, setImporting] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)

  useEffect(() => {
    api<ProviderResponse>('/leads/providers')
      .then((data) => { setProviders(data.providers); if (data.contact_enrichment) setContactEnrichment(data.contact_enrichment) })
      .catch(() => setProviders([]))
  }, [])

  async function search(event: FormEvent) {
    event.preventDefault()
    setLoading(true)
    setSelected(new Set())
    setMeta(null)
    setSearchError(null)
    try {
      const result = await api<SearchResponse>('/leads/search', { method: 'POST', body: JSON.stringify(form) })
      setItems(result.items)
      setMeta({ provider: result.provider, cached: result.cached, attribution: result.attribution, warnings: result.warnings || [] })
      toast.success(result.excluded_existing ? `${result.items.length} new leads found · ${result.excluded_existing} already qualified hidden` : `${result.items.length} new leads found`)
    } catch (error) {
      setItems([])
      setSearchError(error instanceof Error ? error.message : 'Live search is temporarily unavailable. Please retry.')
    } finally {
      setLoading(false)
    }
  }

  async function importSelected() {
    const leads = items.filter((_, index) => selected.has(index))
    if (!leads.length) return toast.error('Select at least one lead')
    setImporting(true)
    try {
      const result = await api<{ imported: number; duplicates: number }>('/leads/bulk', { method: 'POST', body: JSON.stringify({ leads }) })
      toast.success(`${result.imported} imported · ${result.duplicates} duplicates skipped`)
      setSelected(new Set())
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Import failed')
    } finally {
      setImporting(false)
    }
  }

  function toggle(index: number) {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
    })
  }

  return (
    <div className="stack-lg">
      <section className="card hunter-card">
        <div className="card-header"><div><span className="eyebrow">Business search</span><h2>Find live public leads</h2></div><Sparkles size={21} /></div>
        <form className="hunter-form" onSubmit={search}>
          <label>Keyword<input list="niches" value={form.keyword} onChange={(e) => setForm({ ...form, keyword: e.target.value })} required /><datalist id="niches">{niches.map((item) => <option key={item} value={item} />)}</datalist></label>
          <label>City<div className="input-with-icon plain city-input-wrap"><MapPin size={17} /><input className="city-entry" value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} required /></div></label>
          <label>Province<select value={form.province} onChange={(e) => setForm({ ...form, province: e.target.value })}>{provinces.map((item) => <option key={item}>{item}</option>)}</select></label>
          <label>Source<select value={form.provider} onChange={(e) => setForm({ ...form, provider: e.target.value })}>
            {(providers.length ? providers.filter((provider) => provider.id === 'auto' || provider.configured) : [
              { id: 'auto', name: 'Automatic', configured: true, description: '' },
              { id: 'osm', name: 'OpenStreetMap', configured: true, description: '' },
            ] as ProviderOption[]).map((provider) => <option key={provider.id} value={provider.id}>{provider.name}</option>)}
          </select></label>
          <label>Limit<select value={form.limit} onChange={(e) => setForm({ ...form, limit: Number(e.target.value) })}><option>8</option><option>12</option><option>20</option><option>30</option></select></label>
          <button className="button primary" disabled={loading}><Search size={17} />{loading ? 'Searching live' : 'Search'}</button>
        </form>
        <div className="source-note"><Cloud size={15} />Geoapify/OpenStreetMap discovery · {contactEnrichment.tomtom ? 'TomTom Search API + official website contact verification' : 'official website contact verification'}</div>
        {meta && <div className="source-meta"><strong>{meta.provider.replaceAll('+', ' + ')}</strong><span>{meta.cached ? 'Cached result' : 'Live result'}</span>{meta.attribution && <span>{meta.attribution}</span>}</div>}
        {meta?.warnings.map((warning) => <div className="provider-warning" key={warning}><AlertTriangle size={14} />{warning}</div>)}
        {searchError && <div className="search-error-panel" role="alert"><AlertTriangle size={19} /><div><strong>Live search could not complete</strong><span>{searchError}</span></div><button type="button" className="button secondary compact" onClick={() => setSearchError(null)}>Dismiss</button></div>}
      </section>

      <section className="card">
        <div className="card-header">
          <div><span className="eyebrow">Results</span><h2>{items.length ? `${items.length} businesses` : 'Search results'}</h2></div>
          <button className="button secondary" onClick={importSelected} disabled={!selected.size || importing}>{importing ? 'Importing' : `Import selected (${selected.size})`}</button>
        </div>
        {!items.length ? <EmptyState title="Run a real-time business search" /> : (
          <div className="table-wrap">
            <table className="hunter-results-table">
              <thead><tr><th><input type="checkbox" checked={selected.size === items.length} onChange={() => setSelected(selected.size === items.length ? new Set() : new Set(items.map((_, index) => index)))} /></th><th>Business</th><th>Contact</th><th>Website</th><th>Score</th><th>Service</th></tr></thead>
              <tbody>{items.map((lead, index) => (
                <tr key={`${lead.business_name}-${lead.source_url || index}`}>
                  <td><input type="checkbox" checked={selected.has(index)} onChange={() => toggle(index)} /></td>
                  <td><strong>{lead.business_name}</strong><span>{lead.category} · {lead.city}</span></td>
                  <td>
                    <div className="contact-cell enriched-contact-cell">
                      <div className="contact-lines">
                        {lead.phone ? <a href={`tel:${lead.phone}`}><Phone size={13} /><span>{lead.phone}</span></a> : <span className="missing-contact"><Phone size={13} />Phone not published</span>}
                        {lead.email ? <a href={`mailto:${lead.email}`}><Mail size={13} /><span>{lead.email}</span></a> : <span className="missing-contact"><Mail size={13} />Email not published</span>}
                      </div>
                      <div className="contact-evidence">
                        <span>{lead.contact_status || 'Research needed'} · {lead.contact_confidence || 'Low'} confidence</span>
                        {!!lead.contact_sources?.length && <small>{lead.contact_sources.slice(0, 3).join(' · ')}</small>}
                      </div>
                      <div className="contact-actions contact-actions-labeled">
                        {lead.phone && <a href={`tel:${lead.phone}`} title="Call"><Phone size={13} /><span>Call</span></a>}
                        {lead.email && <a href={`mailto:${lead.email}`} title="Email"><Mail size={13} /><span>Email</span></a>}
                        {lead.website && <a href={lead.website} target="_blank" rel="noreferrer" title="Official website"><Globe2 size={13} /><span>Website</span></a>}
                        {lead.contact_search_url && <a href={lead.contact_search_url} target="_blank" rel="noreferrer" title="Verify this business on Google Maps"><MapPinned size={13} /><span>Verify Maps</span><ExternalLink size={11} /></a>}
                      </div>
                    </div>
                  </td>
                  <td><StatusBadge value={lead.website ? 'Available' : 'Missing'} /></td>
                  <td><div className="score-cell"><strong>{lead.lead_score}</strong><StatusBadge value={lead.priority} /></div></td>
                  <td>{lead.recommended_service}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
