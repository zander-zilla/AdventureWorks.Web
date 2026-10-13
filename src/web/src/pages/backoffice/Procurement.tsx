import { useMemo, useState } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { NavLink, Route, Routes } from 'react-router'
import { useAuth } from '../../api/auth'
import { AssistBox, plain } from '../ai/AssistPanel'
import { cssVar } from '../../theme/tokens'
import { api, ApiError, hasRole, money, type AssistResult, type SmartSuggestion, type PurchaseOrder, type PurchaseOrderSummary, type ReorderSuggestion, type VendorProduct, type VendorSummary } from '../../api/client'
import { useLoad } from '../../api/useLoad'
import { Button, DataTable, Drawer, EmptyState, KpiCard, PageHeader, SelectField, StatusPill, Timeline, useToast, type Column, type Tone } from '../../components'

// C2-3 procurement workspace (style B): reorder suggestions (INV-02 + PUR-02) -> purchase order (PUR-04) -> approve /
// reject (PurchasingManager) -> receive into stock (one transaction: PO lines + INV + TransactionHistory P) and vendors
// (PUR-01/03/05 + performance). Historical (SQL-era) POs are shown read-only.

const poTone: Record<number, Tone> = { 1: 'info', 2: 'accent', 3: 'danger', 4: 'ok' }
export const poPill = (s: number, text?: string | null) => <StatusPill label={text ?? ['', 'Pending', 'Approved', 'Rejected', 'Complete'][s] ?? String(s)} tone={poTone[s] ?? 'neutral'} />
const pct = (x?: number | null) => (x == null ? '—' : `${(x * 100).toFixed(1)}%`)
const compact = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', notation: 'compact', maximumFractionDigits: 1 })
const day = (s?: string | null) => (s ? s.slice(0, 10) : '—')

function Tabs() {
  const tab = (to: string, label: string, end = false) => (
    <NavLink to={to} end={end} className={({ isActive }) => `rounded-aw px-3 py-1.5 text-sm ${isActive ? 'bg-accent text-accent-ink' : 'text-mute hover:text-ink'}`}>{label}</NavLink>)
  return (
    <nav className="mb-5 flex gap-2" aria-label="Procurement">
      {tab('/back-office/procurement', 'Reorder suggestions', true)}{tab('/back-office/procurement/orders', 'Purchase orders')}{tab('/back-office/procurement/vendors', 'Vendors')}
    </nav>)
}

export function Procurement() {
  return (
    <>
      <PageHeader title="Procurement" sub="Low stock → suggested PO → approve → receive into inventory. aw-purchasing had no UI in Chapter 1: zero schema change." />
      <Tabs />
      <Routes>
        <Route index element={<Suggestions />} />
        <Route path="orders" element={<PurchaseOrders />} />
        <Route path="vendors" element={<Vendors />} />
      </Routes>
    </>
  )
}

// ---------------------------------------------------------------- suggestions

type Draft = Record<number, { qty: number; on: boolean }>

