import { useNavigate, useParams } from 'react-router'
import { Chart, DataTable, Drawer, KpiCard, PageHeader, StatusPill, Timeline, type Column } from '../../components'
import { ComingSoon } from '../ComingSoon'
import { coverage, phaseFor, type Data, type Process } from '../data'

export function Processes({ data }: { data: Data }) {
  const { bp, c2 } = data
  const cov = coverage(bp, c2)
  const { id } = useParams()
  const go = useNavigate()
  const sel = bp.processes.find(p => p.id === id)
  const status = (p: Process) => cov.beforeIds.has(p.id) ? 'Chapter 1' : phaseFor(c2, p.id) ?? 'not planned'
  const cols: Column<Process>[] = [
    { key: 'name', header: 'Process', value: p => p.name, render: p => <a className="text-accent hover:underline" href={`#/c2/processes/${p.id}`}>{p.name}</a>, sortable: true },
    { key: 'domain', header: 'Domain', value: p => p.domain, sortable: true },
    { key: 'steps', header: 'Steps', value: p => p.counts.steps, align: 'right', sortable: true },
    { key: 'pages', header: 'App pages (Ch. 1)', value: p => p.counts.app_pages, align: 'right', sortable: true },
    { key: 'gaps', header: 'Gaps', value: p => p.counts.gaps, align: 'right', sortable: true },
    { key: 'ui', header: 'UI from', value: status, render: p => { const s = status(p); return s === 'Chapter 1' ? <StatusPill tone="ok" label="Chapter 1" /> : s.startsWith('C2') ? <ComingSoon phase={s} /> : <StatusPill label={s} /> } },
  ]
  return (
    <section aria-label="Business processes">
      <PageHeader title="Business processes" sub="The 10 processes from the PR #15 analysis (docs/business-processes), with what Chapter 2 gives a screen." />
      <div className="mb-5 grid grid-cols-4 gap-4">
        <div data-testid="coverage-tile"><KpiCard label="Processes with UI: before → after Chapter 2" value={`${cov.before} → ${cov.after}`} delta={`of ${cov.total}`} /></div>
        {Object.entries(cov.byPhase).map(([ph, ids]) => <KpiCard key={ph} label={`New in ${ph} (coming soon)`} value={`+${ids.length}`} delta={ids.map(x => bp.processes.find(p => p.id === x)?.name.split(':')[0]).join(', ')} />)}
      </div>
      <div className="mb-5 grid grid-cols-2 gap-4">
        <Chart title="Gaps per process (from evidence)" data={bp.processes.map(p => ({ label: p.id.split('-')[0], value: p.counts.gaps }))} color="warn" />
        <Chart title="Evidenced steps per process" data={bp.processes.map(p => ({ label: p.id.split('-')[0], value: p.counts.evidenced_steps }))} color="accent2" />
      </div>
      <DataTable caption="Business process landscape" rows={bp.processes} columns={cols} rowKey={p => p.id} />
      <Drawer open={!!sel} title={sel?.name ?? ''} onClose={() => go('/c2/processes')}>
        {sel && <div className="grid gap-4" data-testid="process-detail">
          <p className="text-mute">{sel.summary}</p>
          <div><b>Trigger:</b> {sel.trigger}</div>
          <Timeline items={sel.steps.map(s => ({ title: s.name, when: s.actor, detail: s.note, tone: s.basis === 'evidenced' ? 'ok' : 'warn' }))} />
          <div><b>Gaps</b><ul className="mt-1 list-disc pl-5 text-mute">{sel.gaps.map(g => <li key={g}>{g}</li>)}</ul></div>
          <div className="flex flex-wrap gap-1.5">{sel.coverage.access_patterns.map(a => <span key={a.id} title={a.question}><StatusPill tone="info" label={a.id} /></span>)}</div>
        </div>}
      </Drawer>
    </section>
  )
}
