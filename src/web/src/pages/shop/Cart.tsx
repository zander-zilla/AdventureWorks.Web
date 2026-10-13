import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { api, ApiError, money, type Quote } from '../../api/client'
import { useLoad } from '../../api/useLoad'
import { Button, EmptyState, PageHeader, SelectField, useToast } from '../../components'

/** Cart (SAL-01) + checkout (SAL-02) with the server-side quote: offers per line (CAT-10), tax by ship-to state/province
 *  (REF-02), freight by ship method (REF-04). The order is priced again on the server at checkout. */
export function Cart() {
  const cart = useLoad(() => api.cart())
  const methods = useLoad(() => api.shipMethods())
  const [method, setMethod] = useState<number>(1)
  const [quote, setQuote] = useState<Quote>()
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  const nav = useNavigate()
  const lines = cart.data ?? []
  useEffect(() => {
    if (lines.length === 0) { setQuote(undefined); return }
    api.quote(method).then(setQuote).catch(() => setQuote(undefined))
  }, [cart.data, method, lines.length])
  if (cart.error) return <EmptyState title="Sign in to see your cart" action={<Link to="/login"><Button>Sign in</Button></Link>} />
  const setQty = async (pid: number, q: number) => cart.setData(await api.setQuantity(pid, q))
  const place = async () => {
    setBusy(true)
    try { const o = await api.checkout(method); toast(`Order ${o.number} placed`, 'ok'); nav(`/shop/orders/${o.id}`) }
    catch (e) { toast(e instanceof ApiError ? e.message : 'Checkout failed', 'error') } finally { setBusy(false) }
  }
  return (
    <>
      <PageHeader title="Cart & checkout" sub="SAL-01 cart · SAL-02 checkout (one TransactWriteItems) · real pricing" />
      {cart.loading && !cart.data ? <p className="text-mute">Loading…</p> : lines.length === 0 ? (
        <EmptyState title="Your cart is empty" action={<Link to="/shop/products"><Button>Browse products</Button></Link>} />
      ) : (
        <div className="grid grid-cols-3 gap-5">
          <div className="col-span-2 overflow-x-auto rounded-aw border border-line bg-panel">
            <table className="w-full text-sm">
              <caption className="sr-only">Cart</caption>
              <thead><tr className="border-b border-line text-left text-xs text-mute uppercase">
                <th className="px-3.5 py-2.5">Product</th><th className="px-3.5 py-2.5">Qty</th><th className="px-3.5 py-2.5 text-right">Unit</th>
                <th className="px-3.5 py-2.5">Offer</th><th className="px-3.5 py-2.5 text-right">Line total</th></tr></thead>
              <tbody>
                {lines.map(l => {
                  const q = quote?.lines.find(x => x.productId === l.productId)
                  return (
                    <tr key={l.productId} className="border-b border-line last:border-0" data-testid="cart-line">
                      <td className="px-3.5 py-2.5"><Link to={`/shop/products/${l.productId}`} className="hover:text-accent">{l.name}</Link></td>
                      <td className="px-3.5 py-2.5"><input type="number" min={0} max={99} defaultValue={l.quantity} aria-label={`Quantity of ${l.name}`}
                        onBlur={e => Number(e.target.value) !== l.quantity && setQty(l.productId, Number(e.target.value))}
                        className="w-16 rounded-aw border border-line bg-bg px-2 py-1" /></td>
                      <td className="px-3.5 py-2.5 text-right">{money.format(l.unitPrice)}</td>
                      <td className="px-3.5 py-2.5 text-xs">{q && q.unitPriceDiscount > 0 ? <span className="text-ok" data-testid="line-offer">−{Math.round(q.unitPriceDiscount * 100)}% {q.offerDescription}</span> : <span className="text-mute">—</span>}</td>
                      <td className="px-3.5 py-2.5 text-right">{money.format(q?.lineTotal ?? l.lineTotal)}</td>
                    </tr>)
                })}
              </tbody>
            </table>
          </div>
          <aside className="flex flex-col gap-3 rounded-aw border border-line bg-panel p-5" aria-label="Order summary">
            <SelectField label="Ship method (REF-04)" value={String(method)} onChange={e => setMethod(Number(e.target.value))}
              options={(methods.data ?? []).map(m => ({ value: String(m.id), label: `${m.name} · ${money.format(m.shipBase)} + ${money.format(m.shipRate)}/lb` }))} />
            {quote && (
              <dl className="grid grid-cols-2 gap-y-1.5 text-sm" data-testid="quote">
                <dt className="text-mute">Subtotal</dt><dd className="text-right" data-testid="subtotal">{money.format(quote.subTotal)}</dd>
                {quote.discount > 0 && <><dt className="text-mute">Offers saved</dt><dd className="text-right text-ok">−{money.format(quote.discount)}</dd></>}
                <dt className="text-mute">Tax {quote.tax ? `(${quote.tax.stateCode} ${(quote.tax.rate * 100).toFixed(2)}%)` : '(none for ship-to)'}</dt>
                <dd className="text-right" data-testid="tax">{money.format(quote.taxAmt)}</dd>
                <dt className="text-mute">Freight ({quote.weightLb} lb)</dt><dd className="text-right" data-testid="freight">{money.format(quote.freight)}</dd>
                <dt className="font-semibold">Total</dt><dd className="text-right font-semibold" data-testid="total">{money.format(quote.totalDue)}</dd>
              </dl>)}
            <p className="text-xs text-mute">Offers evaluated on the AdventureWorks pricing date {quote?.offerDate}. Tax/freight are allocated to lines exactly as Redshift does.</p>
            <Button onClick={place} disabled={busy || !quote} data-testid="place-order">Place order</Button>
          </aside>
        </div>)}
    </>
  )
}
