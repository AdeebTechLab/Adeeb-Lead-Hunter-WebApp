const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000/api').replace(/\/+$/, '')

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

function clearExpiredSession() {
  localStorage.removeItem('leadHunterToken')
  window.dispatchEvent(new Event('leadHunterUnauthorized'))
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('leadHunterToken')
  const headers = new Headers(options.headers)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)

  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, { ...options, headers })
  } catch {
    throw new ApiError('Unable to reach the API. Check your connection and try again.', 0)
  }

  if (!response.ok) {
    let message = 'Request failed'
    try {
      const data = await response.json()
      message = typeof data.detail === 'string' ? data.detail : message
    } catch {
      message = response.statusText || message
    }
    if (response.status === 401) clearExpiredSession()
    throw new ApiError(message, response.status)
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export async function downloadFile(path: string, filename: string): Promise<void> {
  const token = localStorage.getItem('leadHunterToken')
  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  } catch {
    throw new ApiError('Unable to reach the API. Check your connection and try again.', 0)
  }
  if (!response.ok) {
    if (response.status === 401) clearExpiredSession()
    throw new ApiError('Export failed', response.status)
  }
  const blob = await response.blob()
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(link.href)
}
