import { Chart, KpiCard, PageHeader, Timeline } from '../components'

export function Home() {
  return (
    <>
      <PageHeader title="Chapter 2 · Extend & modernize" sub="Same data, same platform, new face. Back office screens arrive phase by phase." />
      <div className="mb-6 grid grid-cols-4 gap-3.5">
        <KpiCard label="Domain tables (DynamoDB)" value="7" />
        <KpiCard label="Processes with a UI" value="2 → 6" delta="target after C2-4" />
        <KpiCard label="Designed access patterns" value="~70" />
        <KpiCard label="API" value="/api/v2" />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Chart title="Chapter 2 effort by phase (days, upper estimate)" data={[{ label: 'C2-0', value: 6 }, { label: 'C2-1', value: 5 }, { label: 'C2-2', value: 9 }, { label: 'C2-3', value: 8 }, { label: 'C2-4', value: 6 }, { label: 'C2-5', value: 7 }]} />
        <div className="rounded-aw border border-line bg-panel p-4">
          <div className="mb-3 text-xs text-mute">Roadmap</div>
          <Timeline items={[
            { title: 'C2-0 Design system', when: 'now', detail: 'React + Tailwind, /api/v2, /app/', tone: 'info' },
            { title: 'C2-1 Showcase + chapter switch', when: 'next', tone: 'accent' },
            { title: 'C2-2 Order fulfilment, pricing, reviews', when: 'then', tone: 'accent' },
            { title: 'C2-3 Procurement · C2-4 Production · C2-5 AI (off by default)', when: 'later', tone: 'neutral' },
          ]} />
        </div>
      </div>
    </>
  )
}
