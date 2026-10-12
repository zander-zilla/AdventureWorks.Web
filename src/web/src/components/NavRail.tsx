import { NavLink } from 'react-router'
import { cx } from './cx'

export type NavItem = { to: string; label: string; icon: string; badge?: string; disabled?: boolean }
export type NavGroup = { title: string; items: NavItem[] }
export function NavRail({ groups }: { groups: NavGroup[] }) {
  return (
    <nav aria-label="Main" className="flex w-56 shrink-0 flex-col gap-5 border-r border-line px-3 py-5">
      {groups.map(g => (
        <div key={g.title}>
          <div className="mb-1.5 px-3 text-[11px] font-semibold tracking-wider text-mute uppercase">{g.title}</div>
          {g.items.map(i => i.disabled
            ? <span key={i.to} className="flex items-center gap-2.5 rounded-aw px-3 py-2 text-mute/60" title="Coming in a later phase"><span aria-hidden>{i.icon}</span>{i.label}{i.badge && <span className="ml-auto text-[10px]">{i.badge}</span>}</span>
            : <NavLink key={i.to} to={i.to} end className={({ isActive }) => cx('flex items-center gap-2.5 rounded-aw px-3 py-2',
                isActive ? 'border border-line bg-panel font-semibold text-ink' : 'border border-transparent text-mute hover:text-ink')}>
                <span aria-hidden>{i.icon}</span>{i.label}{i.badge && <span className="ml-auto text-[10px] text-accent2">{i.badge}</span>}
              </NavLink>)}
        </div>
      ))}
    </nav>
  )
}
