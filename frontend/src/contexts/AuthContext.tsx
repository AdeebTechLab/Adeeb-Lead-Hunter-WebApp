import { createContext, ReactNode, useContext, useEffect, useState } from 'react'
import { api } from '../api'
import type { User } from '../types'

type AuthResponse = { access_token: string; user: User }

type AuthContextValue = {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  signup: (form: FormData) => Promise<void>
  refreshUser: () => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const onUnauthorized = () => setUser(null)
    window.addEventListener('leadHunterUnauthorized', onUnauthorized)
    return () => window.removeEventListener('leadHunterUnauthorized', onUnauthorized)
  }, [])

  useEffect(() => {
    const token = localStorage.getItem('leadHunterToken')
    if (!token) {
      setLoading(false)
      return
    }
    api<User>('/auth/me')
      .then(setUser)
      .catch(() => localStorage.removeItem('leadHunterToken'))
      .finally(() => setLoading(false))
  }, [])

  async function storeAuth(result: AuthResponse) {
    localStorage.setItem('leadHunterToken', result.access_token)
    setUser(result.user)
  }

  async function login(email: string, password: string) {
    const result = await api<AuthResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
    await storeAuth(result)
  }

  async function signup(form: FormData) {
    const result = await api<AuthResponse>('/auth/signup', { method: 'POST', body: form })
    await storeAuth(result)
  }

  async function refreshUser() {
    const current = await api<User>('/auth/me')
    setUser(current)
  }

  function logout() {
    localStorage.removeItem('leadHunterToken')
    setUser(null)
  }

  return <AuthContext.Provider value={{ user, loading, login, signup, refreshUser, logout }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
