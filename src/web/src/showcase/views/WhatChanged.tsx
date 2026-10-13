import { DataTable, PageHeader, StatusPill } from '../../components'
import { ComingSoon } from '../ComingSoon'
import type { Data } from '../data'

const done = (data: Data, phase: string) => data.c2.phases.find(p => p.id === phase)?.status === 'done'

export function WhatChanged({ data }: { data: Data }) {
  const { c2, adrs } = data
  const tag = (phase: string) => done(data, phase) ? <StatusPill tone="ok" label={phase} /> : <ComingSoon phase={phase} />
  return (
    <section aria-label="What changed" className="grid gap-8">
      <PageHeader title="What changed" sub="New API surface, the access patterns Chapter 2 puts to work, new Redshift views and the decision records." />
      <div><h2 className="mb-2 font-display text-xl font-semibold">/api/v2 (minimal APIs, OpenAPI)</h2>
        <DataTable caption="API v2 endpoints" rows={c2.api_v2} rowKey={r => r.method + r.path} columns={[
          { key: 'm', header: 'Method', value: r => r.method }, { key: 'p', header: 'Path', value: r => r.path, render: r => <code>{r.path}</code> },
          { key: 'ap', header: 'Pattern', value: r => r.pattern ?? '' }, { key: 'ph', header: 'Phase', value: r => r.phase, render: r => tag(r.phase) }]} /></div>
      <div><h2 className="mb-2 font-display text-xl font-semibold">Access patterns</h2>
        <p className="mb-2 text-sm text-mute">Chapter 2 reuses the Chapter 1 model: all but one are designed and load-tested already.</p>
        <DataTable caption="Access patterns used by Chapter 2" rows={c2.access_patterns} rowKey={r => r.id} columns={[
          { key: 'id', header: 'ID', value: r => r.id }, { key: 'u', header: 'Used for', value: r => r.use },
          { key: 'n', header: 'New?', value: r => r.new ? 'new' : 'existing', render: r => r.new ? <StatusPill tone="accent" label="new (if needed)" /> : <StatusPill label="existing" /> },
          { key: 'ph', header: 'Phase', value: r => r.phase, render: r => tag(r.phase) }]} /></div>
      <div><h2 className="mb-2 font-display text-xl font-semibold">Redshift views</h2>
        <ul className="grid grid-cols-2 gap-3">{c2.redshift_views.map(v => <li key={v.name} className="rounded-aw border border-line bg-panel px-4 py-3"><code>{v.name}</code><div className="text-sm text-mute">{v.use}</div><div className="mt-2">{tag(v.phase)}</div></li>)}</ul></div>
      <div><h2 className="mb-2 font-display text-xl font-semibold">Architecture decision records</h2>
        <ul className="grid gap-1.5" data-testid="adrs">{adrs.map(a => <li key={a.id} className="flex items-center gap-3 rounded-aw border border-line bg-panel px-4 py-2">
          <span className="font-mono text-accent2">{a.id}</span><span className="min-w-0 flex-1 truncate">{a.title}</span>
          {a.chapter === 2 && <StatusPill tone="accent" label="Chapter 2" />}<StatusPill tone={a.status === 'Accepted' ? 'ok' : 'neutral'} label={a.status || '—'} /></li>)}</ul></div>
    </section>
  )
}
