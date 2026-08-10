import { createContext, ReactNode, useContext, useEffect, useState } from 'react'

type Theme = 'light' | 'dark'
const ThemeContext = createContext<{ theme: Theme; toggle: () => void } | null>(null)

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => (localStorage.getItem('leadHunterTheme') as Theme) || 'light')
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('leadHunterTheme', theme)
  }, [theme])
  return <ThemeContext.Provider value={{ theme, toggle: () => setTheme((value) => (value === 'light' ? 'dark' : 'light')) }}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const value = useContext(ThemeContext)
  if (!value) throw new Error('useTheme must be used inside ThemeProvider')
  return value
}
