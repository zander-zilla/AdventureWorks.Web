import { useMemo, useState } from 'react'
import { NavLink, Route, Routes } from 'react-router'
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis, BarChart } from 'recharts'
import { useAuth } from '../../api/auth'
import { api, ApiError, hasRole, type BomNode, type RoutingStep, type WorkOrderDetail, type WorkOrderSummary } from '../../api/client'
import { useLoad } from '../../api/useLoad'
import { Button, DataTable, Drawer, EmptyState, KpiCard, PageHeader, SelectField, StatusPill, TextField, Timeline, useToast, type Column, type Tone } from '../../components'
import { cssVar } from '../../theme/tokens'

// C2-4 production floor (style B): scrap and on-time KPIs (INV-06 by due month, Recharts), work orders with a routing
// Gantt (scheduled vs actual), create -> record operations -> complete with scrap (one transaction: work order + stock in
// + components out + TransactionHistory W), and the BOM explorer (INV-04 explosion as of a date, INV-05 where-used).

const pct = (x?: number | null) => (x == null ? '—' : `${(x * 100).toFixed(1)}%`)
const day = (s?: string | null) => (s ? s.slice(0, 10) : '—')
const stateTone: Record<string, Tone> = { Open: 'info', 'Closed on time': 'ok', 'Closed late': 'warn' }
export const woPill = (state: string) => <StatusPill label={state} tone={stateTone[state] ?? 'neutral'} />
const today = () => new Date().toISOString().slice(0, 10)

const ranges = [
  { id: 'sql12', label: 'Last 12 months of SQL-era data (2013-07 – 2014-06)', from: '2013-07', to: '2014-06' },
  { id: 'sql24', label: '24 months (2012-07 – 2014-06)', from: '2012-07', to: '2014-06' },
  { id: 'app', label: 'This year (app work orders)', from: `${new Date().getFullYear()}-01`, to: `${new Date().getFullYear()}-12` },
]

function Tabs() {
  const tab = (to: string, label: string, end = false) => (
    <NavLink to={to} end={end} className={({ isActive }) => `rounded-aw px-3 py-1.5 text-sm ${isActive ? 'bg-accent text-accent-ink' : 'text-mute hover:text-ink'}`}>{label}</NavLink>)
  return (
    <nav className="mb-5 flex gap-2" aria-label="Production">
      {tab('/back-office/production', 'Scrap & on-time', true)}{tab('/back-office/production/work-orders', 'Work orders')}{tab('/back-office/production/bom', 'BOM explorer')}
    </nav>)
}

export default function Production() {
  return (
    <>
      <PageHeader title="Production floor" sub="Work orders, routing, scrap and on-time – and the recursive bill of materials, answered from DynamoDB (INV-04/05/06)." />
      <Tabs />
      <Routes>
        <Route index element={<Dashboard />} />
        <Route path="work-orders" element={<WorkOrders />} />
        <Route path="bom" element={<BomExplorer />} />
      </Routes>
    </>
  )
}

// ---------------------------------------------------------------- dashboard

