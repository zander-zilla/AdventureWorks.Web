import { Link, useParams } from 'react-router'
import { api, money, type Order } from '../../api/client'
import { useLoad } from '../../api/useLoad'
import { DataTable, EmptyState, PageHeader, StatusPill, Timeline, orderStatus, type Column } from '../../components'

export const statusPill = (s: number) => { const [l, t] = orderStatus[s] ?? [String(s), 'neutral' as const]; return <StatusPill label={l} tone={t} /> }
const cols: Column<Order>[] = [
  { key: 'n', header: 'Order', value: o => o.number, render: o => <Link className="font-mono text-xs hover:text-accent" to={`/shop/orders/${o.id}`} data-testid="order-link">{o.number}</Link> },
  { key: 'd', header: 'Date', value: o => o.orderDate.slice(0, 10) },
  { key: 's', header: 'Status', value: o => o.status, render: o => statusPill(o.status) },
  { key: 't', header: 'Total', value: o => o.totalDue, render: o => money.format(o.totalDue), align: 'right' },
]

/** SAL-03 my orders (GSI1 CUSTOMER#, newest first). */
export function MyOrders() {
  const { data, error } = useLoad(() => api.myOrders())
  return (
    <>
      <PageHeader title="My orders" sub="SAL-03 · aw-sales GSI1" />
      {error ? <EmptyState title="Sign in to see your orders" /> : <DataTable caption="My orders" rows={data?.items ?? []} columns={cols} rowKey={o => String(o.id)} empty="No orders yet" />}
    </>
  )
}

/** SAL-04 order with lines and its status history (EVENT# items). */
export function MyOrder() {
  const id = Number(useParams().id)
  const { data: o, error } = useLoad(() => api.myOrder(id), [id])
  if (error) return <EmptyState title="Order not found" />
  if (!o) return <p className="text-mute">Loading…</p>
  return (
    <>
      <PageHeader title={o.number} sub={`Placed ${o.orderDate.replace('T', ' ')} UTC`} actions={<span data-testid="order-status">{statusPill(o.status)}</span>} />
      <OrderBody o={o} />
    </>
  )
}

export function OrderBody({ o }: { o: Order }) {
  return (
    <div className="grid grid-cols-3 gap-5">
      <div className="col-span-2 flex flex-col gap-3">
        <DataTable caption="Order lines" rows={o.lines} rowKey={l => String(l.lineNo)} columns={[
          { key: 'p', header: 'Product', value: l => l.name },
          { key: 'q', header: 'Qty', value: l => l.quantity, align: 'right' },
          { key: 'u', header: 'Unit', value: l => l.unitPrice, render: l => money.format(l.unitPrice), align: 'right' },
          { key: 'd', header: 'Discount', value: l => l.unitPriceDiscount, render: l => (l.unitPriceDiscount > 0 ? `${Math.round(l.unitPriceDiscount * 100)}% (offer ${l.specialOfferId})` : '—') },
          { key: 't', header: 'Line total', value: l => l.lineTotal, render: l => money.format(l.lineTotal), align: 'right' },
        ]} />
        <dl className="ml-auto grid w-72 grid-cols-2 gap-y-1 text-sm">
          <dt className="text-mute">Subtotal</dt><dd className="text-right">{money.format(o.subTotal)}</dd>
          <dt className="text-mute">Tax</dt><dd className="text-right">{money.format(o.taxAmt)}</dd>
          <dt className="text-mute">Freight ({o.shipMethodName})</dt><dd className="text-right">{money.format(o.freight)}</dd>
          <dt className="font-semibold">Total</dt><dd className="text-right font-semibold">{money.format(o.totalDue)}</dd>
        </dl>
      </div>
      <aside className="rounded-aw border border-line bg-panel p-4" aria-label="Status history">
        <div className="mb-2 text-xs text-mute">Ship to: {o.shipTo ?? '—'}</div>
        {o.carrierTrackingNumber && <div className="mb-3 text-sm">Tracking: <b data-testid="tracking">{o.carrierTrackingNumber}</b></div>}
        <Timeline items={o.events.map(e => ({ title: `${e.action} → ${orderStatus[e.toStatus]?.[0] ?? e.toStatus}`, when: e.at.replace('T', ' ').slice(0, 16), detail: [e.actor, e.note].filter(Boolean).join(' · '),
          tone: e.toStatus === 5 ? 'ok' : e.toStatus === 3 ? 'warn' : e.toStatus >= 4 ? 'danger' : 'info' }))} />
        {o.events.length === 0 && <p className="text-sm text-mute">No history recorded (migrated order).</p>}
      </aside>
    </div>
  )
}
