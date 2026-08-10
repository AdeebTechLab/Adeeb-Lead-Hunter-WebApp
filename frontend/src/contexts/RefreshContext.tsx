import { createContext, ReactNode, useContext, useState } from 'react'

const RefreshContext = createContext<{ refreshKey: number; refresh: () => void } | null>(null)

export function RefreshProvider({ children }: { children: ReactNode }) {
  const [refreshKey, setRefreshKey] = useState(0)
  return <RefreshContext.Provider value={{ refreshKey, refresh: () => setRefreshKey((value) => value + 1) }}>{children}</RefreshContext.Provider>
}

export function useRefresh() {
  const value = useContext(RefreshContext)
  if (!value) throw new Error('useRefresh must be used inside RefreshProvider')
  return value
}
