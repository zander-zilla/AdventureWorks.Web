import { useState } from 'react'
import { Link } from 'react-router'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, money, type AskResult, type SearchResult } from '../api/client'
import { useLoad } from '../api/useLoad'
import { Button, EmptyState, KpiCard, PageHeader, StatusPill, TextField } from '../components'
import { cssVar } from '../theme/tokens'

// C2-5 AI layer (enable_ai, off by default). Ask the data: question -> SQL over the dw views (SqlGuard: one SELECT, views only,
// row limit, timeout) -> table + chart; semantic product search: embeddings + vector index blended with keyword overlap.

function Off() {
  return <EmptyState title="The AI layer is off">Set <code>enable_ai = true</code> in Terraform (or <code>Ai__Enabled=true</code> locally) to turn on ask-the-data and semantic search.</EmptyState>
}

const fmt = (v: unknown) => typeof v === 'number' ? (Number.isInteger(v) ? v.toLocaleString('en-US') : v.toLocaleString('en-US', { maximumFractionDigits: 4 })) : v == null ? '—' : String(v)

function ResultChart({ r }: { r: AskResult }) {
  if (!r.chart || r.columns.length !== 2) return null
  const data = r.rows.map(x => ({ label: String(x[0] ?? '—'), value: Number(x[1] ?? 0) }))
  const accent = cssVar('accent') || '#6d7cff', line = cssVar('line') || '#333', mute = cssVar('mute') || '#999'
  return (
    <div className="h-64 rounded-aw border border-line bg-panel p-3" data-testid="ask-chart">
      <ResponsiveContainer width="100%" height="100%">
        {r.chart === 'line'
          ? <LineChart data={data}><CartesianGrid stroke={line} strokeDasharray="3 3" /><XAxis dataKey="label" stroke={mute} fontSize={11} /><YAxis stroke={mute} fontSize={11} width={80} /><Tooltip /><Line dataKey="value" name={r.columns[1]} stroke={accent} strokeWidth={2} /></LineChart>
          : <BarChart data={data}><CartesianGrid stroke={line} strokeDasharray="3 3" /><XAxis dataKey="label" stroke={mute} fontSize={11} interval={0} angle={data.length > 6 ? -25 : 0} textAnchor={data.length > 6 ? 'end' : 'middle'} height={data.length > 6 ? 70 : 30} /><YAxis stroke={mute} fontSize={11} width={80} /><Tooltip /><Bar dataKey="value" name={r.columns[1]} fill={accent} /></BarChart>}
      </ResponsiveContainer>
    </div>
  )
}

export function AskPage() {
  const status = useLoad(() => api.aiStatus(), [])
  const examples = useLoad(() => status.data?.enabled ? api.askExamples() : Promise.resolve([] as string[]), [status.data?.enabled])
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [r, setR] = useState<AskResult | null>(null)
  const ask = async (question: string) => { setQ(question); setBusy(true); try { setR(await api.ask(question)) } finally { setBusy(false) } }
  if (status.data && !status.data.enabled) return <section><PageHeader title="Ask the data" /><Off /></section>
  const s = status.data
  return (
    <section aria-label="Ask the data">
      <PageHeader title="Ask the data" sub="Natural-language questions over the Redshift dw views. The SQL is shown, checked (one SELECT, dw.v_* views only, row limit, timeout) and run as a read-only user." />
      <div className="mb-4 grid gap-3 sm:grid-cols-4">
        <KpiCard label="Model" value={s ? (s.mode === 'mock' ? 'Mocked' : 'Bedrock') : '…'} delta={s?.mode === 'mock' ? 'replays the 30-question eval set' : s?.chatModel} />
        <KpiCard label="Questions left today" value={String(r?.questionsLeft ?? s?.questionsLeft ?? '…')} delta="per-session budget" />
        <KpiCard label="Tokens left today" value={(r?.tokensLeft ?? s?.tokensLeft ?? 0).toLocaleString('en-US')} delta="per-session budget" />
        <KpiCard label="Guards" value={`${s?.rowLimit ?? '…'} rows · ${s?.timeoutSeconds ?? '…'} s`} delta={s?.warehouseConnected ? 'warehouse connected' : 'no warehouse in this environment'} />
      </div>
      <form className="mb-3 flex items-end gap-2" onSubmit={e => { e.preventDefault(); if (q.trim()) ask(q.trim()) }}>
        <TextField label="Question" value={q} onChange={e => setQ(e.target.value)} placeholder="e.g. Sales by channel" className="min-w-[28rem]" data-testid="ask-input" />
        <Button type="submit" disabled={busy || !q.trim()} data-testid="ask-go">{busy ? 'Thinking…' : 'Ask'}</Button>
      </form>
      <div className="mb-5 flex flex-wrap gap-2" aria-label="Examples">
        {(examples.data ?? []).slice(0, 10).map(e => <button key={e} type="button" className="rounded-full border border-line px-3 py-1 text-xs text-mute hover:text-ink" onClick={() => ask(e)} data-testid="ask-example">{e}</button>)}
      </div>
      {r && (
        <div className="space-y-3" data-testid="ask-result">
          {r.blocked && <div className="rounded-aw border border-warn px-4 py-3 text-sm" data-testid="ask-blocked"><StatusPill label="Blocked" tone="warn" /> {r.blocked}</div>}
          {r.error && <div className="rounded-aw border border-line px-4 py-3 text-sm text-mute" data-testid="ask-error">{r.error}</div>}
          {r.sql && (
            <div className="rounded-aw border border-line bg-panel">
              <div className="flex items-center gap-2 border-b border-line px-4 py-2 text-xs text-mute">Generated SQL {r.guardedSql ? <StatusPill label="passed the guard" tone="ok" /> : null}<span className="ml-auto">{r.inputTokens + r.outputTokens} tokens · {r.elapsedMs} ms</span></div>
              <pre className="overflow-x-auto px-4 py-3 text-xs" data-testid="ask-sql">{r.sql}</pre>
            </div>
          )}
          <ResultChart r={r} />
          {r.columns.length > 0 && (
            <div className="overflow-x-auto rounded-aw border border-line">
              <table className="w-full text-sm" data-testid="ask-table">
                <thead><tr>{r.columns.map(c => <th key={c} className="px-3 py-2 text-left text-xs uppercase text-mute">{c}</th>)}</tr></thead>
                <tbody>{r.rows.map((row, i) => <tr key={i} className="border-t border-line">{row.map((v, j) => <td key={j} className="px-3 py-1.5">{fmt(v)}</td>)}</tr>)}</tbody>
              </table>
              {r.truncated && <p className="px-3 py-2 text-xs text-mute">Row limit reached.</p>}
            </div>
          )}
        </div>
      )}
    </section>
  )
}

