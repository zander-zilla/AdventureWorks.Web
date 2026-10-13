import { EmptyState, PageHeader, StatusPill } from '../../components'
import type { Data } from '../data'

// C2-5 is built and tested (mocked model + 30-question eval set in CI) but the AI layer is off by default (Terraform enable_ai),
// so the showcase explains it and links to the app, which says whether it is enabled in this environment.
export function AskTheData({ data }: { data: Data }) {
  const spa = data.config.spaUrl?.replace(/\/?$/, '/') ?? ''
  return (
    <section aria-label="Ask the data">
      <PageHeader title="Ask the data" sub="Natural-language questions over the Redshift dw views and semantic product search (C2-5, Amazon Bedrock)."
        actions={<StatusPill label={data.config.askTheData ? 'Live · C2-5' : 'Built in C2-5 · off by default'} tone={data.config.askTheData ? 'ok' : 'neutral'} />} />
      <EmptyState title={data.config.askTheData ? 'Enabled in this environment' : 'Built in C2-5 · off by default (enable_ai)'}>
        The model writes one SELECT over dw.v_sales, dw.v_vendor_performance and dw.v_production_scrap_on_time; the app checks it (SELECT only, views only, no comments
        or second statement), adds a row limit and runs it as a read-only Redshift user with a timeout, and always shows the SQL. A Bedrock guardrail blocks personal
        data and prompt attacks; each session has a daily question and token budget; prompts and answers are logged. CI uses a mocked model and runs the 30-question
        eval set against the warehouse stand-in.
      </EmptyState>
      {spa && <p className="mt-4 flex gap-4 text-sm"><a className="text-accent" href={spa + 'back-office/ask'} target="_blank" rel="noreferrer">Open ask the data ↗</a>
        <a className="text-accent" href={spa + 'shop/search'} target="_blank" rel="noreferrer">Open semantic search ↗</a></p>}
      <div className="mt-6 grid max-w-2xl gap-2" aria-label="Eval set examples">
        {['Sales by channel', 'Top 10 vendors by spend', 'Three months with the worst on-time production'].map(q =>
          <div key={q} className="rounded-aw border border-dashed border-line px-4 py-2.5 text-mute">“{q}”</div>)}
      </div>
    </section>
  )
}