function Suggestions() {
  const s = useLoad(() => api.suggestions())
  const methods = useLoad(() => api.shipMethods())
  const ai = useLoad(() => api.aiStatus(), [])
  const smart = useLoad(async () => (ai.data?.enabled ? await api.smartSuggestions() : []), [ai.data?.enabled])
  const smartBy = useMemo(() => new Map((smart.data ?? []).map(x => [x.rule.productId, x])), [smart.data])
  const [why, setWhy] = useState<number>()
  const [draft, setDraft] = useState<Draft>({})
  const [busy, setBusy] = useState<number>()
  const [created, setCreated] = useState<number>()
  const toast = useToast()
  const rows = useMemo(() => s.data ?? [], [s.data])
  const groups = useMemo(() => {
    const m = new Map<number, { vendor: VendorProduct; items: ReorderSuggestion[] }>()
    for (const r of rows) if (r.vendor && r.suggestedQty > 0) {
      const g = m.get(r.vendor.vendorId) ?? { vendor: r.vendor, items: [] }; g.items.push(r); m.set(r.vendor.vendorId, g)
    }
    return [...m.values()].sort((a, b) => a.vendor.vendorName.localeCompare(b.vendor.vendorName))
  }, [rows])
  const other = rows.filter(r => !r.vendor || r.suggestedQty === 0)
  const line = (r: ReorderSuggestion) => draft[r.productId] ?? { qty: r.suggestedQty, on: true }
  const set = (id: number, v: Partial<{ qty: number; on: boolean }>, r: ReorderSuggestion) => setDraft(d => ({ ...d, [id]: { ...line(r), ...v } }))
  const create = async (vendorId: number, items: ReorderSuggestion[], shipMethodId: number) => {
    const lines = items.filter(r => line(r).on && line(r).qty > 0).map(r => ({ productId: r.productId, quantity: line(r).qty }))
    if (lines.length === 0) { toast('Select at least one line', 'error'); return }
    setBusy(vendorId)
    try {
      const po = await api.createPo(vendorId, shipMethodId, lines.slice(0, 15))
      toast(`${po.number} created (Pending approval)`, 'ok'); setCreated(po.id); void s.reload()
    } catch (e) { toast(e instanceof ApiError ? e.message : 'Create failed', 'error') } finally { setBusy(undefined) }
  }
  if (s.error) return <EmptyState title="Could not load suggestions" action={<Button onClick={() => void s.reload()}>Retry</Button>}>{s.error.message}</EmptyState>
  return (
    <>
      <div className="mb-5 grid grid-cols-4 gap-3.5">
        <KpiCard label="Below reorder point" value={s.loading ? '…' : String(rows.length)} delta="INV-02 · sparse REORDER index" />
        <KpiCard label="Purchasable (vendor found)" value={String(rows.filter(r => r.vendor).length)} delta="PUR-02 · GSI1 PRODUCT#" />
        <KpiCard label="Suggested POs (by vendor)" value={String(groups.length)} />
        <KpiCard label="Made in house" value={String(rows.filter(r => r.vendors.length === 0).length)} delta="production floor · C2-4" />
      </div>
      {s.loading && <p className="text-mute">Loading…</p>}
      {ai.data?.enabled && smartBy.size > 0 && (
        <div className="mb-4 flex items-center gap-3 rounded-aw border border-accent/60 bg-panel px-4 py-3 text-sm" data-testid="smart-bar">
          <span className="text-xs uppercase text-mute">✦ Smart reorder</span>
          <span className="text-mute">Forecast column = safety stock + forecast demand over the vendor lead time − on hand − on order (INV-07). The reorder rule stays the default.</span>
          <Button size="sm" className="ml-auto" data-testid="use-forecast" onClick={() => setDraft(d => {
            const n = { ...d }; for (const x of smartBy.values()) if (x.smartQty > 0) n[x.rule.productId] = { qty: x.smartQty, on: true }; return n })}>Use forecast quantities</Button>
        </div>)}
      {why !== undefined && smartBy.get(why) && <SmartWhy s={smartBy.get(why)!} onClose={() => setWhy(undefined)} />}
      <div className="flex flex-col gap-4" data-testid="suggestions">
        {groups.map(g => <VendorGroup key={g.vendor.vendorId} g={g} line={line} set={set} busy={busy === g.vendor.vendorId} smart={smartBy} onWhy={setWhy}
          methods={methods.data ?? []} onCreate={(m) => create(g.vendor.vendorId, g.items, m)} />)}
        {!s.loading && groups.length === 0 && <EmptyState title="Nothing to order">Every product below its reorder point is covered by open purchase orders.</EmptyState>}
      </div>
      {other.length > 0 && (
        <details className="mt-6 rounded-aw border border-line bg-panel p-4">
          <summary className="cursor-pointer text-sm text-mute">{other.length} more below reorder point: made in house or covered by open POs</summary>
          <ul className="mt-2 grid grid-cols-2 gap-1 text-xs text-mute">{other.map(r => <li key={r.productId}>{r.name} · on hand {r.stockQty} / ROP {r.reorderPoint} · {r.note}</li>)}</ul>
        </details>)}
      {created && <PoDrawer id={created} onClose={() => setCreated(undefined)} onChanged={() => void s.reload()} />}
    </>
  )
}