export function SearchPage() {
  const status = useLoad(() => api.aiStatus(), [])
  const [q, setQ] = useState('')
  const [r, setR] = useState<SearchResult | null>(null)
  const [busy, setBusy] = useState(false)
  if (status.data && !status.data.enabled) return <section><PageHeader title="Semantic search" /><Off /></section>
  const go = async (text: string) => { setQ(text); setBusy(true); try { setR(await api.semanticSearch(text)) } finally { setBusy(false) } }
  return (
    <section aria-label="Semantic search">
      <PageHeader title="Semantic search" sub={`Products ranked by embedding similarity (70 %) and keyword overlap (30 %). ${status.data?.mode === 'mock' ? 'Mock embeddings here (lexical hashing); Titan Text Embeddings v2 + S3 Vectors on AWS.' : 'Titan Text Embeddings v2 + S3 Vectors.'}`} />
      <form className="mb-3 flex items-end gap-2" onSubmit={e => { e.preventDefault(); if (q.trim()) go(q.trim()) }}>
        <TextField label="Describe what you need" value={q} onChange={e => setQ(e.target.value)} placeholder="lightweight bike for climbing" className="min-w-[24rem]" data-testid="search-input" />
        <Button type="submit" disabled={busy || !q.trim()} data-testid="search-go">{busy ? 'Searching…' : 'Search'}</Button>
      </form>
      <div className="mb-5 flex flex-wrap gap-2">{['lightweight bike for climbing', 'waterproof jacket', 'helmet for kids', 'touring frame'].map(x =>
        <button key={x} type="button" className="rounded-full border border-line px-3 py-1 text-xs text-mute hover:text-ink" onClick={() => go(x)}>{x}</button>)}</div>
      {r && (r.hits.length === 0 ? <EmptyState title="No matches" /> : (
        <ul className="grid gap-2" data-testid="search-hits">
          {r.hits.map(h => (
            <li key={h.productId} className="flex items-center gap-3 rounded-aw border border-line bg-panel px-4 py-2.5" data-testid="search-hit">
              <div className="min-w-0 flex-1"><Link className="font-semibold text-accent" to={`/shop/products/${h.productId}`}>{h.name}</Link>
                <div className="text-xs text-mute">{[h.category, h.subcategory, h.model].filter(Boolean).join(' · ')}</div></div>
              <span className="text-sm">{money.format(h.listPrice)}</span>
              <span className="w-40 text-right text-xs text-mute">score {h.score.toFixed(3)} <span className="opacity-70">(vec {h.vectorScore.toFixed(2)} · kw {h.keywordScore.toFixed(2)})</span></span>
            </li>))}
        </ul>))}
    </section>
  )
}
