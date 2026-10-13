import { useEffect, useState } from 'react'
import { Button, KpiCard, PageHeader, StatusPill } from '../../components'
import { ComingSoon } from '../ComingSoon'
import { coverage, type Data } from '../data'

/** Slides: findings → features → architecture delta (←/→ keys), all from data/*.json. */
export function Story({ data }: { data: Data }) {
  const { bp, c2 } = data
  const cov = coverage(bp, c2)
  const unused = new Set(bp.processes.flatMap(p => p.coverage.access_patterns.map(a => a.id)))
  const gaps = bp.processes.reduce((n, p) => n + p.counts.gaps, 0)
  const slides = [
    { title: 'What Chapter 1 left on the table', body: (
      <div className="grid gap-5">
        <p className="max-w-3xl text-lg text-mute">Migration was step one. The process analysis (PR #15) found business processes the migrated data model supports, but no screen uses.</p>
        <div className="grid grid-cols-4 gap-4">
          <KpiCard label="Business processes analysed" value={String(bp.processes.length)} />
          <KpiCard label="Processes with UI: before → after Chapter 2" value={`${cov.before} → ${cov.after}`} delta={`+${cov.after - cov.before} processes`} />
          <KpiCard label="Access patterns linked to processes" value={String(unused.size)} />
          <KpiCard label="Gaps found" value={String(gaps)} trend="down" delta="to close in C2-2…C2-4" />
        </div>
        <ul className="grid gap-2" data-testid="findings">
          {bp.processes.filter(p => p.gaps.length).slice(0, 5).map(p => <li key={p.id} className="rounded-aw border border-line bg-panel px-4 py-2.5"><b>{p.name}:</b> <span className="text-mute">{p.gaps[0]}</span></li>)}
        </ul>
      </div>) },
    { title: 'What Chapter 2 adds', body: (
      <ol className="grid grid-cols-2 gap-3" data-testid="features">
        {bp.chapter2_candidates.slice(0, 8).map(c => {
          const ph = c2.candidate_phase[String(c.rank)]
          return <li key={c.rank} className="rounded-aw border border-line bg-panel px-4 py-3">
            <div className="flex items-center gap-2"><span className="font-display font-bold text-accent2">#{c.rank}</span><b>{c.name}</b></div>
            <div className="mt-1 text-sm text-mute">{c.demo_value}</div>
            <div className="mt-2 flex gap-2"><StatusPill label={`effort ${c.effort}`} />{c.patterns.slice(0, 4).map(p => <StatusPill key={p} tone="info" label={p} />)}{ph ? <ComingSoon phase={ph} /> : <StatusPill label="backlog" />}</div>
          </li>
        })}
      </ol>) },
    { title: 'Architecture delta', body: (
      <table className="w-full max-w-4xl text-left" data-testid="delta">
        <thead className="text-xs text-mute uppercase"><tr><th className="py-2">Area</th><th>Chapter 1</th><th>Chapter 2</th></tr></thead>
        <tbody>{c2.architecture_delta.map(r => <tr key={r.area} className="border-t border-line"><td className="py-2.5 font-semibold">{r.area}</td><td className="text-mute">{r.before}</td><td>{r.after}</td></tr>)}</tbody>
      </table>) },
  ]
  const [i, setI] = useState(0)
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === 'ArrowRight') setI(n => Math.min(n + 1, slides.length - 1)); if (e.key === 'ArrowLeft') setI(n => Math.max(n - 1, 0)) }
    window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k)
  }, [slides.length])
  return (
    <section aria-label="Story">
      <PageHeader title={slides[i].title} sub={`Chapter 2 · Extend & modernize — slide ${i + 1} of ${slides.length} (← / →)`}
        actions={<><Button variant="secondary" onClick={() => setI(Math.max(i - 1, 0))} disabled={i === 0}>← Back</Button><Button onClick={() => setI(Math.min(i + 1, slides.length - 1))} disabled={i === slides.length - 1}>Next →</Button></>} />
      <div data-testid="slide">{slides[i].body}</div>
    </section>
  )
}