function SmartWhy({ s, onClose }: { s: SmartSuggestion; onClose: () => void }) {
  const [r, setR] = useState<AssistResult | null>(null)
  const [busy, setBusy] = useState(false)
  const f = s.forecast
  const data = [...f.history.slice(-24).map(h => ({ month: h.month, actual: h.qty, forecast: null as number | null })),
    ...f.next.map(n => ({ month: n.month, actual: null as number | null, forecast: n.qty }))]
  return (
    <section className="mb-4 rounded-aw border border-line bg-panel p-4" aria-label={`Forecast for ${s.rule.name}`} data-testid="smart-why">
      <header className="mb-2 flex items-center gap-3"><b>{s.rule.name}</b>
        <span className="text-xs text-mute">{f.method} · monthly {f.monthly} · 12-month baseline {f.baseline} · growth ×{f.growth} · lead time {f.leadTimeDays} d → {f.leadTimeDemand} units</span>
        <Button size="sm" variant="ghost" className="ml-auto" onClick={onClose}>Close</Button></header>
      <div className="h-48" data-testid="forecast-chart">
        <ResponsiveContainer><LineChart data={data}><CartesianGrid strokeDasharray="3 3" stroke={cssVar('line')} /><XAxis dataKey="month" tick={{ fontSize: 10 }} /><YAxis tick={{ fontSize: 10 }} /><Tooltip />
          <Line dataKey="actual" name="units sold" stroke={cssVar('accent')} dot={false} isAnimationActive={false} />
          <Line dataKey="forecast" name="forecast" stroke={cssVar('warn')} strokeDasharray="4 3" isAnimationActive={false} /></LineChart></ResponsiveContainer>
      </div>
      <AssistBox title="Why this quantity" r={r}>
        <div className="flex gap-2"><Button size="sm" variant="ghost" disabled={busy} data-testid="explain-reorder"
          onClick={async () => { setBusy(true); try { setR(await api.explainReorder(s.rule.productId)) } finally { setBusy(false) } }}>Explain</Button>
          <span className="self-center text-xs text-mute">Rule {s.rule.suggestedQty} · forecast {s.smartQty} · {s.reason}</span></div>
      </AssistBox>
    </section>)
}

