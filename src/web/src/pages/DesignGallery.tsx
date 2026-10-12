import { useState, type ReactNode } from 'react'
import {
  Button, ChapterSwitch, Chart, Checkbox, DataTable, Drawer, EmptyState, KpiCard, PageHeader, SelectField, StatusPill, TextField, Timeline,
  orderStatus, useToast, type Chapter, type Column,
} from '../components'
import { useTheme } from '../theme/ThemeProvider'
import { tokenNames, tokens } from '../theme/tokens'

type Order = { no: string; customer: string; date: string; status: number; total: number }
const orders: Order[] = [
  { no: 'SO-DDB-1000000042', customer: 'Donald Garcia', date: '2026-10-12', status: 1, total: 3578.27 },
  { no: 'SO75123', customer: 'Kaitlyn Henderson', date: '2014-06-30', status: 5, total: 189.97 },
  { no: 'SO75122', customer: 'Lucas Phillips', date: '2014-06-30', status: 2, total: 30.97 },
  { no: 'SO75121', customer: 'Catherine Abel', date: '2014-06-29', status: 3, total: 2049.10 },
  { no: 'SO75120', customer: 'Cory Fernandez', date: '2014-06-29', status: 6, total: 84.48 },
]
const money = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
const cols: Column<Order>[] = [
  { key: 'no', header: 'Order', value: o => o.no, render: o => <span className="font-mono text-xs">{o.no}</span> },
  { key: 'customer', header: 'Customer', value: o => o.customer },
  { key: 'date', header: 'Date', value: o => o.date },
  { key: 'status', header: 'Status', value: o => orderStatus[o.status][0], render: o => <StatusPill label={orderStatus[o.status][0]} tone={orderStatus[o.status][1]} /> },
  { key: 'total', header: 'Total', value: o => o.total, render: o => money(o.total), align: 'right' },
]

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return <section id={id} aria-labelledby={`${id}-h`} className="mb-8"><h2 id={`${id}-h`} className="mb-3 font-display text-xl font-semibold">{title}</h2>{children}</section>
}

