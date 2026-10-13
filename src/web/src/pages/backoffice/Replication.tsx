import { useEffect, useState } from 'react'
import { api, type AssistResult } from '../../api/client'
import { AssistBox } from '../ai/AssistPanel'
import { useLoad } from '../../api/useLoad'
import { Button, EmptyState, KpiCard, PageHeader, StatusPill } from '../../components'

const tone = (e: string) => (e.endsWith('ship') || e === 'po.receive' || e === 'wo.complete' ? 'ok' : e.endsWith('placed') || e === 'po.create' || e === 'wo.create' ? 'info' : e.startsWith('order.cancel') || e.endsWith('reject') ? 'danger' : 'accent') as 'ok' | 'info' | 'danger' | 'accent'

/** Replication monitor for app writes (C2-2): every business write lands in DynamoDB with an origin marker
 *  (src = ddb, src_lsn = ~app, so the one-way SQL CDC never overwrites it) and a change-feed entry naming each item and
 *  the Redshift staging view that zero-ETL feeds from it. Chapter 1's monitor shows SQL -> DynamoDB; this shows the
 *  new direction: app -> DynamoDB -> Redshift. Refreshes every 3 s. */
export function Replication() {
  const feed = useLoad(() => api.changes(50))
  const { reload } = feed
  useEffect(() => { const t = setInterval(() => void reload(), 3000); return () => clearInterval(t) }, [reload])
  return (
    <>
      <PageHeader title="Replication monitor" sub="App writes → DynamoDB (origin ~app) → zero-ETL → Redshift staging views. Newest first, live." />
      <Watchdog />
      {feed.error ? <EmptyState title="Could not load the change feed">{feed.error.message}</EmptyState> : (
        <ol className="flex flex-col gap-3" data-testid="feed">
          {(feed.data ?? []).length === 0 && <li className="text-mute">No app writes yet. Place an order in the shop or raise a purchase order.</li>}
          {(feed.data ?? []).map(e => (
            <li key={e.id} className="rounded-aw border border-line bg-panel p-4" data-testid="feed-entry">
              <div className="flex items-center gap-3 text-sm">
                <StatusPill label={e.event} tone={tone(e.event)} /><b className="font-mono">{e.subject}</b>
                <span className="text-mute">{e.at.replace('T', ' ').slice(0, 19)} UTC · {e.actor}</span>
              </div>
              <ul className="mt-2 flex flex-col gap-0.5 font-mono text-xs text-mute">{e.writes.map((w, i) => <li key={i}>{w}</li>)}</ul>
            </li>))}
        </ol>)}
    </>
  )
}

const sevTone = { ok: 'ok', warn: 'warn', danger: 'danger' } as Record<string, 'ok' | 'warn' | 'danger'>
const secs = (ms: number) => (ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`)

/** C2-6 replication watchdog (enable_ai): fixed rules name the likely cause from the SQL -> DynamoDB replication status
 *  (monitor API on AWS, recorded scenarios locally); the model only explains it and links the runbook. Read-only. */
function Watchdog() {
  const ai = useLoad(() => api.aiStatus(), [])
  const [scenario, setScenario] = useState<string>()
  const w = useLoad(async () => (ai.data?.enabled ? await api.watchdog(scenario) : null), [ai.data?.enabled, scenario])
  const [r, setR] = useState<AssistResult | null>(null)
  const [busy, setBusy] = useState(false)
  if (!ai.data?.enabled || !w.data) return null
  const { snapshot: s, cause: c } = w.data
  return (
    <section className="mb-6 flex flex-col gap-3 rounded-aw border border-line bg-panel p-4" aria-label="Replication watchdog" data-testid="watchdog">
      <header className="flex flex-wrap items-center gap-3">
        <span className="text-xs uppercase text-mute">✦ Watchdog · SQL Server → DynamoDB</span>
        <span data-testid="watchdog-cause"><StatusPill label={c.title} tone={sevTone[c.severity] ?? 'neutral'} /></span>
        {w.data.replay && (
          <div className="ml-auto flex gap-1" role="group" aria-label="Recorded scenario">
            {w.data.scenarios.map(x => (
              <button key={x} type="button" onClick={() => { setScenario(x); setR(null) }} data-testid={`scenario-${x}`}
                className={`rounded-aw px-2 py-1 text-xs ${(scenario ?? 'healthy') === x ? 'bg-accent text-accent-ink' : 'text-mute hover:text-ink'}`}>{x}</button>))}
          </div>)}
      </header>
      <div className="grid grid-cols-4 gap-3">
        <KpiCard label="Lag (last)" value={secs(s.status.lagMs.last)} delta={`p50 ${secs(s.status.lagMs.p50)} · max ${secs(s.status.lagMs.max)}`} />
        <KpiCard label="Queued" value={String(s.status.queued)} delta={s.status.paused ? 'consumer paused' : 'consumer running'} />
        <KpiCard label="Dead-letter queue" value={String(s.status.dlq ?? '—')} delta="depth only on AWS" />
        <KpiCard label="Source" value={w.data.replay ? 'Recorded' : 'Live'} delta={w.data.replay ? `scenario ${s.scenario}` : 'monitor API'} />
      </div>
      {s.dlqSamples.length > 0 && (
        <ul className="font-mono text-xs text-mute" data-testid="dlq-samples">{s.dlqSamples.map((d, i) => <li key={i}>{d.table} · {d.op} · {d.error} · {d.attempts} attempts</li>)}</ul>)}
      <AssistBox title="What is going on" r={r}>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" disabled={busy} data-testid="watchdog-explain"
            onClick={async () => { setBusy(true); try { setR(await api.explainWatchdog(scenario)) } finally { setBusy(false) } }}>Explain</Button>
          <span className="text-xs text-mute">Next step: {c.nextStep} · runbook <code>{c.runbook}</code></span>
        </div>
      </AssistBox>
    </section>
  )
}
