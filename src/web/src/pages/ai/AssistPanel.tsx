import type { ReactNode } from 'react'
import type { AssistResult } from '../../api/client'
import { StatusPill } from '../../components'

// C2-6 shared rendering of an AI explanation / draft: the text with its cited fact keys as chips (hover shows the value),
// a "blocked" or "error" state, and the tokens / budget used. The AI only drafts; actions stay buttons people press.
export function AssistText({ r }: { r: AssistResult }) {
  if (r.blocked) return <p className="text-sm" data-testid="assist-blocked"><StatusPill label="Blocked" tone="warn" /> {r.blocked}</p>
  if (r.error) return <p className="text-sm text-mute" data-testid="assist-error">{r.error}</p>
  const parts: ReactNode[] = []
  const re = /\[([a-z0-9_.]+)\]/g
  let last = 0; let m: RegExpExecArray | null
  const text = r.text ?? ''
  while ((m = re.exec(text))) {
    parts.push(text.slice(last, m.index))
    const key = m[1]
    parts.push(<span key={m.index} title={`${key} = ${JSON.stringify((r.facts as Record<string, unknown>)[key])}`} className="mx-0.5 rounded bg-raised px-1 font-mono text-[10px] text-accent" data-testid="assist-cite">{key}</span>)
    last = m.index + m[0].length
  }
  parts.push(text.slice(last))
  return <p className="whitespace-pre-wrap text-sm leading-relaxed" data-testid="assist-text">{parts}</p>
}

export function AssistBox({ title, r, children }: { title: string; r?: AssistResult | null; children?: ReactNode }) {
  return (
    <div className="flex flex-col gap-2 rounded-aw border border-accent/60 bg-panel p-3" aria-label={title} data-testid="assist-box">
      <div className="flex items-center gap-2 text-xs uppercase text-mute">✦ {title}
        {r && <span className="ml-auto normal-case">{r.mode === 'mock' ? 'mocked model' : 'Bedrock'} · {r.inputTokens + r.outputTokens} tokens · {r.questionsLeft} left today</span>}</div>
      {children}
      {r && <AssistText r={r} />}
    </div>
  )
}

/** Remove the [key] citations for text that goes into a note or an e-mail. */
export const plain = (t?: string | null) => (t ?? '').replace(/\s?\[[a-z0-9_.]+\]/g, '').replace(/\s+([.,;:])/g, '$1').trim()
