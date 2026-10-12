import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import type { ThemeName } from './tokens'

const KEY = 'aw.theme'
type Ctx = { theme: ThemeName; setTheme: (t: ThemeName) => void; toggle: () => void }
const ThemeCtx = createContext<Ctx | null>(null)

function initial(fallback: ThemeName): ThemeName {
  try { const s = localStorage.getItem(KEY); if (s === 'dark' || s === 'light') return s } catch { /* private mode */ }
  return fallback
}

export function ThemeProvider({ children, fallback = 'dark' }: { children: ReactNode; fallback?: ThemeName }) {
  const [theme, setThemeState] = useState<ThemeName>(() => initial(fallback))
  useEffect(() => { document.documentElement.dataset.theme = theme }, [theme])
  const setTheme = useCallback((t: ThemeName) => {
    setThemeState(t)
    try { localStorage.setItem(KEY, t) } catch { /* ignore */ }
  }, [])
  const toggle = useCallback(() => setTheme(theme === 'dark' ? 'light' : 'dark'), [theme, setTheme])
  return <ThemeCtx.Provider value={{ theme, setTheme, toggle }}>{children}</ThemeCtx.Provider>
}

export function useTheme() {
  const c = useContext(ThemeCtx)
  if (!c) throw new Error('useTheme outside ThemeProvider')
  return c
}
