import { Link, useParams } from 'react-router'
import { api, money } from '../../api/client'
import { useLoad } from '../../api/useLoad'
import { EmptyState, PageHeader } from '../../components'

/** CAT-03: active products of a subcategory (SUBCAT GSI, name order). */
export function Subcategory() {
  const id = Number(useParams().id)
  const { data, error, loading } = useLoad(() => api.subcategoryProducts(id), [id])
  const name = data?.[0]?.subcategoryName ?? 'Products'
  return (
    <>
      <PageHeader title={name} sub="CAT-03 · aw-catalog GSI1 SUBCAT#" />
      {error ? <EmptyState title="Could not load products" /> : loading ? <p className="text-mute">Loading…</p> : (
        <div className="grid grid-cols-4 gap-3.5">
          {(data ?? []).map(p => (
            <Link key={p.id} to={`/shop/products/${p.id}`} className="rounded-aw border border-line bg-panel p-4 hover:border-accent" data-testid="product-card">
              <div className="text-sm text-mute">{p.productNumber}</div>
              <div className="font-semibold">{p.name}</div>
              <div className="mt-2">{money.format(p.listPrice)}</div>
            </Link>))}
        </div>)}
    </>
  )
}
