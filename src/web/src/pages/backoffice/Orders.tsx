import { useState } from 'react'
import { api, ApiError, money, type BackOfficeOrder, type Order } from '../../api/client'
import { useLoad } from '../../api/useLoad'
import { AssistBox, plain } from '../ai/AssistPanel'
import type { AssistResult } from '../../api/client'
import { Button, DataTable, Drawer, EmptyState, KpiCard, PageHeader, SelectField, TextField, useToast, type Column } from '../../components'
import { OrderBody, statusPill } from '../shop/MyOrders'

type Op = 'approve' | 'reject' | 'backorder' | 'ship' | 'cancel'
const label: Record<Op, string> = { approve: 'Approve', reject: 'Reject', backorder: 'Backorder', ship: 'Ship…', cancel: 'Cancel order' }

/** Back office order fulfilment (C2-2): SAL-05 queue by status (sparse ORDERSTATUS GSI), detail with stock (INV-01),
 *  approve / reject / backorder / cancel (SAL-06) and ship = one TransactWriteItems (status + stock + TransactionHistory). */
export function BackOfficeOrders() {
  const [status, setStatus] = useState(1)
  const [territory, setTerritory] = useState('')
  const counts = useLoad(() => api.queueCounts())
  const queue = useLoad(() => api.queue(status, territory ? Number(territory) : undefined), [status, territory])
  const [open, setOpen] = useState<number>()
  const toast = useToast()
  const refresh = () => { void queue.reload(); void counts.reload() }
  const cols: Column<Order>[] = [
    { key: 'n', header: 'Order', value: o => o.number, render: o => <button type="button" className="font-mono text-xs text-accent hover:underline" onClick={() => setOpen(o.id)} data-testid="open-order">{o.number}</button> },
    { key: 'c', header: 'Customer', value: o => o.customerName ?? String(o.customerId) },
    { key: 'd', header: 'Date', value: o => o.orderDate.slice(0, 16).replace('T', ' ') },
    { key: 'terr', header: 'Territory', value: o => o.territoryId ?? '—' },
    { key: 's', header: 'Status', value: o => o.status, render: o => statusPill(o.status) },
    { key: 't', header: 'Total', value: o => o.totalDue, render: o => money.format(o.totalDue), align: 'right' },
  ]
  const bulk = async (keys: string[]) => {
    const rows = (queue.data?.items ?? []).filter(o => keys.includes(String(o.id)))
    const res = await api.bulkApprove(rows.map(o => ({ id: o.id, version: o.version })))
    const okN = res.filter(r => r.ok).length
    toast(`${okN} approved${res.length > okN ? `, ${res.length - okN} skipped` : ''}`, okN ? 'ok' : 'error'); refresh()
  }
  const c = (s: number) => counts.data?.find(x => x.status === s)?.count ?? 0
  return (
    <>
      <PageHeader title="Order fulfilment" sub="Approve → ship. Ship = one TransactWriteItems: status + stock + TransactionHistory (INV-03); CDC and zero-ETL carry it to Redshift." />
      <div className="mb-5 grid grid-cols-3 gap-3.5" role="tablist" aria-label="Order status">
        {[1, 2, 3].map(s => (
          <button key={s} type="button" role="tab" aria-selected={status === s} onClick={() => setStatus(s)} className={status === s ? 'rounded-aw ring-2 ring-accent' : ''} data-testid={`status-tab-${s}`}>
            <KpiCard label={['', 'In process (to approve)', 'Approved (to ship)', 'Backordered'][s]} value={String(c(s))} delta="SAL-05 · ORDERSTATUS GSI" />
          </button>))}
      </div>
      <div className="mb-3 w-64">
        <SelectField label="Territory (filter on SAL-05, no SAL-14 index)" value={territory} onChange={e => setTerritory(e.target.value)}
          options={[{ value: '', label: 'All territories' }, ...[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(t => ({ value: String(t), label: `Territory ${t}` }))]} />
      </div>
      {queue.error ? <EmptyState title="Could not load the queue" action={<Button onClick={refresh}>Retry</Button>}>{queue.error.message}</EmptyState> : (
        <DataTable caption="Order queue" rows={queue.data?.items ?? []} columns={cols} rowKey={o => String(o.id)} selectable={status === 1}
          empty={queue.loading ? 'Loading…' : 'No orders in this status'}
          actions={sel => status === 1 && <Button size="sm" disabled={sel.length === 0} onClick={() => bulk(sel)} data-testid="bulk-approve">Approve selected</Button>} />)}
      {open && <OrderDrawer id={open} onClose={() => setOpen(undefined)} onChanged={refresh} />}
    </>
  )
}

function OrderDrawer({ id, onClose, onChanged }: { id: number; onClose: () => void; onChanged: () => void }) {
  const d = useLoad(() => api.boOrder(id), [id])
  const methods = useLoad(() => api.shipMethods())
  const [shipping, setShipping] = useState(false)
  const [method, setMethod] = useState('5')
  const [tracking, setTracking] = useState('')
  const [busy, setBusy] = useState(false)
  const ai = useLoad(() => api.aiStatus(), [])
  const [assist, setAssist] = useState<AssistResult | null>(null)
  const [note, setNote] = useState('')
  const toast = useToast()
  const ask = async (kind: 'explain' | 'approve-note' | 'backorder-note') => {
    setBusy(true)
    try { const r = await api.triageAssist(id, kind); setAssist(r); if (kind !== 'explain' && r.text) setNote(plain(r.text)) }
    catch (e) { toast(e instanceof ApiError ? e.message : 'Copilot failed', 'error') } finally { setBusy(false) }
  }
  const run = async (op: Op) => {
    if (!d.data) return
    if (op === 'ship' && !shipping) { setShipping(true); return }
    setBusy(true)
    try {
      const r = await api.transition(id, op, d.data.order.version, op === 'ship' ? { shipMethodId: Number(method), trackingNumber: tracking } : undefined, op === 'ship' ? undefined : note.trim())
      toast(r.outcome === 'shipped' ? `${r.order.number} shipped` : r.outcome === 'backordered' ? `${r.order.number} backordered: ${r.shortages.join('; ')}` : `${r.order.number}: ${r.outcome}`,
        r.outcome === 'shipped' || r.outcome === op ? 'ok' : 'error')
      setShipping(false); setNote(''); setAssist(null); await d.reload(); onChanged()
    } catch (e) { toast(e instanceof ApiError ? e.message : 'Action failed', 'error') } finally { setBusy(false) }
  }
  const b: BackOfficeOrder | undefined = d.data
  return (
    <Drawer open wide title={b ? `Order ${b.order.number}` : 'Order'} onClose={onClose}
      footer={b && <>{(b.actions as Op[]).map(op => (
        <Button key={op} size="sm" variant={op === 'cancel' || op === 'reject' ? 'danger' : op === 'ship' || op === 'approve' ? 'primary' : 'secondary'}
          disabled={busy || (op === 'ship' && shipping && !tracking.trim())} onClick={() => run(op)} data-testid={`action-${op}`}>{op === 'ship' && shipping ? 'Confirm ship' : label[op]}</Button>))}</>}>
      {!b ? <p className="text-mute">Loading…</p> : (
        <div className="flex flex-col gap-4 text-sm">
          <div className="flex items-center gap-3">{statusPill(b.order.status)}<span className="text-mute">v{b.order.version} · rev {b.order.revisionNumber} · {b.order.customerName}</span></div>
          {shipping && (
            <div className="flex flex-col gap-3 rounded-aw border border-accent p-3" aria-label="Ship">
              <SelectField label="Ship method" value={method} onChange={e => setMethod(e.target.value)} options={(methods.data ?? []).map(m => ({ value: String(m.id), label: m.name }))} />
              <TextField label="Tracking number" value={tracking} maxLength={25} onChange={e => setTracking(e.target.value)} placeholder="e.g. 1Z999AA10123456784" />
            </div>)}
          {ai.data?.enabled && b.actions.length > 0 && (
            <AssistBox title="Triage copilot" r={assist}>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="secondary" disabled={busy} onClick={() => ask('explain')} data-testid="triage-explain">Explain</Button>
                {b.actions.includes('approve') && <Button size="sm" variant="secondary" disabled={busy} onClick={() => ask('approve-note')} data-testid="triage-approve-note">Draft approve note</Button>}
                {b.actions.includes('backorder') && <Button size="sm" variant="secondary" disabled={busy} onClick={() => ask('backorder-note')} data-testid="triage-backorder-note">Draft backorder note</Button>}
              </div>
            </AssistBox>)}
          {b.actions.length > 0 && b.actions.some(a => a !== 'ship') && (
            <label className="flex flex-col gap-1 text-xs text-mute">Note for the order history (optional, goes with approve / backorder / reject / cancel)
              <textarea className="rounded-aw border border-line bg-bg p-2 text-sm text-ink" rows={3} maxLength={500} value={note} onChange={e => setNote(e.target.value)} data-testid="order-note" />
            </label>)}
          <div>
            <div className="mb-1 text-xs text-mute uppercase">Stock (INV-01)</div>
            <ul className="flex flex-col gap-1" data-testid="stock">
              {b.stock.map(s => {
                const need = (b.order.lines ?? []).filter(l => l.productId === s.productId).reduce((a, l) => a + l.quantity, 0)
                const best = Math.max(0, ...s.locations.map(l => l.quantity))
                return <li key={s.productId} className={best >= need ? '' : 'text-warn'}>Product {s.productId}: need {need}, on hand {s.onHand} (best location {best}){s.onHand - need < s.reorderPoint ? ' · will drop below reorder point' : ''}</li>
              })}
            </ul>
          </div>
          <OrderBody o={b.order} compact />
        </div>)}
    </Drawer>
  )
}
