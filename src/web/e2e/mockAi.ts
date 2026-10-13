// Stand-in for /api/v2/ai (C2-5) in mock mode: same shapes as the .NET AskService / SemanticSearch with the mocked model.
// Numbers are the AdventureWorksDW totals the warehouse-e2e eval test checks on the Postgres stand-in.
const examples = ['What is the total sales amount across both channels?', 'Sales by channel', 'Sales by calendar year', 'Which product categories sell the most?',
  'Top 10 products by sales amount', 'Top 10 vendors by spend', 'What is the overall scrap rate?', 'On-time production rate by year']
const answers: Record<string, { sql: string; columns: string[]; rows: (string | number)[][]; chart: string | null }> = {
  'sales by channel': { sql: 'SELECT channel, SUM(sales_amount) AS total_sales FROM dw.v_sales GROUP BY channel ORDER BY channel', columns: ['channel', 'total_sales'],
    rows: [['Internet', 29358677.22], ['Reseller', 80450596.98]], chart: 'bar' },
  'sales by calendar year': { sql: 'SELECT calendar_year, SUM(sales_amount) AS total_sales FROM dw.v_sales GROUP BY calendar_year ORDER BY calendar_year', columns: ['calendar_year', 'total_sales'],
    rows: [[2010, 43421.04], [2011, 12075198.38], [2012, 28193631.53], [2013, 40084927.13], [2014, 29514096.12]], chart: 'line' },
}
const hits = [
  { productId: 749, name: 'Road-150 Red, 62', category: 'Bikes', subcategory: 'Road Bikes', model: 'Road-150', listPrice: 3578.27, score: 0.62, vectorScore: 0.6, keywordScore: 0.67 },
  { productId: 771, name: 'Mountain-100 Silver, 38', category: 'Bikes', subcategory: 'Mountain Bikes', model: 'Mountain-100', listPrice: 3399.99, score: 0.51, vectorScore: 0.59, keywordScore: 0.33 },
  { productId: 717, name: 'HL Road Frame - Red, 62', category: 'Components', subcategory: 'Road Frames', model: 'HL Road Frame', listPrice: 1431.5, score: 0.44, vectorScore: 0.53, keywordScore: 0.22 },
]
const key = (q: string) => q.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()

const assist = (feature: string, kind: string, text: string, facts: Record<string, unknown>) => ({ feature, kind, text, facts,
  cites: [...text.matchAll(/\[([a-z0-9_.]+)\]/g)].map(m => m[1]), blocked: null, error: null, inputTokens: 520, outputTokens: 60, questionsLeft: 18, tokensLeft: 38800, mode: 'mock' })
const orderFacts = { 'order.number': 'SO75123', 'order.status': 'In process', 'order.status_age_days': 6, 'queue.median_age_days': 1, 'order.lines': 2, 'order.total_due': 3953.99,
  'order.ship_method': 'CARGO TRANSPORT 5', 'order.can_ship': false, 'customer.prior_orders': 0, 'line1.product': 'HL Road Frame - Red, 62', 'line1.qty': 4, 'line1.stock': 1, 'line1.short': 3,
  'line2.product': 'Sport-100 Helmet, Blue', 'line2.qty': 1, 'line2.stock': 220, 'line2.short': 0 }
export const triageMock = (kind: string) => kind === 'explain'
  ? assist('triage', 'triage-explain', 'Needs attention: line 1 HL Road Frame - Red, 62 has 1 in stock but needs 4 [line1.short]; it has been In process for 6 days vs a queue median of 1 days [order.status_age_days] [queue.median_age_days]; this is the customer\'s first order [customer.prior_orders].', orderFacts)
  : kind === 'approve-note' ? assist('triage', 'triage-approve-note', 'Approved SO75123 [order.number]: all 2 lines in stock [order.can_ship], 3953.99 due [order.total_due], ships via CARGO TRANSPORT 5 [order.ship_method].', orderFacts)
  : assist('triage', 'triage-backorder-note', 'Backordered SO75123 [order.number]: HL Road Frame - Red, 62 short by 3 (in stock 1, ordered 4) [line1.short]. Ship once stock arrives.', orderFacts)

export function aiMock() {
  let left = 20, tokens = 40000
  const status = () => ({ enabled: true, mode: 'mock', chatModel: 'amazon.nova-pro-v1:0', embeddingModel: 'amazon.titan-embed-text-v2:0', rowLimit: 200, timeoutSeconds: 15,
    questionsLeft: left, tokensLeft: tokens, warehouseConnected: true })
  return (p: string, m: string, url: URL, body: () => Record<string, unknown>): { status?: number; json: unknown } | null => {
    const tri = p.match(/^\/back-office\/orders\/\d+\/assist\/([a-z-]+)$/); if (tri) return { json: triageMock(tri[1]) }
    if (p === '/ai/status') return { json: status() }
    if (p === '/ai/examples') return { json: examples }
    if (p === '/ai/search') return { json: { query: url.searchParams.get('q'), mode: 'mock', hits } }
    if (p === '/ai/ask' && m === 'POST') {
      const q = String(body().question ?? ''); left--; tokens -= 950
      const base = { question: q, inputTokens: 900, outputTokens: 50, elapsedMs: 42, questionsLeft: left, tokensLeft: tokens, mode: 'mock', truncated: false, columns: [] as string[], rows: [] as unknown[],
        sql: null as string | null, guardedSql: null as string | null, chart: null as string | null, blocked: null as string | null, error: null as string | null }
      if (/salary|email/i.test(q)) return { json: { ...base, blocked: 'Blocked by the guardrail: this topic is not allowed (personal data, credentials or HR records).' } }
      const a = answers[key(q)]
      if (!a) return { json: { ...base, error: 'The mocked model only knows the 30 eval-set questions; try one of the examples.' } }
      return { json: { ...base, sql: a.sql, guardedSql: `SELECT * FROM (${a.sql}) AS q LIMIT 200`, columns: a.columns, rows: a.rows, chart: a.chart } }
    }
    return null
  }
}