function VendorGroup({ g, line, set, busy, methods, onCreate, smart, onWhy }: {
  smart: Map<number, SmartSuggestion>; onWhy: (id: number) => void
  g: { vendor: VendorProduct; items: ReorderSuggestion[] }; line: (r: ReorderSuggestion) => { qty: number; on: boolean }
  set: (id: number, v: Partial<{ qty: number; on: boolean }>, r: ReorderSuggestion) => void; busy: boolean
  methods: { id: number; name: string }[]; onCreate: (shipMethodId: number) => void
}) {
  const [method, setMethod] = useState('3')
  const total = g.items.filter(r => line(r).on).reduce((a, r) => a + line(r).qty * (r.vendor?.standardPrice ?? 0), 0)
  return (
    <section className="rounded-aw border border-line bg-panel" data-testid="vendor-group" aria-label={`Suggested PO for ${g.vendor.vendorName}`}>
      <header className="flex items-center gap-3 border-b border-line px-4 py-3">
        <b>{g.vendor.vendorName}</b>
        {g.vendor.preferred && <StatusPill label="Preferred" tone="ok" />}
        <span className="text-xs text-mute">vendor {g.vendor.vendorId} · lead time {g.vendor.averageLeadTime} d</span>
        <span className="ml-auto font-mono text-sm" data-testid="group-total">{money.format(total)}</span>
        <div className="w-52"><SelectField label="Ship method" value={method} onChange={e => setMethod(e.target.value)}
          options={methods.length ? methods.map(m => ({ value: String(m.id), label: m.name })) : [{ value: '3', label: 'OVERSEAS - DELUXE' }]} /></div>
        <Button size="sm" disabled={busy} onClick={() => onCreate(Number(method))} data-testid="create-po">Create PO</Button>
      </header>
      <table className="w-full text-sm">
        <thead><tr className="text-left text-xs text-mute"><th className="w-8 px-4 py-2" /><th>Product</th><th className="text-right">On hand</th><th className="text-right">Reorder pt</th>
          <th className="text-right">Safety stock</th><th className="text-right">On order</th><th className="text-right">Unit price</th>{smart.size > 0 && <th className="text-right">Forecast</th>}<th className="w-28 px-4 text-right">Qty</th><th className="px-4">Note</th></tr></thead>
        <tbody>
          {g.items.map(r => (
            <tr key={r.productId} className="border-t border-line" data-testid="suggestion">
              <td className="px-4 py-2"><input type="checkbox" aria-label={`Include ${r.name}`} checked={line(r).on} onChange={e => set(r.productId, { on: e.target.checked }, r)} /></td>
              <td>{r.name} <span className="font-mono text-xs text-mute">{r.productNumber}</span>{r.vendors.length > 1 && <span className="text-xs text-mute"> · {r.vendors.length} vendors</span>}</td>
              <td className="text-right text-warn">{r.stockQty}</td><td className="text-right">{r.reorderPoint}</td><td className="text-right">{r.safetyStockLevel}</td>
              <td className="text-right">{r.onOrder}</td><td className="text-right">{money.format(r.vendor?.standardPrice ?? 0)}</td>
              {smart.size > 0 && <td className="text-right">{smart.get(r.productId) ? <button type="button" className="font-mono text-accent underline-offset-2 hover:underline" data-testid="smart-qty"
                title={smart.get(r.productId)!.reason} onClick={() => onWhy(r.productId)}>{smart.get(r.productId)!.smartQty}</button> : '—'}</td>}
              <td className="px-4 text-right"><input aria-label={`Quantity for ${r.name}`} type="number" min={1} value={line(r).qty}
                onChange={e => set(r.productId, { qty: Math.max(0, Number(e.target.value)) }, r)} className="w-20 rounded-aw border border-line bg-bg px-2 py-1 text-right" /></td>
              <td className="px-4 text-xs text-mute">{r.note}</td>
            </tr>))}
        </tbody>
      </table>
    </section>)
}

// ---------------------------------------------------------------- purchase orders

