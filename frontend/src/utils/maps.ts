import type { Lead } from '../types'

function isGoogleMapsUrl(value?: string | null) {
  if (!value) return false
  try {
    const url = new URL(value)
    const host = url.hostname.toLowerCase()
    return host === 'maps.google.com' || host === 'maps.app.goo.gl' || (host.endsWith('google.com') && url.pathname.startsWith('/maps'))
  } catch {
    return false
  }
}

/**
 * Always returns a Google Maps URL. Older stored leads can contain an
 * OpenStreetMap source URL, so the UI never reuses source_url as a Maps link.
 */
export function googleMapsVerificationUrl(lead: Lead) {
  if (isGoogleMapsUrl(lead.google_business_url)) return lead.google_business_url as string

  const name = (lead.business_name || '').trim()
  const address = (lead.address || '').trim()
  const city = (lead.city || '').trim()
  const province = (lead.province || '').trim()

  // A named Google Maps search with the full address is the best no-Place-ID
  // path to the business detail card. Coordinates remain a fallback only when
  // the provider did not publish enough address identity.
  const query = address
    ? `${name}, ${address}`
    : name
      ? [name, city, province, 'Pakistan'].filter(Boolean).join(', ')
      : (lead.latitude != null && lead.longitude != null)
        ? `${lead.latitude},${lead.longitude}`
        : [city, province, 'Pakistan'].filter(Boolean).join(', ')

  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`
}