/** Storybook-lite: every core component in every state, in the current theme (/app/design). */
export function DesignGallery() {
  const { theme, setTheme } = useTheme()
  const toast = useToast()
  const [drawer, setDrawer] = useState(false)
  const [chapter, setChapter] = useState<Chapter>('c2')
  return (
    <>
      <PageHeader title="Component gallery" sub={`Design tokens and the 12 core components · theme: ${theme === 'dark' ? 'B · Ops console (dark)' : 'A · Trail (light)'}`}
        actions={<><Button variant={theme === 'dark' ? 'primary' : 'secondary'} size="sm" onClick={() => setTheme('dark')}>Dark</Button>
          <Button variant={theme === 'light' ? 'primary' : 'secondary'} size="sm" onClick={() => setTheme('light')}>Light</Button></>} />

      <Section id="tokens" title="Tokens">
        <div className="grid grid-cols-6 gap-2">
          {tokenNames.map(t => (
            <div key={t} className="rounded-aw border border-line bg-panel p-2 text-xs">
              <div className="mb-1.5 h-8 rounded-aw border border-line" style={{ background: `var(--aw-${t})` }} />
              <div className="font-semibold">{t}</div><div className="font-mono text-mute">{tokens[theme][t]}</div>
            </div>))}
        </div>
        <div className="mt-3 flex items-baseline gap-6"><span className="font-display text-3xl font-bold">Display</span><span className="text-base">Body 14/1.45</span><span className="text-xs text-mute">Caption · mute</span><span className="font-mono text-xs">SO-DDB-1000000042</span></div>
      </Section>

      <Section id="buttons" title="Buttons · StatusPill · ChapterSwitch">
        <div className="flex flex-wrap items-center gap-3">
          <Button>Primary</Button><Button variant="secondary">Secondary</Button><Button variant="ghost">Ghost</Button><Button variant="danger">Danger</Button><Button disabled>Disabled</Button>
          <span className="mx-2 h-6 border-l border-line" />
          {Object.values(orderStatus).map(([l, t]) => <StatusPill key={l} label={l} tone={t} />)}
          <span className="mx-2 h-6 border-l border-line" />
          <ChapterSwitch value={chapter} onChange={setChapter} />
        </div>
      </Section>

      <Section id="kpis" title="KpiCard">
        <div className="grid grid-cols-4 gap-3.5">
          <KpiCard label="Open orders" value="1,284" delta="4.2% vs last week" /><KpiCard label="Awaiting shipment" value="312" />
          <KpiCard label="Backordered" value="27" delta="3 since yesterday" trend="down" /><KpiCard label="Revenue (30 d)" value="$1.94M" delta="8.1%" />
        </div>
      </Section>

      <Section id="table" title="DataTable (sort, filter, multi-select)">
        <DataTable caption="Orders" rows={orders} columns={cols} rowKey={o => o.no} selectable
          actions={sel => <><Button variant="secondary" size="sm" disabled={!sel.length} onClick={() => toast(`Approved ${sel.length} order(s)`, 'ok')}>Approve</Button>
            <Button size="sm" disabled={!sel.length} onClick={() => setDrawer(true)}>Ship…</Button></>} />
      </Section>

      <div className="grid grid-cols-2 gap-6">
        <Section id="forms" title="Form fields · Drawer · Toast">
          <div className="flex flex-col gap-3 rounded-aw border border-line bg-panel p-4">
            <TextField label="Tracking number" placeholder="1Z999AA10123456784" hint="Carrier tracking id" />
            <TextField label="Quantity" defaultValue="-1" error="Must be at least 1" />
            <SelectField label="Ship method" options={[{ value: '5', label: 'CARGO TRANSPORT 5' }, { value: '1', label: 'XRQ - TRUCK GROUND' }]} />
            <Checkbox label="Notify customer" defaultChecked />
            <div className="flex gap-2"><Button onClick={() => setDrawer(true)}>Open drawer</Button><Button variant="secondary" onClick={() => toast('Saved', 'ok')}>Show toast</Button></div>
          </div>
        </Section>
        <Section id="timeline" title="Timeline">
          <div className="rounded-aw border border-line bg-panel p-4">
            <Timeline items={[
              { title: 'Order placed', when: '10:02', detail: 'Web · 3 lines', tone: 'info' }, { title: 'Approved', when: '10:15', tone: 'accent' },
              { title: 'Shipped', when: '14:40', detail: 'CARGO TRANSPORT 5 · 1Z999AA1', tone: 'ok' }, { title: 'Replicated to Redshift', when: '14:41', detail: 'zero-ETL', tone: 'neutral' },
            ]} />
          </div>
        </Section>
      </div>

      <div className="grid grid-cols-2 gap-6">
        <Section id="charts" title="Chart wrapper">
          <div className="grid grid-cols-2 gap-3">
            <Chart title="Orders per day" data={[{ label: 'Mon', value: 42 }, { label: 'Tue', value: 58 }, { label: 'Wed', value: 51 }, { label: 'Thu', value: 74 }, { label: 'Fri', value: 66 }]} />
            <Chart kind="line" color="accent2" title="Scrap rate %" data={[{ label: 'Q1', value: 2.1 }, { label: 'Q2', value: 1.8 }, { label: 'Q3', value: 2.6 }, { label: 'Q4', value: 1.4 }]} />
          </div>
        </Section>
        <Section id="empty" title="EmptyState">
          <EmptyState title="No backordered orders" action={<Button variant="secondary" size="sm">Show all orders</Button>}>Everything in stock has shipped.</EmptyState>
        </Section>
      </div>

      <Drawer open={drawer} title="Ship orders" onClose={() => setDrawer(false)}
        footer={<><Button variant="secondary" onClick={() => setDrawer(false)}>Cancel</Button><Button onClick={() => { setDrawer(false); toast('Shipped (demo)', 'ok') }}>Ship</Button></>}>
        <div className="flex flex-col gap-3">
          <SelectField label="Ship method" options={[{ value: '5', label: 'CARGO TRANSPORT 5' }]} />
          <TextField label="Tracking number" />
        </div>
      </Drawer>
    </>
  )
}
