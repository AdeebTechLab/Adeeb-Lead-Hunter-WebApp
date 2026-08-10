export type UserRole = 'admin' | 'manager' | 'salesperson'

export interface User {
  id: string
  name: string
  email: string
  role: UserRole
  cnic: string
  city: string
  profile_image_url?: string | null
  active: boolean
  created_at: string
}

export interface ScoreProfile {
  band: string
  label: string
  meaning: string
  action: string
}

export interface ScoreBreakdown extends ScoreProfile {
  total: number
  opportunity_signal: number
  contactability: number
  engagement_signal: number
}

export interface Lead {
  id?: string
  business_name: string
  category: string
  city: string
  province: string
  phone?: string | null
  email?: string | null
  website?: string | null
  google_business_url?: string | null
  google_place_id?: string | null
  facebook?: string | null
  instagram?: string | null
  linkedin?: string | null
  address?: string | null
  latitude?: number | null
  longitude?: number | null
  source: string
  source_url?: string | null
  reviews_count: number
  rating?: number | null
  tags: string[]
  contact_sources?: string[]
  contact_confidence?: string | null
  contact_status?: string | null
  contact_search_url?: string | null
  contact_discovery?: Record<string, unknown>
  lead_score: number
  priority: 'Hot' | 'Warm' | 'Cold'
  recommended_service: string
  score_reasons: string[]
  score_profile?: ScoreProfile
  score_breakdown?: ScoreBreakdown
  business_summary: string
  audit?: Record<string, unknown>
  outreach?: Record<string, string>
  status?: 'Not Contacted' | 'Contacted' | 'Follow-up' | 'Closed'
  notes?: string
  follow_up_date?: string | null
  last_contact_date?: string | null
  assigned_salesperson?: string
  call_status?: string
  proposal_status?: string
  deal_status?: string
  meeting_notes?: string
  created_at?: string
  updated_at?: string
  competitor_insights?: Lead[]
}

export interface NotificationItem {
  id: string
  title: string
  message: string
  kind: string
  link: string
  read: boolean
  created_at: string
}

export interface ProviderOption {
  id: 'auto' | 'google' | 'geoapify' | 'osm'
  name: string
  configured: boolean
  description: string
}
