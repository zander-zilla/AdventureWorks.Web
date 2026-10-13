import { useCallback, useEffect, useState } from 'react'

/** Load data once (and on demand via reload); exposes loading / error state for EmptyState screens. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T>()
  const [error, setError] = useState<Error>()
  const [loading, setLoading] = useState(true)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fn, deps)
  const reload = useCallback(() => {
    setLoading(true)
    return run().then(d => { setData(d); setError(undefined) }).catch(e => setError(e as Error)).finally(() => setLoading(false))
  }, [run])
  useEffect(() => { void reload() }, [reload])
  return { data, error, loading, reload, setData }
}
