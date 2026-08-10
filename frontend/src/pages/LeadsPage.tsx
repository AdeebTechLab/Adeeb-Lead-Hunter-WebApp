import { Download, ExternalLink, Filter, Mail, Phone, Search, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, downloadFile } from '../api'
import EmptyState from '../components/EmptyState'
import LeadDrawer from '../components/LeadDrawer'
import Loader from '../components/Loader'
import StatusBadge from '../components/StatusBadge'
import { useRefresh } from '../contexts/RefreshContext'
import type { Lead } from '../types'

type LeadResponse = { items: Lead[]; total: number; page: number; pages: number }
type Options = { cities: string[]; categories: string[]; services: string[] }

const scoreBands = [
  ['0–39', 'Low confidence'],
  ['40–49', 'Cold / incomplete'],
  ['50–64', 'Warm'],
  ['65–74', 'Strong warm'],
  ['75–89', 'Hot'],
  ['90–100', 'Top priority'],
]

export default function LeadsPage() {
  const { leadId } = useParams()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [data, setData] = useState<LeadResponse | null>(null)
  const [options, setOptions] = useState<Options>({ cities: [], categories: [], services: [] })
  const [filters, setFilters] = useState({ q: '', city: '', category: '', priority: searchParams.get('priority') || '', status: '', service: '', website: '', social: '', contact: '', min_score: '0', sort_by: 'lead_score', sort_order: 'desc' })
  const [page, setPage] = useState(1)
  const { refreshKey } = useRefresh()

  const query = useMemo(() => {
    const params = new URLSearchParams({ page: String(page), page_size: '20', ...filters })
    for (const [key, value] of [...params.entries()]) if (!value) params.delete(key)
    return params.toString()
  }, [filters, page])

  function load() {
    api<LeadResponse>(`/leads?${query}`).then(setData).catch((error) => toast.error(error.message))
  }

  useEffect(load, [query, refreshKey])
  useEffect(() => { api<Options>('/leads/options').then(setOptions).catch(() => undefined) }, [refreshKey])

  async function exportLeads(format: 'csv' | 'xlsx') {
    try {
      await downloadFile(`/leads/export?format=${format}${filters.priority ? `&priority=${filters.priority}` : ''}${filters.status ? `&status=${filters.status}` : ''}`, `qualified-leads.${format}`)
      toast.success(`${format.toUpperCase()} exported`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Export failed')
    }
  }

  function reset() {
    setFilters({ q: '', city: '', category: '', priority: '', status: '', service: '', website: '', social: '', contact: '', min_score: '0', sort_by: 'lead_score', sort_order: 'desc' })
    setPage(1)
  }

  return (
    <>
      <section className="card filter-card">
        <div className="filter-title"><Filter size={18} /><strong>Filters</strong><button className="text-button" onClick={reset}><X size={15} />Clear</button></div>
        <div className="filters-grid">
          <label className="search-field"><Search size={17} /><input placeholder="Search business, phone or email" value={filters.q} onChange={(e) => { setPage(1); setFilters({ ...filters, q: e.target.value }) }} /></label>
          <select aria-label="City" value={filters.city} onChange={(e) => setFilters({ ...filters, city: e.target.value })}><option value="">All cities</option>{options.cities.map((item) => <option key={item}>{item}</option>)}</select>
          <select aria-label="Category" value={filters.category} onChange={(e) => setFilters({ ...filters, category: e.target.value })}><option value="">All categories</option>{options.categories.map((item) => <option key={item}>{item}</option>)}</select>
          <select aria-label="Priority" value={filters.priority} onChange={(e) => setFilters({ ...filters, priority: e.target.value })}><option value="">All priorities</option><option>Hot</option><option>Warm</option><option>Cold</option></select>
          <select aria-label="Status" value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}><option value="">All statuses</option><option>Not Contacted</option><option>Contacted</option><option>Follow-up</option><option>Closed</option></select>
          <select aria-label="Service" value={filters.service} onChange={(e) => setFilters({ ...filters, service: e.target.value })}><option value="">All services</option>{options.services.map((item) => <option key={item}>{item}</option>)}</select>
          <select aria-label="Website" value={filters.website} onChange={(e) => setFilters({ ...filters, website: e.target.value })}><option value="">Any website</option><option value="available">Website available</option><option value="missing">Website missing</option></select>
          <select aria-label="Social" value={filters.social} onChange={(e) => setFilters({ ...filters, social: e.target.value })}><option value="">Any social</option><option value="available">Social available</option><option value="missing">Social missing</option></select>
          <select aria-label="Contact" value={filters.contact} onChange={(e) => setFilters({ ...filters, contact: e.target.value })}><option value="">Any contact</option><option value="available">Direct contact available</option><option value="missing">Direct contact missing</option></select>
          <select aria-label="Score" value={filters.min_score} onChange={(e) => setFilters({ ...filters, min_score: e.target.value })}><option value="0">Any score</option><option value="40">40+</option><option value="50">50+</option><option value="65">65+</option><option value="75">75+</option><option value="90">90+</option></select>
          <select aria-label="Sort" value={filters.sort_by} onChange={(e) => setFilters({ ...filters, sort_by: e.target.value })}><option value="lead_score">Sort: score</option><option value="created_at">Sort: newest</option><option value="business_name">Sort: name</option><option value="city">Sort: city</option></select>
          <select aria-label="Order" value={filters.sort_order} onChange={(e) => setFilters({ ...filters, sort_order: e.target.value })}><option value="desc">Descending</option><option value="asc">Ascending</option></select>
        </div>
        <details className="score-guide">
          <summary>How the lead score works</summary>
          <p>A high score means a stronger, reachable sales opportunity—not that the business itself is better. The score combines visible service need, contactability and public engagement.</p>
          <div>{scoreBands.map(([range, label]) => <span key={range}><strong>{range}</strong>{label}</span>)}</div>
        </details>
      </section>
      <section className="card leads-card">
        <div className="card-header">
          <div><span className="eyebrow">Qualified database</span><h2>{data ? `${data.total} leads` : 'Leads'}</h2></div>
          <div className="button-row"><button className="button secondary" onClick={() => exportLeads('csv')}><Download size={16} />CSV</button><button className="button primary" onClick={() => exportLeads('xlsx')}><Download size={16} />Excel</button></div>
        </div>
        {!data ? <Loader /> : !data.items.length ? <EmptyState /> : (
          <>
            <div className="table-wrap">
              <table className="qualified-table">
                <thead><tr><th>Business</th><th>City</th><th>Contact</th><th>Website</th><th>Score</th><th>Service</th><th>Status</th></tr></thead>
                <tbody>{data.items.map((lead) => (
                  <tr key={lead.id} onClick={() => navigate(`/leads/${lead.id}`)}>
                    <td><strong>{lead.business_name}</strong><span>{lead.category}</span></td>
                    <td>{lead.city}</td>
                    <td>
                      <div className="table-contact">
                        <strong>{lead.phone || lead.email || 'Not published'}</strong>
                        <span>{lead.contact_status || 'Research needed'}</span>
                        <div>
                          {lead.phone && <a href={`tel:${lead.phone}`} onClick={(event) => event.stopPropagation()} title="Call"><Phone size={13} /></a>}
                          {lead.email && <a href={`mailto:${lead.email}`} onClick={(event) => event.stopPropagation()} title="Email"><Mail size={13} /></a>}
                          {lead.contact_search_url && <a href={lead.contact_search_url} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()} title="Review listing"><ExternalLink size={13} /></a>}
                        </div>
                      </div>
                    </td>
                    <td><StatusBadge value={lead.website ? 'Available' : 'Missing'} /></td>
                    <td><div className="score-cell"><strong>{lead.lead_score}</strong><StatusBadge value={lead.priority} /></div></td>
                    <td>{lead.recommended_service}</td><td><StatusBadge value={lead.status} /></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
            <div className="pagination"><button disabled={page === 1} onClick={() => setPage((value) => value - 1)}>Previous</button><span>{page} / {data.pages}</span><button disabled={page >= data.pages} onClick={() => setPage((value) => value + 1)}>Next</button></div>
          </>
        )}
      </section>
      <LeadDrawer leadId={leadId || null} onClose={() => navigate('/leads')} onChanged={load} />
    </>
  )
}
