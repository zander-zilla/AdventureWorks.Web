import { useEffect } from 'react'
import { api } from '../../api/client'
import { useLoad } from '../../api/useLoad'
import { EmptyState, PageHeader, StatusPill } from '../../components'

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
