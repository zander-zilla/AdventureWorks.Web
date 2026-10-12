import { cx } from './cx'

export type Tone = 'neutral' | 'accent' | 'info' | 'ok' | 'warn' | 'danger'
const tone: Record<Tone, string> = {
  neutral: 'text-mute border-mute', accent: 'text-accent border-accent', info: 'text-accent2 border-accent2',
  ok: 'text-ok border-ok', warn: 'text-warn border-warn', danger: 'text-danger border-danger',
}
/** Sales order status 1-6 (ufnGetSalesOrderStatusText) → tone. */
export const orderStatus: Record<number, [string, Tone]> = {
  1: ['In process', 'info'], 2: ['Approved', 'accent'], 3: ['Backordered', 'warn'], 4: ['Rejected', 'danger'], 5: ['Shipped', 'ok'], 6: ['Cancelled', 'neutral'],
}
export function StatusPill({ label, tone: t = 'neutral' }: { label: string; tone?: Tone }) {
  return <span className={cx('inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap', tone[t])}>{label}</span>
}
