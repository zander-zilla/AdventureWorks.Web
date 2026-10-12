import { StatusPill } from '../components'

/** Marks anything that only arrives in a later Chapter 2 phase. */
export function ComingSoon({ phase }: { phase: string }) {
  return <span data-testid="coming-soon"><StatusPill tone="warn" label={`Coming soon · ${phase}`} /></span>
}
