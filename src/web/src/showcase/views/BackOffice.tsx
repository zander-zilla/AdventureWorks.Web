import { PageHeader, StatusPill } from '../../components'
import { ComingSoon } from '../ComingSoon'
import type { Data } from '../data'

/** C2-2/C2-3: the back office is live (fulfilment, procurement). Lists live screens (deep links into the app) and the ones later phases add. */
export function BackOffice({ data }: { data: Data }) {
  const spa = data.config.spaUrl?.replace(/\/?$/, '/')
  const link = (path: string) => (spa && !path.includes(':') ? spa + path.replace(/^\/app\/?/, '') : undefined)
  const live = data.c2.phases.filter(p => p.status === 'done')
  const later = data.c2.phases.filter(p => p.pages.length && p.status !== 'done')
  return (
    <section aria-label="Back office">
      <PageHeader title="Back office" sub="The Chapter 2 app (React SPA, now the site root). Order fulfilment (C2-2) and procurement (C2-3) are live: reorder suggestions become purchase orders that a manager approves and a buyer receives into stock, with vendor performance and a replication monitor showing each write on its way to Redshift." />
      <div className="mb-4 flex flex-wrap gap-3 text-sm" data-testid="back-office-live">
        {spa ? <>
          <a className="text-accent" href={link('/app/back-office/orders')} target="_blank" rel="noreferrer">Open back office orders ↗</a>
          <a className="text-accent" href={link('/app/back-office/procurement')} target="_blank" rel="noreferrer">Open procurement ↗</a>
          <a className="text-accent" href={link('/app/back-office/replication')} target="_blank" rel="noreferrer">Open replication monitor ↗</a>
          <span className="text-mute">Demo staff: fulfilment@ (orders), mikael0@ (buyer), sheela0@ (purchasing manager) at adventure-works.com</span>
        </> : <span className="text-xs text-mute">App URL not configured (config.json spaUrl)</span>}
      </div>
      <ul className="grid grid-cols-3 gap-4">
        {live.flatMap(ph => ph.pages.map(pg => {
          const href = link(pg.path)
          return (
            <li key={pg.path} className="rounded-aw border border-line bg-panel px-4 py-3" data-testid="live-screen">
              <b>{href ? <a href={href} target="_blank" rel="noreferrer">{pg.name}</a> : pg.name}</b><br />
              <code className="text-xs text-mute">{pg.path}</code>
              <div className="mt-2"><StatusPill tone="ok" label={`Live · ${ph.id}`} /></div>
            </li>)
        }))}
        {later.flatMap(ph => ph.pages.map(pg => (
          <li key={pg.path} className="rounded-aw border border-line bg-panel px-4 py-3" data-testid="planned-screen">
            <b>{pg.name}</b><br /><code className="text-xs text-mute">{pg.path}</code>
            <div className="mt-2"><ComingSoon phase={ph.id} /></div>
          </li>)))}
      </ul>
    </section>
  )
}
