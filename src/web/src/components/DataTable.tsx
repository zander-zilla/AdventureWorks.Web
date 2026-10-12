import { useMemo, useState, type ReactNode } from 'react'
import { cx } from './cx'

export type Column<T> = { key: string; header: string; value: (row: T) => string | number; render?: (row: T) => ReactNode; align?: 'left' | 'right'; sortable?: boolean }

export function sortRows<T>(rows: T[], col: Column<T> | undefined, dir: 'asc' | 'desc') {
  if (!col) return rows
  const m = dir === 'asc' ? 1 : -1
  return [...rows].sort((a, b) => { const x = col.value(a), y = col.value(b); return (x < y ? -1 : x > y ? 1 : 0) * m })
}
export function filterRows<T>(rows: T[], cols: Column<T>[], q: string) {
  const s = q.trim().toLowerCase()
  return s ? rows.filter(r => cols.some(c => String(c.value(r)).toLowerCase().includes(s))) : rows
}

/** Sort (click header), filter (search box), multi-select (checkboxes) – the back-office workhorse. */
export function DataTable<T>({ rows, columns, rowKey, selectable, onSelectionChange, actions, empty = 'No rows', caption }: {
  rows: T[]; columns: Column<T>[]; rowKey: (r: T) => string; selectable?: boolean; onSelectionChange?: (keys: string[]) => void
  actions?: (selected: string[]) => ReactNode; empty?: ReactNode; caption?: string
}) {
  const [q, setQ] = useState('')
  const [sort, setSort] = useState<{ key: string; dir: 'asc' | 'desc' } | null>(null)
  const [sel, setSel] = useState<string[]>([])
  const view = useMemo(() => sortRows(filterRows(rows, columns, q), columns.find(c => c.key === sort?.key), sort?.dir ?? 'asc'), [rows, columns, q, sort])
  const update = (next: string[]) => { setSel(next); onSelectionChange?.(next) }
  const all = view.length > 0 && view.every(r => sel.includes(rowKey(r)))
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <input aria-label="Filter rows" placeholder="Filter…" value={q} onChange={e => setQ(e.target.value)}
          className="w-64 rounded-aw border border-line bg-bg px-3 py-1.5 text-sm placeholder:text-mute focus:border-accent focus:outline-none" />
        {selectable && <span className="text-xs text-mute" data-testid="selected-count">{sel.length} selected</span>}
        <div className="ml-auto flex gap-2">{actions?.(sel)}</div>
      </div>
      <div className="overflow-x-auto rounded-aw border border-line bg-panel">
        <table className="w-full border-collapse text-sm">
          {caption && <caption className="sr-only">{caption}</caption>}
          <thead>
            <tr className="border-b border-line">
              {selectable && <th className="w-10 px-3 py-2.5"><input type="checkbox" aria-label="Select all" checked={all}
                onChange={() => update(all ? [] : view.map(rowKey))} className="accent-[var(--aw-accent)]" /></th>}
              {columns.map(c => {
                const active = sort?.key === c.key
                return (
                  <th key={c.key} scope="col" aria-sort={active ? (sort!.dir === 'asc' ? 'ascending' : 'descending') : undefined}
                    className={cx('px-3.5 py-2.5 text-xs font-medium tracking-wider text-mute uppercase', c.align === 'right' ? 'text-right' : 'text-left')}>
                    {c.sortable === false ? c.header : (
                      <button type="button" className="uppercase hover:text-ink" onClick={() => setSort({ key: c.key, dir: active && sort!.dir === 'asc' ? 'desc' : 'asc' })}>
                        {c.header}{active ? (sort!.dir === 'asc' ? ' ↑' : ' ↓') : ''}
                      </button>)}
                  </th>)
              })}
            </tr>
          </thead>
          <tbody>
            {view.length === 0 && <tr><td colSpan={columns.length + (selectable ? 1 : 0)} className="px-3.5 py-8 text-center text-mute">{empty}</td></tr>}
            {view.map(r => {
              const k = rowKey(r), on = sel.includes(k)
              return (
                <tr key={k} className={cx('border-b border-line last:border-0', on && 'bg-raised')}>
                  {selectable && <td className="px-3 py-2.5"><input type="checkbox" aria-label={`Select ${k}`} checked={on}
                    onChange={() => update(on ? sel.filter(x => x !== k) : [...sel, k])} className="accent-[var(--aw-accent)]" /></td>}
                  {columns.map(c => <td key={c.key} className={cx('px-3.5 py-2.5', c.align === 'right' && 'text-right tabular-nums')}>{c.render ? c.render(r) : c.value(r)}</td>)}
                </tr>)
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