function PurchaseOrders() {
  const [tab, setTab] = useState<'1' | '2' | 'mine'>('1')
  const counts = useLoad(() => api.poCounts())
  const list = useLoad(() => (tab === 'mine' ? api.myPos() : api.pos(Number(tab))), [tab])
  const [open, setOpen] = useState<number>()
  const c = (s: number) => counts.data?.find(x => x.status === s)?.count ?? 0
  const refresh = () => { void list.reload(); void counts.reload() }
  const cols: Column<PurchaseOrderSummary>[] = [
    { key: 'n', header: 'PO', value: o => o.number, render: o => <button type="button" className="font-mono text-xs text-accent hover:underline" onClick={() => setOpen(o.id)} data-testid="open-po">{o.number}</button> },
    { key: 'v', header: 'Vendor', value: o => o.vendorName ?? String(o.vendorId) },
    { key: 'd', header: 'Order date', value: o => o.orderDate.slice(0, 16).replace('T', ' ') },
    { key: 'b', header: 'Buyer', value: o => o.employeeName ?? (o.employeeId ? `Employee ${o.employeeId}` : '—') },
    { key: 's', header: 'Status', value: o => o.status, render: o => poPill(o.status, o.statusText) },
    { key: 'src', header: 'Origin', value: o => o.source, render: o => <StatusPill label={o.source === 'ddb' ? 'app (C2-3)' : 'SQL-era, read-only'} tone={o.source === 'ddb' ? 'accent' : 'neutral'} /> },
    { key: 't', header: 'Total', value: o => o.totalDue, render: o => money.format(o.totalDue), align: 'right' },
  ]
  return (
    <>
      <div className="mb-5 grid grid-cols-3 gap-3.5" role="tablist" aria-label="Purchase order status">
        {([['1', 'Pending (to approve)', String(c(1)), 'PUR-07 · POSTATUS#1'], ['2', 'Approved (to receive)', String(c(2)), 'PUR-07 · POSTATUS#2'], ['mine', 'My purchase orders', '·', 'PUR-06 · GSI2 EMPLOYEE#']] as const).map(([k, l, v, d]) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)} className={tab === k ? 'rounded-aw ring-2 ring-accent' : ''} data-testid={`po-tab-${k}`}>
            <KpiCard label={l} value={v} delta={d} />
          </button>))}
      </div>
      {list.error ? <EmptyState title="Could not load purchase orders" action={<Button onClick={refresh}>Retry</Button>}>{list.error.message}</EmptyState> : (
        <DataTable caption="Purchase orders" rows={list.data?.items ?? []} columns={cols} rowKey={o => String(o.id)} empty={list.loading ? 'Loading…' : 'No purchase orders'} />)}
      {open && <PoDrawer id={open} onClose={() => setOpen(undefined)} onChanged={refresh} />}
    </>
  )
}

type Rcv = Record<number, { rcv: string; rej: string; loc: string }>

