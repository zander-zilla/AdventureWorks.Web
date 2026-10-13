import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { api, money, type ProductSummary } from '../api/client'
import { Button, DataTable, EmptyState, PageHeader, StatusPill, type Column } from '../components'

const cols: Column<ProductSummary>[] = [
  { key: 'number', header: 'Number', value: p => p.productNumber, render: p => <span className="font-mono text-xs">{p.productNumber}</span> },
  { key: 'name', header: 'Name', value: p => p.name, render: p => <Link className="hover:text-accent" to={`/shop/products/${p.id}`}>{p.name}</Link> },
  { key: 'price', header: 'List price', value: p => p.listPrice, render: p => money.format(p.listPrice), align: 'right' },
  { key: 'state', header: 'State', value: p => (p.active ? 'Active' : 'Discontinued'), render: p => <StatusPill label={p.active ? 'Active' : 'Discontinued'} tone={p.active ? 'ok' : 'neutral'} /> },
]

/** Proof screen for C2-0: product list over GET /api/v2/products (CAT-06), paged with the DynamoDB cursor. */
export function Products() {
  const [rows, setRows] = useState<ProductSummary[]>([])
  const [next, setNext] = useState<string | null>(null)
  const [state, setState] = useState<'loading' | 'ok' | 'error'>('loading')
  const fetchPage = (cursor?: string | null) =>
    api.products(cursor, 50).then(p => { setRows(r => (cursor ? [...r, ...p.items] : p.items)); setNext(p.next); setState('ok') }).catch(() => setState('error'))
  const load = (cursor?: string | null) => { setState('loading'); fetchPage(cursor) }
  useEffect(() => { fetchPage() }, [])
  return (
    <>
      <PageHeader title="Products" sub="CAT-06 · aw-catalog, paged by the DynamoDB cursor" />
      {state === 'error' ? <EmptyState title="Could not load products" action={<Button onClick={() => load()}>Retry</Button>}>The API did not answer. Is the app running?</EmptyState>
        : <DataTable caption="Products" rows={rows} columns={cols} rowKey={p => String(p.id)} empty={state === 'loading' ? 'Loading…' : 'No products'} />}
      {next && <div className="mt-4"><Button variant="secondary" onClick={() => load(next)}>Load more</Button></div>}
    </>
  )
}
