import { Navigate, Route, Routes } from 'react-router'
import { ChapterSwitch, EmptyState, NavRail, type NavGroup } from '../components'
import { useTheme } from '../theme/ThemeProvider'
import { useData } from './data'
import { AskTheData } from './views/AskTheData'
import { BackOffice } from './views/BackOffice'
import { Processes } from './views/Processes'
import { Story } from './views/Story'
import { WhatChanged } from './views/WhatChanged'

// Chapter 1 'Migration' is the frozen v1.0-migration build under /c1/ (same bucket + distribution).
export const goChapter1 = () => { window.location.href = 'c1/' }

const nav: NavGroup[] = [
  { title: 'Chapter 2', items: [
    { to: '/c2/story', label: 'Story', icon: '▶' },
    { to: '/c2/processes', label: 'Business processes', icon: '⇶' },
    { to: '/c2/back-office', label: 'Back office', icon: '⇄', badge: 'C2-4' },
    { to: '/c2/changes', label: 'What changed', icon: '△' },
    { to: '/c2/ask', label: 'Ask the data', icon: '✦', badge: 'C2-5' },
  ] },
]

export function Showcase() {
  const { theme, toggle } = useTheme()
  const { data, error } = useData()
  return (
    <div className="flex min-h-full flex-col">
      <header className="flex flex-wrap items-center gap-6 border-b border-line bg-panel px-6 py-3">
        <a href="#/c2/story" className="font-display text-lg font-bold">Adventure<b className="text-accent2">Works</b> <span className="text-sm font-normal text-mute">modernization</span></a>
        <ChapterSwitch value="c2" onChange={c => c === 'c1' && goChapter1()} />
        <div className="ml-auto flex items-center gap-3 text-sm">
          {data?.config.spaUrl && <a className="text-accent" href={data.config.spaUrl} target="_blank" rel="noreferrer">Open the Chapter 2 app ↗</a>}
          <button type="button" onClick={toggle} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
            className="rounded-aw border border-line px-2.5 py-1.5 text-mute hover:text-ink" data-testid="theme-toggle">{theme === 'dark' ? '☾ Dark' : '☀ Light'}</button>
        </div>
      </header>
      <div className="flex flex-1">
        <NavRail groups={nav} />
        <main className="min-w-0 flex-1 px-8 py-6">
          {error ? <EmptyState title="Could not load the showcase data">{error}</EmptyState>
            : !data ? <div role="status" className="text-mute">Loading…</div>
            : <Routes>
                <Route index element={<Navigate to="/c2/story" replace />} />
                <Route path="c2" element={<Navigate to="/c2/story" replace />} />
                <Route path="c2/story" element={<Story data={data} />} />
                <Route path="c2/processes" element={<Processes data={data} />} />
                <Route path="c2/processes/:id" element={<Processes data={data} />} />
                <Route path="c2/back-office" element={<BackOffice data={data} />} />
                <Route path="c2/changes" element={<WhatChanged data={data} />} />
                <Route path="c2/ask" element={<AskTheData data={data} />} />
                <Route path="*" element={<EmptyState title="Not found">Try the Story tab.</EmptyState>} />
              </Routes>}
          {data?.build.commit && <footer className="mt-10 text-xs text-mute">Built from {data.build.commit} · {data.build.built}</footer>}
        </main>
      </div>
    </div>
  )
}
