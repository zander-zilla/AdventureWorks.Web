import { cx } from './cx'

export function KpiCard({ label, value, delta, trend }: { label: string; value: string; delta?: string; trend?: 'up' | 'down' }) {
  return (
    <div className="rounded-aw border border-line bg-panel px-4 py-3.5" data-testid="kpi">
      <div className="text-xs text-mute">{label}</div>
      <div className="font-display text-kpi font-bold">{value}</div>
      {delta && <div className={cx('text-xs', trend === 'down' ? 'text-danger' : 'text-ok')}>{trend === 'down' ? '▼' : '▲'} {delta}</div>}
    </div>
  )
}