function Dashboard() {
  const [range, setRange] = useState(ranges[0].id)
  const r = ranges.find(x => x.id === range)!
  const k = useLoad(() => api.kpis(r.from, r.to), [r.from, r.to])
  const months = useMemo(() => (k.data?.months ?? []).map(m => ({ month: m.month, scrap: +(m.scrapRate * 100).toFixed(2), onTime: +(m.onTimeRate * 100).toFixed(1), wos: m.workOrders })), [k.data])
  const reasons = (k.data?.scrapReasons ?? []).slice(0, 8)
  const axis = { stroke: cssVar('mute'), fontSize: 11 }
  return (
    <>
      <div className="mb-4 max-w-md"><SelectField label="Period (by due month)" value={range} onChange={e => setRange(e.target.value)} options={ranges.map(x => ({ value: x.id, label: x.label }))} /></div>
      {k.error ? <EmptyState title="Could not load KPIs" action={<Button onClick={() => void k.reload()}>Retry</Button>}>{k.error.message}</EmptyState> : (
        <>
          <div className="mb-5 grid grid-cols-4 gap-3.5">
            <div data-testid="kpi-scrap"><KpiCard label="Scrap rate" value={k.data ? pct(k.data.scrapRate) : '…'} delta={k.data ? `${k.data.scrappedQty.toLocaleString()} of ${k.data.orderQty.toLocaleString()} units` : ''} trend="down" /></div>
            <div data-testid="kpi-ontime"><KpiCard label="On-time production" value={k.data ? pct(k.data.onTimeRate) : '…'} delta="closed with end ≤ due date" trend="up" /></div>
            <KpiCard label="Work orders" value={k.data ? k.data.workOrders.toLocaleString() : '…'} delta={`INV-06 · ${months.length} GSI2 WODUE# queries`} />
            <KpiCard label="Open" value={k.data ? String(k.data.open) : '…'} delta="no end date yet" />
          </div>
          <div className="grid grid-cols-3 gap-4">
            <figure className="col-span-2 rounded-aw border border-line bg-panel p-4" data-testid="scrap-chart">
              <figcaption className="mb-2 text-xs text-mute">Scrap rate (bars, %) and on-time (line, %) by due month</figcaption>
              <div style={{ height: 260 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={months} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
                    <CartesianGrid stroke={cssVar('line')} vertical={false} />
                    <XAxis dataKey="month" tick={axis} tickLine={false} />
                    <YAxis yAxisId="s" tick={axis} tickLine={false} unit="%" />
                    <YAxis yAxisId="o" orientation="right" tick={axis} tickLine={false} unit="%" domain={[0, 100]} />
                    <Tooltip contentStyle={{ background: cssVar('raised'), border: `1px solid ${cssVar('line')}`, fontSize: 12 }} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar yAxisId="s" dataKey="scrap" name="Scrap %" fill={cssVar('warn')} radius={[3, 3, 0, 0]} isAnimationActive={false} />
                    <Line yAxisId="o" dataKey="onTime" name="On-time %" stroke={cssVar('accent')} strokeWidth={2} dot={false} isAnimationActive={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </figure>
            <figure className="rounded-aw border border-line bg-panel p-4">
              <figcaption className="mb-2 text-xs text-mute">Top scrap reasons (units)</figcaption>
              <div style={{ height: 260 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={reasons} layout="vertical" margin={{ top: 0, right: 8, bottom: 0, left: 0 }}>
                    <XAxis type="number" tick={axis} tickLine={false} />
                    <YAxis type="category" dataKey="reason" width={130} tick={{ ...axis, fontSize: 10 }} tickLine={false} />
                    <Tooltip contentStyle={{ background: cssVar('raised'), border: `1px solid ${cssVar('line')}`, fontSize: 12 }} />
                    <Bar dataKey="scrappedQty" name="Scrapped" fill={cssVar('danger')} radius={[0, 3, 3, 0]} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </figure>
          </div>
          <p className="mt-3 text-xs text-mute">Same definitions as the Redshift view dw.v_production_scrap_on_time (scrap = scrapped ÷ ordered; on-time = end date ≤ due date).</p>
        </>)}
    </>
  )
}

// ---------------------------------------------------------------- work orders

function WorkOrders() {
  const { me } = useAuth()
  const supervisor = hasRole(me, 'ProductionSupervisor')
  const [month, setMonth] = useState('open')
  const list = useLoad(() => (month === 'open' ? api.openWorkOrders() : api.workOrders(month).then(r => r.items ?? [])), [month])
  const [open, setOpen] = useState<number>()
  const [creating, setCreating] = useState(false)
  const months = ['open', '2014-06', '2014-05', '2014-04', '2014-03', '2013-12', '2013-06']
  const cols: Column<WorkOrderSummary>[] = [
    { key: 'n', header: 'Work order', value: w => w.number, render: w => <button type="button" className="font-mono text-xs text-accent hover:underline" onClick={() => setOpen(w.id)} data-testid="open-wo">{w.number}</button> },
    { key: 'p', header: 'Product', value: w => w.productName ?? String(w.productId) },
    { key: 'q', header: 'Qty', value: w => w.orderQty, align: 'right' },
    { key: 'sc', header: 'Scrapped', value: w => w.scrappedQty, align: 'right' },
    { key: 'st', header: 'Start', value: w => day(w.startDate) },
    { key: 'd', header: 'Due', value: w => day(w.dueDate) },
    { key: 'e', header: 'End', value: w => day(w.endDate) },
    { key: 's', header: 'State', value: w => w.state, render: w => woPill(w.state) },
    { key: 'r', header: 'Scrap reason', value: w => w.scrapReason ?? '' },
    { key: 'src', header: 'Origin', value: w => w.source, render: w => <StatusPill label={w.source === 'ddb' ? 'app (C2-4)' : 'SQL-era, read-only'} tone={w.source === 'ddb' ? 'accent' : 'neutral'} /> },
  ]
  return (
    <>
      <div className="mb-4 flex items-end gap-3">
        <div className="w-64"><SelectField label="Due month (INV-06)" value={month} onChange={e => setMonth(e.target.value)}
          options={months.map(m => ({ value: m, label: m === 'open' ? 'Open work orders (app)' : m }))} data-testid="wo-month" /></div>
        {supervisor ? <Button onClick={() => setCreating(true)} data-testid="new-wo">New work order</Button>
          : <span className="pb-2 text-xs text-mute">Sign in as production@adventure-works.com to create and complete work orders.</span>}
      </div>
      {list.error ? <EmptyState title="Could not load work orders" action={<Button onClick={() => void list.reload()}>Retry</Button>}>{list.error.message}</EmptyState> : (
        <DataTable caption="Work orders" rows={list.data ?? []} columns={cols} rowKey={w => String(w.id)}
          empty={list.loading ? 'Loading…' : month === 'open' ? 'No open work orders – create one' : 'No work orders'} />)}
      {open && <WoDrawer id={open} onClose={() => setOpen(undefined)} onChanged={() => void list.reload()} />}
      {creating && <NewWoDrawer onClose={() => setCreating(false)} onCreated={id => { setCreating(false); setMonth('open'); void list.reload(); setOpen(id) }} />}
    </>
  )
}

/** Routing Gantt: one row per operation, scheduled (outline) vs actual (filled; warn when it ended late). */
export function Gantt({ steps }: { steps: RoutingStep[] }) {
  const times = steps.flatMap(s => [s.scheduledStartDate, s.scheduledEndDate, s.actualStartDate, s.actualEndDate]).filter(Boolean).map(t => Date.parse(t!))
  if (times.length === 0) return <p className="text-xs text-mute">No routing (purchased or not routed).</p>
  const min = Math.min(...times), max = Math.max(...times), span = Math.max(max - min, 3_600_000)
  const x = (t: string) => ((Date.parse(t) - min) / span) * 100
  const bar = (a?: string | null, b?: string | null) => (a && b ? { left: `${x(a)}%`, width: `${Math.max(x(b) - x(a), 0.8)}%` } : undefined)
  return (
    <div className="flex flex-col gap-1.5" aria-label="Routing timeline">
      {steps.map(s => (
        <div key={s.operationSequence} className="grid grid-cols-[150px_1fr] items-center gap-2 text-xs" data-testid="gantt-step">
          <div className="truncate"><span className="text-mute">{s.operationSequence}.</span> {s.locationName}</div>
          <div className="relative h-6 rounded bg-raised">
            {bar(s.scheduledStartDate, s.scheduledEndDate) && <div className="absolute top-0.5 h-2 rounded-sm border border-mute" style={bar(s.scheduledStartDate, s.scheduledEndDate)} title="scheduled" />}
            {bar(s.actualStartDate, s.actualEndDate) && <div className={`absolute bottom-0.5 h-2.5 rounded-sm ${s.late ? 'bg-warn' : 'bg-ok'}`} style={bar(s.actualStartDate, s.actualEndDate)} title="actual" />}
          </div>
        </div>))}
      <div className="flex justify-between pl-[158px] text-[10px] text-mute"><span>{new Date(min).toISOString().slice(0, 16).replace('T', ' ')}</span><span>outline = scheduled · filled = actual (amber = late)</span><span>{new Date(max).toISOString().slice(0, 16).replace('T', ' ')}</span></div>
    </div>
  )
}

export function WoDrawer({ id, onClose, onChanged }: { id: number; onClose: () => void; onChanged: () => void }) {
  const { me } = useAuth()
  const d = useLoad(() => api.workOrder(id), [id])
  const reasons = useLoad(() => api.scrapReasons())
  const [hrs, setHrs] = useState('3.5')
  const [completing, setCompleting] = useState(false)
  const [scrap, setScrap] = useState('0')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  const w: WorkOrderDetail | undefined = d.data
  const supervisor = hasRole(me, 'ProductionSupervisor')
  const actions = w?.actions ?? []
  const act = async (f: () => Promise<{ outcome: string; order: WorkOrderDetail }>, ok: (o: string) => string) => {
    setBusy(true)
    try { const r = await f(); toast(ok(r.outcome), 'ok'); await d.reload(); onChanged(); return true }
    catch (e) { toast(e instanceof ApiError ? e.message : 'Action failed', 'error'); return false } finally { setBusy(false) }
  }
  const record = () => w && act(() => api.recordOperation(id, w.version, Number(hrs)), () => `${w.order.number}: operation recorded`)
  const complete = async () => {
    if (!w) return
    if (!completing) { setCompleting(true); return }
    const s = Number(scrap || 0)
    if (await act(() => api.completeWorkOrder(id, w.version, s, s > 0 && reason ? Number(reason) : null, null),
      o => `${w.order.number} completed (${o === 'closed-on-time' ? 'on time' : 'late'})`)) setCompleting(false)
  }
  const o = w?.order
  return (
    <Drawer open wide title={o ? `Work order ${o.number}` : 'Work order'} onClose={onClose}
      footer={w && supervisor && <>
        {actions.includes('record-operation') && <><TextField label="Hours" aria-label="Resource hours" className="w-20" value={hrs} onChange={e => setHrs(e.target.value)} data-testid="op-hrs" />
          <Button size="sm" variant="secondary" disabled={busy} onClick={record} data-testid="record-op">Record next operation</Button></>}
        {actions.includes('complete') && <Button size="sm" disabled={busy} onClick={complete} data-testid="complete-wo">{completing ? 'Confirm completion' : 'Complete…'}</Button>}
      </>}>
      {!w || !o ? <p className="text-mute">Loading…</p> : (
        <div className="flex flex-col gap-4 text-sm">
          <div className="flex flex-wrap items-center gap-3"><span data-testid="wo-state">{woPill(o.state)}</span>
            <span className="text-mute">{o.productName} · v{w.version}</span>
            {w.readOnly && <StatusPill label="SQL-era · read-only" tone="neutral" />}</div>
          <div className="grid grid-cols-5 gap-2 text-xs">
            <div><div className="text-mute">Ordered</div>{o.orderQty}</div><div><div className="text-mute">Stocked · scrapped</div>{o.stockedQty} · {o.scrappedQty}</div>
            <div><div className="text-mute">Start</div>{day(o.startDate)}</div><div><div className="text-mute">Due</div>{day(o.dueDate)}</div><div><div className="text-mute">End</div>{day(o.endDate)}</div>
          </div>
          {o.scrapReason && <div className="text-xs"><span className="text-mute">Scrap reason:</span> {o.scrapReason}</div>}
          {completing && (
            <div className="grid grid-cols-2 gap-3 rounded-aw border border-line p-3" data-testid="complete-form">
              <TextField label={`Scrapped (of ${o.orderQty})`} type="number" min={0} max={o.orderQty} value={scrap} onChange={e => setScrap(e.target.value)} data-testid="scrap-qty" />
              <SelectField label="Scrap reason" value={reason} onChange={e => setReason(e.target.value)} data-testid="scrap-reason"
                options={[{ value: '', label: '—' }, ...(reasons.data ?? []).map(r => ({ value: String(r.id), label: r.name }))]} />
              <p className="col-span-2 text-xs text-mute">Stocks {o.orderQty - Number(scrap || 0)} into Finished Goods Storage and consumes the level-1 components for {o.orderQty} (inferred – AdventureWorks has no consumption records). Remaining operations close at planned hours.</p>
            </div>)}
          <section><h3 className="mb-2 text-xs uppercase tracking-wide text-mute">Routing</h3><Gantt steps={w.routing ?? []} /></section>
          {(w.routing ?? []).length > 0 && (
            <table className="w-full text-xs [&_td]:px-1.5 [&_th]:px-1.5" aria-label="Routing steps"><thead><tr className="text-left text-mute"><th>#</th><th>Work centre</th><th>Scheduled end</th><th>Actual end</th><th className="text-right">Hours</th><th className="text-right">Planned</th><th className="text-right">Actual</th></tr></thead>
              <tbody>{(w.routing ?? []).map(s => <tr key={s.operationSequence} className="border-t border-line"><td>{s.operationSequence}</td><td>{s.locationName}</td><td>{s.scheduledEndDate?.slice(0, 16).replace('T', ' ')}</td>
                <td className={s.late ? 'text-warn' : ''}>{s.actualEndDate?.slice(0, 16).replace('T', ' ') ?? '—'}</td><td className="text-right">{s.actualResourceHrs ?? '—'}</td>
                <td className="text-right">{s.plannedCost?.toFixed(2)}</td><td className="text-right">{s.actualCost?.toFixed(2) ?? '—'}</td></tr>)}</tbody></table>)}
          {(w.events ?? []).length > 0 && <section><h3 className="mb-2 text-xs uppercase tracking-wide text-mute">History</h3>
            <Timeline items={(w.events ?? []).map(e => ({ title: e.action, when: e.at.slice(0, 16).replace('T', ' '), detail: `${e.actor}${e.note ? ' · ' + e.note : ''}`, tone: e.action === 'complete' ? 'ok' : 'accent' }))} /></section>}
        </div>)}
    </Drawer>
  )
}

function NewWoDrawer({ onClose, onCreated }: { onClose: () => void; onCreated: (id: number) => void }) {
  const a = useLoad(() => api.assemblies())
  const [product, setProduct] = useState('')
  const [qty, setQty] = useState('2')
  const plan = useLoad(() => (product ? api.plan(Number(product), Number(qty) || 1) : Promise.resolve(null)), [product, qty])
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  const p = plan.data
  const create = async () => {
    setBusy(true)
    try { const w = await api.createWorkOrder(Number(product), Number(qty), null); toast(`${w.order.number} created`, 'ok'); onCreated(w.order.id) }
    catch (e) { toast(e instanceof ApiError ? e.message : 'Create failed', 'error') } finally { setBusy(false) }
  }
  return (
    <Drawer open wide title="New work order" onClose={onClose}
      footer={<Button size="sm" disabled={busy || !p?.feasible} onClick={create} data-testid="wo-create">Create work order</Button>}>
      <div className="flex flex-col gap-4 text-sm">
        <div className="grid grid-cols-[1fr_120px] gap-3">
          <SelectField label="Product (top-level assembly, ASSEMBLY#ROOT)" value={product} onChange={e => setProduct(e.target.value)} data-testid="wo-product"
            options={[{ value: '', label: a.loading ? 'Loading…' : 'Choose…' }, ...(a.data ?? []).map(x => ({ value: String(x.productId), label: x.name }))]} />
          <TextField label="Quantity" type="number" min={1} value={qty} onChange={e => setQty(e.target.value)} data-testid="wo-qty" />
        </div>
        {p && <>
          <div className="flex items-center gap-3 text-xs" data-testid={p.feasible ? 'wo-plan-ok' : 'wo-plan-blocked'}>
            <StatusPill label={p.feasible ? 'Components in stock' : 'Blocked'} tone={p.feasible ? 'ok' : 'danger'} />
            <span className="text-mute">start {day(p.startDate)} · due {day(p.dueDate)} · {p.routing?.length} operations</span></div>
          {(p.problems ?? []).map(x => <p key={x} className="text-xs text-danger">{x}</p>)}
          <section><h3 className="mb-2 text-xs uppercase tracking-wide text-mute">Standard routing</h3><Gantt steps={p.routing ?? []} /></section>
          <table className="w-full text-xs [&_td]:px-1.5 [&_th]:px-1.5" aria-label="Components"><thead><tr className="text-left text-mute"><th>Component (level 1, INV-04)</th><th className="text-right">Per unit</th><th className="text-right">Required</th><th className="text-right">On hand</th><th /></tr></thead>
            <tbody>{(p.components ?? []).map(c => <tr key={c.productId} className="border-t border-line"><td>{c.name}</td><td className="text-right">{c.perAssemblyQty}</td><td className="text-right">{c.required}</td>
              <td className="text-right">{c.onHand}</td><td>{c.available ? <StatusPill label="ok" tone="ok" /> : <StatusPill label="short" tone="danger" />}</td></tr>)}</tbody></table>
        </>}
      </div>
    </Drawer>
  )
}

// ---------------------------------------------------------------- BOM explorer

function Tree({ node, onPick, testid }: { node: BomNode; onPick: (id: number) => void; testid: string }) {
  const [open, setOpen] = useState(node.level < 1)
  const kids = node.children ?? []
  return (
    <li>
      <div className="flex items-center gap-2 py-0.5" data-testid={testid}>
        {kids.length > 0 ? <button type="button" className="w-4 text-mute" aria-label={open ? 'Collapse' : 'Expand'} onClick={() => setOpen(!open)}>{open ? '▾' : '▸'}</button> : <span className="w-4" />}
        <button type="button" className="text-left hover:text-accent" onClick={() => onPick(node.productId)}>{node.name || `Product ${node.productId}`}</button>
        <span className="text-xs text-mute">#{node.productId}{node.level > 0 ? ` · ×${node.perAssemblyQty} ${node.unitMeasureCode ?? ''}` : ''}{kids.length ? ` · ${kids.length}` : ''}</span>
      </div>
      {open && kids.length > 0 && <ul className="ml-5 border-l border-line pl-2">{kids.map(c => <Tree key={`${c.productId}-${c.startDate}`} node={c} onPick={onPick} testid={testid} />)}</ul>}
    </li>)
}

function BomExplorer() {
  const a = useLoad(() => api.assemblies())
  const [asm, setAsm] = useState('')
  const [asOf, setAsOf] = useState(today())
  const [picked, setPicked] = useState<number>()
  const first = a.data?.find(x => x.name.startsWith('Road-150'))?.productId ?? a.data?.[0]?.productId
  const root = asm ? Number(asm) : first
  const bom = useLoad(() => (root ? api.bom(root, asOf) : Promise.resolve(null)), [root, asOf])
  const used = useLoad(() => (picked ? api.whereUsed(picked, asOf) : Promise.resolve(null)), [picked, asOf])
  return (
    <>
      <div className="mb-4 grid max-w-3xl grid-cols-[1fr_180px] gap-3">
        <SelectField label="Assembly (INV-04)" value={asm || String(root ?? '')} onChange={e => { setAsm(e.target.value); setPicked(undefined) }} data-testid="bom-assembly"
          options={(a.data ?? []).map(x => ({ value: String(x.productId), label: x.name }))} />
        <TextField label="As of" type="date" value={asOf} onChange={e => setAsOf(e.target.value)} data-testid="bom-asof" />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <section className="rounded-aw border border-line bg-panel p-4">
          <h3 className="mb-1 text-sm font-semibold">Bill of materials</h3>
          {bom.data && <p className="mb-2 text-xs text-mute">{bom.data.nodes} items · {bom.data.queries} queries (one per assembly per level, levels in parallel){bom.data.depthCapped ? ' · capped at 4 levels' : ''}</p>}
          {bom.loading ? <p className="text-mute">Loading…</p> : bom.data && <ul className="text-sm"><Tree node={bom.data.root} onPick={setPicked} testid="bom-node" /></ul>}
        </section>
        <section className="rounded-aw border border-line bg-panel p-4" data-testid="where-used">
          <h3 className="mb-1 text-sm font-semibold">Where used (INV-05)</h3>
          {!picked ? <p className="text-xs text-mute">Click a component to see every assembly that uses it (GSI1 COMPONENT#, upwards).</p>
            : used.loading ? <p className="text-mute">Loading…</p> : used.data && <>
              <p className="mb-2 text-xs text-mute">{used.data.nodes - 1} assemblies · {used.data.queries} queries</p>
              <ul className="text-sm"><Tree node={used.data.root} onPick={id => { setAsm(String(id)); setPicked(undefined) }} testid="used-node" /></ul></>}
        </section>
      </div>
    </>
  )
}
