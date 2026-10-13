import { useState, type FormEvent } from 'react'
import { useNavigate, useParams } from 'react-router'
import { api, ApiError, hasRole, money } from '../../api/client'
import { useAuth } from '../../api/auth'
import { useLoad } from '../../api/useLoad'
import { Button, DataTable, EmptyState, PageHeader, SelectField, StatusPill, TextField, useToast } from '../../components'

const day = (s?: string | null) => (s ? s.slice(0, 10) : '—')
const stars = (n: number) => '★★★★★'.slice(0, n) + '☆☆☆☆☆'.slice(0, 5 - n)

/** Product detail: offers (CAT-10), add to cart (SAL-01), reviews (CAT-11) and, for catalog admins, the price edit
 *  that now writes ListPriceHistory (CAT-07 fix). */
export function ProductPage() {
  const id = Number(useParams().id)
  const { me } = useAuth()
  const nav = useNavigate()
  const toast = useToast()
  const detail = useLoad(() => api.product(id), [id])
  const reviews = useLoad(() => api.reviews(id), [id])
  const [qty, setQty] = useState(1)
  if (detail.error) return <EmptyState title="Product not found" />
  if (!detail.data) return <p className="text-mute">Loading…</p>
  const { product: p, offers, priceHistory } = detail.data
  const add = async () => {
    if (!me?.customerId) { nav('/login'); return }
    try { await api.addToCart(p.id, qty); toast(`Added ${qty} × ${p.name} to your cart`, 'ok') }
    catch (e) { toast(e instanceof ApiError ? e.message : 'Could not add to cart', 'error') }
  }
  const live = offers.filter(o => o.id !== 1 && o.discountPct > 0)
  return (
    <>
      <PageHeader title={p.name} sub={`${p.productNumber} · ${p.categoryName ?? ''} / ${p.subcategoryName ?? ''}`} />
      <div className="grid grid-cols-3 gap-5">
        <section className="col-span-2 flex flex-col gap-4 rounded-aw border border-line bg-panel p-5">
          <div className="flex items-baseline gap-4">
            <span className="font-display text-3xl font-bold" data-testid="list-price">{money.format(p.listPrice)}</span>
            {p.active ? <StatusPill label={p.stockQty > 0 ? `In stock (${p.stockQty})` : 'Out of stock'} tone={p.stockQty > 0 ? 'ok' : 'warn'} /> : <StatusPill label="Discontinued" />}
          </div>
          <dl className="grid grid-cols-3 gap-2 text-sm">
            <dt className="text-mute">Color</dt><dd className="col-span-2">{p.color ?? '—'}</dd>
            <dt className="text-mute">Size</dt><dd className="col-span-2">{p.size ?? '—'}</dd>
            <dt className="text-mute">Weight</dt><dd className="col-span-2">{p.weight ? `${p.weight} ${p.weightUnit ?? ''}` : '—'}</dd>
          </dl>
          {p.active && (
            <div className="flex items-end gap-3">
              <TextField label="Quantity" type="number" min={1} max={99} value={qty} onChange={e => setQty(Math.max(1, Math.min(99, Number(e.target.value) || 1)))} className="w-24" />
              <Button onClick={add} data-testid="add-to-cart">Add to cart</Button>
            </div>)}
        </section>
        <aside className="rounded-aw border border-line bg-panel p-5" aria-label="Offers">
          <h2 className="mb-2 font-semibold">Offers (CAT-10)</h2>
          {live.length === 0 ? <p className="text-sm text-mute">No special offers on this product.</p> : (
            <ul className="flex flex-col gap-2 text-sm" data-testid="offers">
              {live.map(o => <li key={o.id}><b>{Math.round(o.discountPct * 100)}%</b> {o.description}
                <span className="text-mute"> · qty {o.minQty}{o.maxQty ? `–${o.maxQty}` : '+'} · until {day(o.end)}</span></li>)}
            </ul>)}
          <p className="mt-3 text-xs text-mute">Applied automatically at checkout (best offer per line).</p>
        </aside>
      </div>

      {hasRole(me, 'CatalogAdmin') && <PriceEditor id={p.id} price={p.listPrice} version={p.version} history={priceHistory} onSaved={() => detail.reload()} />}

      <section id="reviews" className="mt-6" aria-labelledby="reviews-h">
        <h2 id="reviews-h" className="mb-3 font-display text-xl font-semibold">Reviews</h2>
        <div className="grid grid-cols-3 gap-5">
          <ul className="col-span-2 flex flex-col gap-3" data-testid="reviews">
            {(reviews.data ?? []).length === 0 && <li className="text-mute">No reviews yet.</li>}
            {(reviews.data ?? []).map(r => (
              <li key={r.id} className="rounded-aw border border-line bg-panel p-4" data-testid="review">
                <div className="flex gap-3 text-sm"><span className="text-accent2" aria-label={`${r.rating} of 5`}>{stars(r.rating)}</span>
                  <b>{r.reviewerName}</b><span className="text-mute">{day(r.date)}</span></div>
                <p className="mt-1">{r.comments}</p>
              </li>))}
          </ul>
          {me?.customerId ? <ReviewForm id={id} onDone={() => reviews.reload()} /> : <p className="text-sm text-mute">Sign in as a customer to write a review.</p>}
        </div>
      </section>
    </>
  )
}

