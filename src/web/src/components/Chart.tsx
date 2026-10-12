import { cssVar, type TokenName } from '../theme/tokens'

export type Point = { label: string; value: number }
/** Dependency-free SVG chart wrapper (bar | line) using theme tokens; swap for Recharts later behind the same props. */
export function Chart({ data, kind = 'bar', height = 160, color = 'accent', title }: { data: Point[]; kind?: 'bar' | 'line'; height?: number; color?: TokenName; title: string }) {
  const w = 100 * Math.max(data.length, 1), max = Math.max(1, ...data.map(d => d.value)), pad = 18
  const y = (v: number) => height - pad - (v / max) * (height - pad - 6)
  return (
    <figure className="rounded-aw border border-line bg-panel p-4">
      <figcaption className="mb-2 text-xs text-mute">{title}</figcaption>
      <svg role="img" aria-label={title} viewBox={`0 0 ${w} ${height}`} className="w-full" preserveAspectRatio="none" style={{ height }}>
        <line x1="0" x2={w} y1={height - pad} y2={height - pad} stroke={cssVar('line')} />
        {kind === 'bar'
          ? data.map((d, i) => <rect key={d.label} data-testid="bar" x={i * 100 + 20} width="60" y={y(d.value)} height={height - pad - y(d.value)} rx="3" fill={cssVar(color)} />)
          : <polyline fill="none" stroke={cssVar(color)} strokeWidth="3" points={data.map((d, i) => `${i * 100 + 50},${y(d.value)}`).join(' ')} />}
        {data.map((d, i) => <text key={d.label} x={i * 100 + 50} y={height - 4} textAnchor="middle" fontSize="11" fill={cssVar('mute')}>{d.label}</text>)}
      </svg>
    </figure>
  )
}