export function PoDrawer({ id, onClose, onChanged }: { id: number; onClose: () => void; onChanged: () => void }) {
  const { me } = useAuth()
  const d = useLoad(() => api.po(id), [id])
  const locs = useLoad(() => api.locations())
  const [receiving, setReceiving] = useState(false)
  const [rcv, setRcv] = useState<Rcv>({})
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  const o: PurchaseOrder | undefined = d.data
  const manager = hasRole(me, 'PurchasingManager')
  const run = async (op: 'approve' | 'reject') => {
    if (!o) return
    setBusy(true)
    try { const r = await api.poTransition(id, op, o.version); toast(`${r.order.number} ${r.outcome}`, op === 'approve' ? 'ok' : 'error'); await d.reload(); onChanged() }
    catch (e) { toast(e instanceof ApiError ? e.message : 'Action failed', 'error') } finally { setBusy(false) }
  }
  const receive = async () => {
    if (!o) return
    if (!receiving) { setReceiving(true); return }
    const lines = (o.lines ?? []).map(l => ({ detailId: l.detailId, receivedQty: Number(rcv[l.detailId]?.rcv || 0), rejectedQty: Number(rcv[l.detailId]?.rej || 0),
      locationId: rcv[l.detailId]?.loc ? Number(rcv[l.detailId].loc) : null })).filter(l => l.receivedQty > 0)
    setBusy(true)
    try {
      const r = await api.receive(id, o.version, lines)
      toast(r.outcome === 'complete' ? `${r.order.number} received in full (Complete)` : `${r.order.number} partially received`, 'ok')
      setReceiving(false); setRcv({}); await d.reload(); onChanged()
    } catch (e) { toast(e instanceof ApiError ? e.message : 'Receipt failed', 'error') } finally { setBusy(false) }
  }
  const setLine = (detail: number, k: 'rcv' | 'rej' | 'loc', v: string) => setRcv(x => ({ ...x, [detail]: { ...{ rcv: '', rej: '', loc: '' }, ...x[detail], [k]: v } }))
  const actions = o?.actions ?? []
  const ai = useLoad(() => api.aiStatus(), [])
  const [mail, setMail] = useState<AssistResult | null>(null)
  const [mailText, setMailText] = useState('')
  const draftMail = async () => {
    setBusy(true)
    try { const r = await api.poEmailDraft(id); setMail(r); setMailText(plain(r.text)) } catch (e) { toast(e instanceof ApiError ? e.message : 'Draft failed', 'error') } finally { setBusy(false) }
  }
  const subject = mailText.match(/^Subject: (.*)$/m)?.[1] ?? `Purchase order ${o?.number ?? ''}`
  const bodyText = mailText.replace(/^Subject: .*\n+/, '')
  return (
    <Drawer open wide title={o ? `Purchase order ${o.number}` : 'Purchase order'} onClose={onClose}
      footer={o && <>
        {actions.includes('approve') && manager && <Button size="sm" disabled={busy} onClick={() => run('approve')} data-testid="po-approve">Approve</Button>}
        {actions.includes('reject') && manager && <Button size="sm" variant="danger" disabled={busy} onClick={() => run('reject')} data-testid="po-reject">Reject</Button>}
        {actions.includes('receive') && <Button size="sm" disabled={busy} onClick={receive} data-testid="po-receive">{receiving ? 'Confirm receipt' : 'Receive…'}</Button>}
        {actions.includes('approve') && !manager && <span className="text-xs text-mute">Waiting for a purchasing manager to approve.</span>}
      </>}>
      {!o ? <p className="text-mute">Loading…</p> : (
        <div className="flex flex-col gap-4 text-sm">
          <div className="flex flex-wrap items-center gap-3"><span data-testid="po-status">{poPill(o.status, o.statusText)}</span>
            <span className="text-mute">{o.vendorName} · v{o.version} · rev {o.revisionNumber} · {o.employeeName ?? '—'} · {o.shipMethodName}</span>
            {o.readOnly && <StatusPill label="SQL-era · read-only" tone="neutral" />}</div>
          <div className="grid grid-cols-4 gap-2 text-xs">
            <div><div className="text-mute">Ordered</div>{day(o.orderDate)}</div><div><div className="text-mute">Shipped / first receipt</div>{day(o.shipDate)}</div>
            <div><div className="text-mute">Subtotal · tax · freight</div>{money.format(o.subTotal)} · {money.format(o.taxAmt)} · {money.format(o.freight)}</div>
            <div><div className="text-mute">Total due</div><b>{money.format(o.totalDue)}</b></div>
          </div>
          <table className="w-full text-sm [&_td]:px-1.5 [&_th]:px-1.5 [&_th]:whitespace-nowrap" aria-label="PO lines">
            <thead><tr className="text-left text-xs text-mute"><th>Product</th><th className="text-right">Ordered</th><th className="text-right">Received</th><th className="text-right">Rejected</th>
              <th className="text-right">Stocked</th><th className="text-right">Unit</th>{!receiving && <th>Due</th>}{receiving && <><th>Receive</th><th>Reject</th><th>Location</th></>}</tr></thead>
            <tbody>
              {(o.lines ?? []).map(l => (
                <tr key={l.detailId} className="border-t border-line" data-testid="po-line">
                  <td className="py-1.5">{l.productName} <span className="text-xs text-mute">#{l.productId}</span></td>
                  <td className="text-right">{l.orderQty}</td><td className="text-right" data-testid="line-received">{l.receivedQty}</td><td className="text-right">{l.rejectedQty}</td>
                  <td className="text-right">{l.stockedQty}</td><td className="text-right">{money.format(l.unitPrice)}</td>{!receiving && <td className="text-xs whitespace-nowrap">{day(l.dueDate)}</td>}
                  {receiving && <>
                    <td><input aria-label={`Received for ${l.productName}`} type="number" min={0} max={l.orderQty - l.receivedQty} value={rcv[l.detailId]?.rcv ?? ''}
                      placeholder={String(l.orderQty - l.receivedQty)} onChange={e => setLine(l.detailId, 'rcv', e.target.value)} className="w-16 rounded-aw border border-line bg-bg px-1 py-0.5 text-right" /></td>
                    <td><input aria-label={`Rejected for ${l.productName}`} type="number" min={0} value={rcv[l.detailId]?.rej ?? ''} placeholder="0"
                      onChange={e => setLine(l.detailId, 'rej', e.target.value)} className="w-14 rounded-aw border border-line bg-bg px-1 py-0.5 text-right" /></td>
                    <td><select aria-label={`Location for ${l.productName}`} value={rcv[l.detailId]?.loc ?? ''} onChange={e => setLine(l.detailId, 'loc', e.target.value)}
                      className="rounded-aw border border-line bg-bg px-1 py-0.5 text-xs">
                      <option value="">largest stock</option>{(locs.data ?? []).map(x => <option key={x.locationId} value={x.locationId}>{x.name}</option>)}</select></td>
                  </>}
                </tr>))}
            </tbody>
          </table>
          {ai.data?.enabled && !o.readOnly && (
            <AssistBox title="Vendor e-mail draft" r={mail}>
              <div className="flex gap-2"><Button size="sm" variant="ghost" disabled={busy} onClick={draftMail} data-testid="po-email-draft">Draft e-mail to vendor</Button>
                <span className="self-center text-xs text-mute">Draft only: nothing is sent. Edit, then copy or open in your mail app.</span></div>
              {mail?.text && <>
                <textarea aria-label="E-mail draft" className="rounded-aw border border-line bg-bg p-2 font-mono text-xs text-ink" rows={10} value={mailText} onChange={e => setMailText(e.target.value)} data-testid="po-email-text" />
                <div className="flex gap-2"><Button size="sm" variant="ghost" onClick={() => { void navigator.clipboard?.writeText(mailText); toast('Copied', 'ok') }} data-testid="po-email-copy">Copy</Button>
                  <a className="rounded-aw border border-line px-3 py-1 text-sm" href={`mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(bodyText)}`} data-testid="po-email-mailto">Open in mail app</a></div>
              </>}
            </AssistBox>)}
          {receiving && <p className="text-xs text-mute">One transaction: PO lines (received / rejected / stocked) + stock per location (INV-01) + stock total and REORDER marker (INV-02) + TransactionHistory type P (INV-03).</p>}
          {(o.events ?? []).length > 0 && (
            <div><div className="mb-1 text-xs text-mute uppercase">History</div>
              <Timeline items={(o.events ?? []).map(e => ({ title: `${e.action} · ${['', 'Pending', 'Approved', 'Rejected', 'Complete'][e.toStatus]}`, when: e.at.replace('T', ' ').slice(0, 16),
                detail: `${e.actor}${e.note ? ' · ' + e.note : ''}`, tone: e.action === 'reject' ? 'danger' : e.toStatus === 4 ? 'ok' : 'info' }))} /></div>)}
        </div>)}
    </Drawer>
  )
}

