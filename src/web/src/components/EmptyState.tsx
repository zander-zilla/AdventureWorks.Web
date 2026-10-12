import type { ReactNode } from 'react'

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-aw border border-dashed border-line bg-panel px-6 py-10 text-center" role="status">
      <div className="text-3xl text-mute" aria-hidden>◌</div>
      <div className="font-display text-lg font-semibold">{title}</div>
      {children && <div className="max-w-md text-mute">{children}</div>}
      {action}
    </div>
  )
}
