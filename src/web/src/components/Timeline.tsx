import { cx } from './cx'
import type { Tone } from './StatusPill'

export type TimelineItem = { title: string; when: string; detail?: string; tone?: Tone }
const dot: Record<Tone, string> = { neutral: 'bg-mute', accent: 'bg-accent', info: 'bg-accent2', ok: 'bg-ok', warn: 'bg-warn', danger: 'bg-danger' }
export function Timeline({ items }: { items: TimelineItem[] }) {
  return (
    <ol className="relative ml-2 border-l border-line">
      {items.map((it, i) => (
        <li key={i} className="mb-4 ml-5 last:mb-0">
          <span className={cx('absolute -left-[5px] mt-1.5 size-2.5 rounded-full', dot[it.tone ?? 'accent'])} />
          <div className="flex items-baseline gap-3"><span className="font-semibold">{it.title}</span><time className="text-xs text-mute">{it.when}</time></div>
          {it.detail && <div className="text-sm text-mute">{it.detail}</div>}
        </li>
      ))}
    </ol>
  )
}
