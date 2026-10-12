import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { cx } from './cx'

type Kind = 'info' | 'ok' | 'error'
type T = { id: number; kind: Kind; text: string }
const Ctx = createContext<(text: string, kind?: Kind) => void>(() => {})
let seq = 0

export function ToastProvider({ children, ttl = 4000 }: { children: ReactNode; ttl?: number }) {
  const [items, setItems] = useState<T[]>([])
  const push = useCallback((text: string, kind: Kind = 'info') => {
    const id = ++seq
    setItems(x => [...x, { id, kind, text }])
    setTimeout(() => setItems(x => x.filter(t => t.id !== id)), ttl)
  }, [ttl])
  return (
    <Ctx.Provider value={push}>
      {children}
      <div className="fixed right-4 bottom-4 z-50 flex flex-col gap-2" aria-live="polite">
        {items.map(t => (
          <div key={t.id} role="status" className={cx('rounded-aw border bg-panel px-4 py-3 text-sm shadow-lg',
            t.kind === 'ok' ? 'border-ok' : t.kind === 'error' ? 'border-danger' : 'border-accent')}>{t.text}</div>
        ))}
      </div>
    </Ctx.Provider>
  )
}
export const useToast = () => useContext(Ctx)
