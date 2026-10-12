import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, type Me } from './client'

type Ctx = { me: Me | null; loading: boolean; login: (e: string, p: string) => Promise<void>; logout: () => Promise<void> }
const AuthCtx = createContext<Ctx>({ me: null, loading: true, login: async () => {}, logout: async () => {} })

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => { api.me().then(setMe).catch(() => setMe({ authenticated: false, roles: [] })).finally(() => setLoading(false)) }, [])
  const login = useCallback(async (e: string, p: string) => setMe(await api.login(e, p)), [])
  const logout = useCallback(async () => { await api.logout(); setMe({ authenticated: false, roles: [] }) }, [])
  return <AuthCtx.Provider value={{ me, loading, login, logout }}>{children}</AuthCtx.Provider>
}
export const useAuth = () => useContext(AuthCtx)
