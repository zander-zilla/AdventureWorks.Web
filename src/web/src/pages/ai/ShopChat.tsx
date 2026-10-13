import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { api, ApiError, money, type ChatResponse } from '../../api/client'
import { useLoad } from '../../api/useLoad'
import { Button } from '../../components'
import { AssistText } from './AssistPanel'

type Turn = { q: string; r?: ChatResponse; error?: string }

/** C2-6 shopper chat (enable_ai): the server picks the tools (search, product details, customers also bought) and the
 *  model writes a short grounded reply; product cards come from the tool results. Shop guardrail, 10 questions a day. */
export function ShopChat({ productId }: { productId?: number }) {
  const ai = useLoad(() => api.aiStatus(), [])
  const [open, setOpen] = useState(false)
  const [turns, setTurns] = useState<Turn[]>([])
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  if (!ai.data?.enabled) return null
  const left = turns.length ? turns[turns.length - 1].r?.turnsLeft : undefined
  const send = async (e: FormEvent) => {
    e.preventDefault()
    const text = q.trim(); if (!text) return
    setBusy(true); setQ('')
    try { const r = await api.shopChat(text, productId); setTurns(t => [...t, { q: text, r }]) }
    catch (err) { setTurns(t => [...t, { q: text, error: err instanceof ApiError ? err.message : 'The assistant is not available' }]) }
    finally { setBusy(false) }
  }
  if (!open) return (
    <button type="button" onClick={() => setOpen(true)} data-testid="chat-open"
      className="fixed right-6 bottom-6 z-30 rounded-full bg-accent px-4 py-3 text-sm font-semibold text-accent-ink shadow-lg">✦ Ask the shop assistant</button>)
  return (
    <section className="fixed right-6 bottom-6 z-30 flex max-h-[80vh] w-[26rem] flex-col rounded-aw border border-accent/60 bg-panel shadow-2xl" aria-label="Shop assistant" data-testid="chat">
      <header className="flex items-center gap-2 border-b border-line px-4 py-2 text-sm">
        <b>✦ Shop assistant</b><span className="text-xs text-mute">{left !== undefined ? `${left} questions left today` : 'answers from our catalog only'}</span>
        <button type="button" className="ml-auto text-mute hover:text-ink" aria-label="Close chat" onClick={() => setOpen(false)}>×</button>
      </header>
      <ol className="flex flex-1 flex-col gap-3 overflow-y-auto p-4" data-testid="chat-log">
        {turns.length === 0 && <li className="text-sm text-mute">Ask about bikes, components, clothing or accessories, for example “a light helmet for commuting” or “what goes with this?”.</li>}
        {turns.map((t, i) => (
          <li key={i} className="flex flex-col gap-2" data-testid="chat-turn">
            <p className="self-end rounded-aw bg-raised px-3 py-1.5 text-sm">{t.q}</p>
            {t.error && <p className="text-sm text-mute">{t.error}</p>}
            {t.r && <AssistText r={t.r.answer} />}
            {t.r && t.r.cards.length > 0 && (
              <ul className="grid grid-cols-2 gap-2">{t.r.cards.slice(0, 6).map(c => (
                <li key={c.source + c.productId}><Link to={`/shop/products/${c.productId}`} className="block rounded-aw border border-line bg-bg p-2 text-xs hover:border-accent" data-testid="chat-card">
                  <span className="block font-semibold text-ink">{c.name}</span><span className="text-mute">{money.format(c.listPrice)} · {c.source === 'also-bought' ? 'also bought' : c.category ?? 'match'}</span></Link></li>))}
              </ul>)}
          </li>))}
      </ol>
      <form onSubmit={send} className="flex gap-2 border-t border-line p-3">
        <input aria-label="Message the shop assistant" value={q} maxLength={300} onChange={e => setQ(e.target.value)} disabled={busy || left === 0}
          className="flex-1 rounded-aw border border-line bg-bg px-3 py-1.5 text-sm text-ink" placeholder={left === 0 ? 'Daily limit reached' : 'Ask about our products…'} data-testid="chat-input" />
        <Button size="sm" type="submit" disabled={busy || left === 0} data-testid="chat-send">Send</Button>
      </form>
    </section>
  )
}

/** C2-6 customers also bought (CAT-12): derived co-purchase ranks; shown whether or not the AI layer is on. */
export function AlsoBoughtShelf({ id }: { id: number }) {
  const a = useLoad(() => api.alsoBought(id), [id])
  if (!a.data || a.data.length === 0) return null
  return (
    <section className="mt-6" aria-labelledby="also-h" data-testid="also-bought">
      <h2 id="also-h" className="mb-3 font-display text-xl font-semibold">Customers also bought</h2>
      <ul className="grid grid-cols-6 gap-3">{a.data.map(x => (
        <li key={x.productId}><Link to={`/shop/products/${x.productId}`} className="block h-full rounded-aw border border-line bg-panel p-3 text-sm hover:border-accent" data-testid="also-item">
          <span className="block font-semibold">{x.name}</span><span className="text-xs text-mute">{money.format(x.listPrice)} · in {x.orders} orders together</span></Link></li>))}
      </ul>
    </section>)
}
