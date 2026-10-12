import { EmptyState, PageHeader } from '../../components'
import { ComingSoon } from '../ComingSoon'
import type { Data } from '../data'

export function AskTheData({ data }: { data: Data }) {
  return (
    <section aria-label="Ask the data">
      <PageHeader title="Ask the data" sub="Natural-language questions over the Redshift dw schema (optional phase C2-5, Bedrock)." actions={<ComingSoon phase="C2-5" />} />
      <EmptyState title={data.config.askTheData ? 'Enabled' : 'Coming soon (optional C2-5)'}>
        Guarded: read-only Redshift user on dw.* views, SELECT-only allow-list, the generated SQL is always shown. Off by default; enabled per environment.
      </EmptyState>
      <div className="mt-6 grid max-w-2xl gap-2 opacity-60" aria-hidden>
        {['Which territories grew fastest last quarter?', 'Top 10 products by margin in 2014', 'Vendors with the most rejected receipts'].map(q =>
          <div key={q} className="rounded-aw border border-dashed border-line px-4 py-2.5 text-mute">“{q}”</div>)}
      </div>
    </section>
  )
}