// ---------------------------------------------------------------- vendors

function Vendors() {
  const list = useLoad(() => api.vendors())
  const [open, setOpen] = useState<number>()
  const cols: Column<VendorSummary>[] = [
    { key: 'n', header: 'Vendor', value: v => v.name, render: v => <button type="button" className="text-accent hover:underline" onClick={() => setOpen(v.id)} data-testid="open-vendor">{v.name}</button> },
    { key: 'a', header: 'Account', value: v => v.accountNumber ?? '' },
    { key: 'c', header: 'Credit rating', value: v => v.creditRating, align: 'right' },
    { key: 'p', header: 'Preferred', value: v => (v.preferred ? 'yes' : 'no'), render: v => (v.preferred ? <StatusPill label="Preferred" tone="ok" /> : <span className="text-mute">—</span>) },
    { key: 's', header: 'Active', value: v => (v.active ? 'active' : 'inactive'), render: v => <StatusPill label={v.active ? 'Active' : 'Inactive'} tone={v.active ? 'accent' : 'danger'} /> },
  ]
  return (
    <>
      {list.error ? <EmptyState title="Could not load vendors">{list.error.message}</EmptyState> :
        <DataTable caption="Vendors" rows={list.data ?? []} columns={cols} rowKey={v => String(v.id)} empty={list.loading ? 'Loading…' : 'No vendors'} />}
      {open && <VendorDrawer id={open} onClose={() => setOpen(undefined)} />}
    </>
  )
}

