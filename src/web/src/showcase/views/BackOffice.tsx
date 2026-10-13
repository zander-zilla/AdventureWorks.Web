import { EmptyState, PageHeader, StatusPill } from '../../components'
import { ComingSoon } from '../ComingSoon'
import type { Data } from '../data'

export function BackOffice({ data }: { data: Data }) {
  const later = data.c2.phases.filter(p => p.pages.length && p.status !== 'done')
  const spa = data.config.spaUrl
  return (
    <section aria-label="Back office">
      <PageHeader title="Back office" sub="The Chapter 2 app (React SPA under /app/ on the app origin). Screens arrive phase by phase." />
      <EmptyState title="Back office screens are coming soon"
        action={spa ? <a className="text-accent" href={spa} target="_blank" rel="noreferrer">Open the Chapter 2 app ↗</a> : <span className="text-xs text-mute">App URL not configured (config.json spaUrl)</span>}>
        The order fulfilment back office lands in C2-2, procurement in C2-3 and the production floor in C2-4. Today the app has the new product list and the component gallery.
      </EmptyState>
      <ul className="mt-6 grid grid-cols-3 gap-4">
        {later.flatMap(ph => ph.pages.map(pg => (
          <li key={pg.path} className="rounded-aw border border-line bg-panel px-4 py-3" data-testid="planned-screen">
            <div className="flex items-center gap-2"><b>{pg.name}</b></div>
            <code className="text-xs text-mute">{pg.path}</code>
            <div className="mt-2"><ComingSoon phase={ph.id} /></div>
          </li>)))}
        {data.c2.phases.filter(p => p.status === 'done').flatMap(ph => ph.pages.map(pg => (
          <li key={pg.path} className="rounded-aw border border-line bg-panel px-4 py-3">
            <b>{pg.name}</b><br /><code className="text-xs text-mute">{pg.path}</code>
            <div className="mt-2"><StatusPill tone="ok" label={`Live · ${ph.id}`} /></div>
          </li>)))}
      </ul>
    </section>
  )
}
