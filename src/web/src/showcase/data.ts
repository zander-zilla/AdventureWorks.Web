import { useEffect, useState } from 'react'

export type Step = { name: string; actor: string; basis: string; note?: string }
export type Process = {
  id: string; name: string; domain: string; summary: string; trigger: string; actors: string[]; steps: Step[]; gaps: string[]
  coverage: { access_patterns: { id: string; question: string; scope: string }[]; app_pages: string[]; redshift: string[] }
  counts: { steps: number; evidenced_steps: number; app_pages: number; gaps: number }
}
export type Candidate = { rank: number; name: string; processes: string[]; patterns: string[]; effort: string; demo_value: string; fills_gaps: string[] }
export type BusinessProcesses = { processes: Process[]; chapter2_candidates: Candidate[] }
export type Page = { path: string; name: string; processes: string[] }
export type Phase = { id: string; name: string; status: 'done' | 'building' | 'planned'; pr?: number; optional?: boolean; pages: Page[] }
export type Chapter2 = {
  phases: Phase[]
  api_v2: { method: string; path: string; pattern?: string; phase: string }[]
  access_patterns: { id: string; use: string; phase: string; new: boolean }[]
  redshift_views: { name: string; use: string; phase: string }[]
  candidate_phase: Record<string, string>
  architecture_delta: { area: string; before: string; after: string }[]
}
export type Adr = { id: string; title: string; status: string; file: string; chapter: number }
export type Config = { appUrl?: string; spaUrl?: string; askTheData?: boolean }
export type Build = { commit?: string; built?: string }
export type Data = { bp: BusinessProcesses; c2: Chapter2; adrs: Adr[]; config: Config; build: Build }

const get = <T,>(u: string): Promise<T> => fetch(u).then(r => { if (!r.ok) throw new Error(`${u}: ${r.status}`); return r.json() as Promise<T> })

export async function loadData(): Promise<Data> {
  const [bp, c2, adrs, config, build] = await Promise.all([
    get<BusinessProcesses>('data/business-processes.json'), get<Chapter2>('data/chapter2.json'), get<Adr[]>('data/adrs.json'),
    get<Config>('config.json').catch(() => ({})), get<Build>('data/build.json').catch(() => ({})),
  ])
  return { bp, c2, adrs, config, build }
}

export function useData() {
  const [s, set] = useState<{ data?: Data; error?: string }>({})
  useEffect(() => { loadData().then(data => set({ data }), e => set({ error: String(e) })) }, [])
  return s
}

/** Coverage tile: processes with any UI before Chapter 2 (app pages in business-processes.json) vs. after all Chapter 2 phases. */
export function coverage(bp: BusinessProcesses, c2: Chapter2) {
  const before = new Set(bp.processes.filter(p => p.counts.app_pages > 0).map(p => p.id))
  const after = new Set(before)
  const byPhase: Record<string, string[]> = {}
  for (const ph of c2.phases) for (const pg of ph.pages) for (const id of pg.processes) {
    if (!after.has(id)) (byPhase[ph.id] ??= []).push(id)
    after.add(id)
  }
  return { before: before.size, after: after.size, total: bp.processes.length, beforeIds: before, afterIds: after, byPhase }
}

/** First Chapter 2 phase that gives a process a (new) page. */
export function phaseFor(c2: Chapter2, processId: string) {
  return c2.phases.find(ph => ph.id !== 'C2-0' && ph.pages.some(pg => pg.processes.includes(processId)))?.id
}
