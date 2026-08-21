import { AlertTriangle, CheckCircle2, Cloud, ExternalLink, Globe2, Mail, MapPin, MapPinned, Phone, Search, Sparkles } from 'lucide-react'
import { FormEvent, useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import { api } from '../api'
import EmptyState from '../components/EmptyState'
import StatusBadge from '../components/StatusBadge'
import type { Lead } from '../types'
import { googleMapsVerificationUrl } from '../utils/maps'

const niches = [
  'Restaurant', 'Cafe', 'Bakery', 'Real Estate', 'Property Dealer', 'Hospital', 'Clinic', 'Dental Clinic',
  'Medical Laboratory', 'Pharmacy', 'Physiotherapy', 'Veterinarian', 'Beauty Salon', 'Spa', 'School',
  'Academy', 'College', 'University', 'Tuition Center', 'Coaching Center', 'Daycare', 'Gym', 'Fitness Center',
  'Hotel', 'Guest House', 'Travel Agency', 'Law Firm', 'Car Dealership', 'Auto Workshop', 'Software House',
  'Digital Marketing Agency', 'Accountant', 'Architect', 'Construction Company', 'Insurance', 'Bank',
  'Supermarket', 'Grocery Store', 'Clothing Store', 'Boutique', 'Electronics Store', 'Furniture Store',
  'Wedding Hall', 'Banquet Hall', 'Event Planner', 'Photographer', 'Courier', 'Logistics', 'Coworking Space',
  'Any Local Business',
]

const cities = [
  'Lahore', 'Karachi', 'Islamabad', 'Rawalpindi', 'Faisalabad', 'Multan', 'Peshawar', 'Quetta', 'Gujranwala',
  'Sialkot', 'Hyderabad', 'Bahawalpur', 'Sargodha', 'Sukkur', 'Abbottabad', 'Gujrat', 'Jhelum', 'Kasur', 'Sahiwal',
  'Okara', 'Rahim Yar Khan', 'Dera Ghazi Khan', 'Mardan', 'Nowshera', 'Swabi', 'Mansehra', 'Haripur', 'Wah Cantt',
  'Taxila', 'Mirpur', 'Muzaffarabad', 'Gilgit', 'Gwadar', 'Turbat', 'Khuzdar', 'Larkana', 'Nawabshah', 'Mirpur Khas',
]

type SearchResponse = {
  items: Lead[]
  count: number
  excluded_existing: number
  provider: string
  cached: boolean
  attribution?: string | null
  warnings: string[]
  pages_scanned?: number
  resolved_city?: string
  resolved_province?: string
  city_corrected?: boolean
  requested_count?: number
  source_exhausted?: boolean
}

type ProviderResponse = {
  contact_enrichment?: { tomtom: boolean; website: boolean; google: boolean }
}

function normalisedBusinessName(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()
}

function branchMeta(items: Lead[], index: number) {
  const key = normalisedBusinessName(items[index]?.business_name || '')
  if (!key) return null
  const matches = items.map((lead, itemIndex) => ({ lead, itemIndex })).filter(({ lead }) => normalisedBusinessName(lead.business_name) === key)
  if (matches.length < 2) return null
  const position = matches.findIndex(({ itemIndex }) => itemIndex === index) + 1
  return { position, total: matches.length }
}

function editDistance(left: string, right: string) {
  const a = left.toLowerCase()
  const b = right.toLowerCase()
  const row = Array.from({ length: b.length + 1 }, (_, index) => index)
  for (let i = 1; i <= a.length; i += 1) {
    let previous = row[0]
    row[0] = i
    for (let j = 1; j <= b.length; j += 1) {
      const saved = row[j]
      row[j] = Math.min(row[j] + 1, row[j - 1] + 1, previous + (a[i - 1] === b[j - 1] ? 0 : 1))
      previous = saved
    }
  }
  return row[b.length]
}

function suggestions(values: string[], query: string, max = 8) {
  const value = query.trim().toLowerCase()
  if (!value) return values.slice(0, max)
  return values
    .map((item) => {
      const lower = item.toLowerCase()
      const starts = lower.startsWith(value)
      const contains = lower.includes(value)
      const distance = value.length >= 3 ? editDistance(lower, value) : 99
      const fuzzy = distance <= Math.max(1, Math.floor(value.length / 4))
      return { item, eligible: starts || contains || fuzzy || value.length < 3, score: starts ? 0 : contains ? 1 : fuzzy ? 2 + distance : 10 }
    })
    .filter(({ eligible }) => eligible)
    .sort((a, b) => a.score - b.score || a.item.localeCompare(b.item))
    .slice(0, max)
    .map(({ item }) => item)
}

export default function LeadHunterPage() {
  const [form, setForm] = useState({ keyword: 'Restaurant', city: 'Lahore', limit: '20' })
  const [items, setItems] = useState<Lead[]>([])
  const [meta, setMeta] = useState<Omit<SearchResponse, 'items' | 'count' | 'excluded_existing'> | null>(null)
  const [contactEnrichment, setContactEnrichment] = useState({ tomtom: false, website: true, google: false })
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [loading, setLoading] = useState(false)
  const [importing, setImporting] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [progress, setProgress] = useState(0)
  const [keywordOpen, setKeywordOpen] = useState(false)
  const [cityOpen, setCityOpen] = useState(false)

  const nicheSuggestions = useMemo(() => suggestions(niches, form.keyword), [form.keyword])
  const citySuggestions = useMemo(() => suggestions(cities, form.city, 10), [form.city])

  useEffect(() => {
    api<ProviderResponse>('/leads/providers')
      .then((data) => { if (data.contact_enrichment) setContactEnrichment(data.contact_enrichment) })
      .catch(() => undefined)
  }, [])

  useEffect(() => {
    if (!loading) return
    setProgress(8)
    const timer = window.setInterval(() => {
      setProgress((current) => Math.min(92, current + (current < 40 ? 7 : current < 70 ? 4 : 2)))
    }, 650)
    return () => window.clearInterval(timer)
  }, [loading])

  async function search(event: FormEvent) {
    event.preventDefault()
    const requestedLimit = Number(form.limit)
    if (!Number.isInteger(requestedLimit) || requestedLimit < 1 || requestedLimit > 100) {
      return toast.error('Enter a lead count from 1 to 100')
    }
    setLoading(true)
    setSelected(new Set())
    setMeta(null)
    setSearchError(null)
    try {
      const result = await api<SearchResponse>('/leads/search', {
        method: 'POST',
        body: JSON.stringify({ keyword: form.keyword.trim(), city: form.city.trim(), limit: requestedLimit }),
      })
      setProgress(100)
      setItems(result.items)
      setMeta({
        provider: result.provider,
        cached: result.cached,
        attribution: result.attribution,
        warnings: result.warnings || [],
        pages_scanned: result.pages_scanned,
        resolved_city: result.resolved_city,
        resolved_province: result.resolved_province,
        city_corrected: result.city_corrected,
        requested_count: result.requested_count,
        source_exhausted: result.source_exhausted,
      })
      if (result.city_corrected && result.resolved_city) {
        setForm((current) => ({ ...current, city: result.resolved_city || current.city }))
        toast.success(`City corrected to ${result.resolved_city}`)
      }
      if (result.items.length) {
        toast.success(result.excluded_existing
          ? `${result.items.length} new matching leads · ${result.excluded_existing} qualified leads skipped`
          : `${result.items.length} matching leads found`)
      } else {
        toast('No additional matching leads were found')
      }
    } catch (error) {
      setItems([])
      setSearchError(error instanceof Error ? error.message : 'Live search is temporarily unavailable. Please retry.')
    } finally {
      window.setTimeout(() => {
        setLoading(false)
        setProgress(0)
      }, 220)
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
        <form className="hunter-form hunter-form-clean" onSubmit={search} aria-busy={loading}>
          <label className="suggest-field">Business / niche
            <input
              value={form.keyword}
              onFocus={() => setKeywordOpen(true)}
              onBlur={() => window.setTimeout(() => setKeywordOpen(false), 120)}
              onChange={(event) => { setForm({ ...form, keyword: event.target.value }); setKeywordOpen(true) }}
              autoComplete="off"
              placeholder="e.g. Gym, Restaurant, Dental Clinic"
              required
            />
            {keywordOpen && nicheSuggestions.length > 0 && (
              <div className="suggest-menu">
                {nicheSuggestions.map((item) => <button type="button" key={item} onMouseDown={(event) => event.preventDefault()} onClick={() => { setForm({ ...form, keyword: item }); setKeywordOpen(false) }}>{item}</button>)}
              </div>
            )}
          </label>

          <label className="suggest-field">City
            <div className="input-with-icon plain city-input-wrap"><MapPin size={17} /><input
              className="city-entry"
              value={form.city}
              onFocus={() => setCityOpen(true)}
              onBlur={() => window.setTimeout(() => setCityOpen(false), 120)}
              onChange={(event) => { setForm({ ...form, city: event.target.value }); setCityOpen(true) }}
              autoComplete="off"
              placeholder="Type any Pakistan city"
              required
            /></div>
            {cityOpen && citySuggestions.length > 0 && (
              <div className="suggest-menu city-suggest-menu">
                {citySuggestions.map((item) => <button type="button" key={item} onMouseDown={(event) => event.preventDefault()} onClick={() => { setForm({ ...form, city: item }); setCityOpen(false) }}><MapPin size={13} />{item}</button>)}
              </div>
            )}
          </label>

          <label>Leads needed<input className="limit-entry" type="number" inputMode="numeric" min="1" max="100" step="1" placeholder="e.g. 30" value={form.limit} onChange={(event) => setForm({ ...form, limit: event.target.value })} required /></label>
          <button className="button primary hunter-search-button" disabled={loading}><Search size={17} />{loading ? 'Finding leads…' : 'Search leads'}</button>
        </form>

        {loading && (
          <div className="lead-search-progress" role="status" aria-live="polite">
            <div className="lead-progress-row"><strong>Lead search in progress</strong><span>{progress}%</span></div>
            <div className="lead-progress-track"><span style={{ width: `${progress}%` }} /></div>
            <small>{progress < 30 ? 'Checking city and business category…' : progress < 70 ? 'Searching live business sources…' : 'Verifying matches and public contact details…'}</small>
          </div>
        )}

        <div className="source-note"><Cloud size={15} />Automatic Geoapify/OpenStreetMap discovery · {contactEnrichment.tomtom ? 'TomTom Places + official website contact enrichment' : 'official website contact enrichment'}</div>
        {meta && <div className="source-meta"><strong>{meta.provider.replaceAll('+', ' + ')}</strong><span>{meta.cached ? 'Cached source page' : 'Live source'}</span>{meta.resolved_city && <span>{meta.resolved_city}{meta.resolved_province ? `, ${meta.resolved_province}` : ''}</span>}{meta.pages_scanned ? <span>{meta.pages_scanned} page{meta.pages_scanned === 1 ? '' : 's'} scanned</span> : null}</div>}
        {meta?.warnings.filter((warning) => !warning.toLowerCase().includes('another configured source')).map((warning) => <div className="provider-notice" key={warning}><AlertTriangle size={14} />{warning}</div>)}
        {meta?.source_exhausted && items.length > 0 && meta.requested_count && items.length < meta.requested_count && (
          <div className="provider-info"><CheckCircle2 size={14} /><span>{items.length} verified matching businesses were available from the connected live sources for this search. The system did not fill the remaining slots with unrelated businesses.</span></div>
        )}
        {searchError && <div className="search-error-panel" role="alert"><AlertTriangle size={19} /><div><strong>Live search could not complete</strong><span>{searchError}</span></div><button type="button" className="button secondary compact" onClick={() => setSearchError(null)}>Dismiss</button></div>}
      </section>

      <section className="card">
        <div className="card-header">
          <div><span className="eyebrow">Results</span><h2>{items.length ? `${items.length} matching businesses` : 'Search results'}</h2></div>
          <button className="button secondary" onClick={importSelected} disabled={!selected.size || importing}>{importing ? 'Importing…' : `Import selected (${selected.size})`}</button>
        </div>
        {!items.length ? <EmptyState title={loading ? 'Searching live businesses…' : 'Run a business search'} /> : (
          <div className="table-wrap">
            <table className="hunter-results-table">
              <thead><tr><th><input type="checkbox" checked={selected.size === items.length} onChange={() => setSelected(selected.size === items.length ? new Set() : new Set(items.map((_, index) => index)))} /></th><th>Business</th><th>Contact</th><th>Website</th><th>Score</th><th>Service</th></tr></thead>
              <tbody>{items.map((lead, index) => (
                <tr key={`${lead.business_name}-${lead.source_url || index}`}>
                  <td><input type="checkbox" checked={selected.has(index)} onChange={() => toggle(index)} /></td>
                  <td>
                    <div className="business-identity">
                      <div className="business-name-line"><strong>{lead.business_name}</strong>{branchMeta(items, index) && <em>Location {branchMeta(items, index)?.position}/{branchMeta(items, index)?.total}</em>}</div>
                      <span>{lead.category} · {lead.city}</span>
                      {lead.address && <small>{lead.address}</small>}
                    </div>
                  </td>
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
                        <a href={googleMapsVerificationUrl(lead)} target="_blank" rel="noreferrer" title="Verify this business on Google Maps"><MapPinned size={13} /><span>Verify Maps</span><ExternalLink size={11} /></a>
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