function ReviewForm({ id, onDone }: { id: number; onDone: () => void }) {
  const [rating, setRating] = useState('5')
  const [text, setText] = useState('')
  const [error, setError] = useState<string>()
  const toast = useToast()
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setError(undefined)
    try { await api.addReview(id, Number(rating), text); setText(''); toast('Thanks for your review', 'ok'); onDone() }
    catch (x) { setError(x instanceof ApiError ? x.message : 'Could not save the review') }
  }
  return (
    <form onSubmit={submit} className="flex flex-col gap-3 rounded-aw border border-line bg-panel p-4" aria-label="Write a review">
      <SelectField label="Rating" value={rating} onChange={e => setRating(e.target.value)} options={[5, 4, 3, 2, 1].map(n => ({ value: String(n), label: stars(n) }))} />
      <label className="flex flex-col gap-1 text-sm"><span>Your review</span>
        <textarea value={text} onChange={e => setText(e.target.value)} rows={4} maxLength={3850} required minLength={10}
          className="rounded-aw border border-line bg-bg px-3 py-2" aria-label="Your review" /></label>
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      <Button type="submit">Submit review</Button>
      <p className="text-xs text-mute">One review per customer and product · 10–3850 characters.</p>
    </form>
  )
}

type PricePoint = { startDate: string; endDate?: string | null; listPrice: number; source: string }
function PriceEditor({ id, price, version, history, onSaved }: { id: number; price: number; version: number; history: PricePoint[]; onSaved: () => void }) {
  const [value, setValue] = useState(String(price))
  const toast = useToast()
  const save = async () => {
    try { await api.setPrice(id, Number(value), version); toast('Price saved and history written (CAT-07)', 'ok'); onSaved() }
    catch (e) { toast(e instanceof ApiError ? e.message : 'Could not save', 'error') }
  }
  return (
    <section className="mt-6 rounded-aw border border-line bg-panel p-5" aria-label="Price (catalog admin)">
      <h2 className="mb-3 font-semibold">List price · catalog admin (CAT-07)</h2>
      <div className="mb-4 flex items-end gap-3">
        <TextField label="New list price" type="number" step="0.01" min={0} value={value} onChange={e => setValue(e.target.value)} className="w-40" />
        <Button onClick={save} data-testid="save-price">Save price</Button>
      </div>
      <DataTable caption="Price history" rows={[...history].reverse()} rowKey={h => h.startDate}
        columns={[
          { key: 's', header: 'Start', value: h => day(h.startDate) },
          { key: 'e', header: 'End', value: h => day(h.endDate) },
          { key: 'p', header: 'List price', value: h => h.listPrice, render: h => money.format(h.listPrice), align: 'right' },
          { key: 'src', header: 'Written by', value: h => (h.source === 'ddb' ? 'app (C2-2)' : 'SQL migration') },
        ]} />
    </section>
  )
}
