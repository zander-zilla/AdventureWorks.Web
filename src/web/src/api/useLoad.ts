import { useEffect, useState } from 'react'

/** Load data when deps change (and on demand via reload); exposes loading / error for EmptyState screens. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const key = JSON.stringify(deps)
  const [s, set] = useState<{ key?: string; data?: T; error?: Error }>({})
  useEffect(() => {
    let live = true
    fn().then(d => { if (live) set({ key, data: d }) }, (e: Error) => { if (live) set(p => ({ key, data: p.data, error: e })) })
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  const reload = () => fn().then(d => set({ key, data: d }), (e: Error) => set(p => ({ ...p, error: e })))
  const setData = (d: T) => set(p => ({ ...p, data: d }))
  return { data: s.data, error: s.error, loading: s.key !== key, reload, setData }
}