function VendorDrawer({ id, onClose }: { id: number; onClose: () => void }) {
  const d = useLoad(() => api.vendor(id), [id])
  const [po, setPo] = useState<number>()
  const v = d.data
  return (
    <Drawer open wide title={v ? `${v.vendor.name} · ${v.vendor.accountNumber ?? ''}` : 'Vendor'} onClose={onClose}>
      {!v ? <p className="text-mute">{d.error ? d.error.message : 'Loading…'}</p> : (
        <div className="flex flex-col gap-4 text-sm">
          <div className="grid grid-cols-4 gap-2" data-testid="vendor-performance">
            <KpiCard label="On time" value={pct(v.performance.onTimeRate)} delta={`${v.performance.orders} POs · ${v.performance.lines} lines`} />
            <KpiCard label="Reject rate" value={pct(v.performance.rejectRate)} delta={`${v.performance.rejected} of ${v.performance.received} received`} />
            <KpiCard label="Fill rate" value={pct(v.performance.fillRate)} delta={`avg lead ${v.performance.avgLeadDays ?? '—'} d`} />
            <KpiCard label="Spend" value={compact.format(v.performance.spend)} delta="approved + complete" />
          </div>
          <div className="grid grid-cols-2 gap-4 text-xs">
            <div><div className="mb-1 text-mute uppercase">Addresses (PUR-01)</div>{v.addresses.map((a, i) => <div key={i}>{a.type}: {a.line1}, {a.city} {a.state} {a.postalCode} {a.country}</div>)}</div>
            <div><div className="mb-1 text-mute uppercase">Contacts</div>{v.contacts.map((c, i) => <div key={i}>{c.name} · {c.type}</div>)}</div>
          </div>
          <div><div className="mb-1 text-xs text-mute uppercase">Supplies (PUR-03)</div>
            <table className="w-full text-xs [&_td]:px-1.5 [&_th]:px-1.5"><thead><tr className="text-left text-mute"><th>Product</th><th className="text-right">Std price</th><th className="text-right">Lead</th><th className="text-right">Min–max</th><th className="text-right">On order</th><th>Last receipt</th></tr></thead>
              <tbody>{v.products.map(p => <tr key={p.productId} className="border-t border-line"><td className="py-1">{p.productName}</td><td className="text-right">{money.format(p.standardPrice)}</td>
                <td className="text-right">{p.averageLeadTime} d</td><td className="text-right">{p.minOrderQty}–{p.maxOrderQty}</td><td className="text-right">{p.onOrderQty}</td><td>{day(p.lastReceiptDate)}</td></tr>)}</tbody></table></div>
          <div><div className="mb-1 text-xs text-mute uppercase">Purchase orders (PUR-05, newest first)</div>
            <ul className="flex flex-col gap-1" data-testid="vendor-pos">{v.orders.map(o => (
              <li key={o.id} className="flex items-center gap-3 text-xs"><button type="button" className="font-mono text-accent hover:underline" onClick={() => setPo(o.id)}>{o.number}</button>
                {poPill(o.status, o.statusText)}<span className="text-mute">{day(o.orderDate)}</span><span className="ml-auto">{money.format(o.totalDue)}</span></li>))}</ul></div>
        </div>)}
      {po && <PoDrawer id={po} onClose={() => setPo(undefined)} onChanged={() => void d.reload()} />}
    </Drawer>
  )
}
