import type { ReactNode } from 'react'
import { useTheme } from '../theme/ThemeProvider'
import { ChapterSwitch, type Chapter } from './ChapterSwitch'
import { NavRail, type NavGroup } from './NavRail'

export function AppShell({ nav, user, chapter, onChapter, onSignOut, children }: {
  nav: NavGroup[]; user?: string | null; chapter: Chapter; onChapter: (c: Chapter) => void; onSignOut?: () => void; children: ReactNode
}) {
  const { theme, toggle } = useTheme()
  return (
    <div className="flex min-h-full flex-col">
      <header className="flex items-center gap-6 border-b border-line bg-panel px-6 py-3">
        <a href="/app/" className="font-display text-lg font-bold">Adventure<b className="text-accent2">Works</b></a>
        <ChapterSwitch value={chapter} onChange={onChapter} />
        <div className="ml-auto flex items-center gap-3 text-sm">
          <button type="button" onClick={toggle} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
            className="rounded-aw border border-line px-2.5 py-1.5 text-mute hover:text-ink" data-testid="theme-toggle">{theme === 'dark' ? '☾ Dark' : '☀ Light'}</button>
          {user ? <><span className="text-mute" data-testid="user">{user}</span>
            {onSignOut && <button type="button" onClick={onSignOut} className="text-mute hover:text-ink">Sign out</button>}</>
            : <a href="/app/login" className="text-accent">Sign in</a>}
        </div>
      </header>
      <div className="flex flex-1">
        <NavRail groups={nav} />
        <main className="min-w-0 flex-1 px-8 py-6">{children}</main>
      </div>
    </div>
  )
}

export function PageHeader({ title, sub, actions }: { title: string; sub?: string; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex items-end gap-4">
      <div><h1 className="font-display text-3xl font-bold">{title}</h1>{sub && <p className="text-mute">{sub}</p>}</div>
      {actions && <div className="ml-auto flex gap-2">{actions}</div>}
    </div>
  )
}
