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
type MockOrder = { number: string; status: number; orderDate?: unknown; totalDue?: unknown; shipMethodName?: unknown; lines: { name?: unknown; quantity: number; productId: number }[] }
const stockOf = (pid: number) => (pid === 749 ? 3 : 288)
// facts built from the order shown (like TriageFacts on the server), so the text matches the drawer
export function orderFacts(o: MockOrder): Record<string, unknown> {
  const f: Record<string, unknown> = { 'order.number': o.number, 'order.status': ['', 'In process', 'Approved', 'Backordered'][o.status] ?? String(o.status), 'order.status_age_days': 0,
    'queue.median_age_days': 0, 'order.lines': o.lines.length, 'order.total_due': o.totalDue, 'order.ship_method': o.shipMethodName, 'customer.prior_orders': 0 }
  o.lines.forEach((l, i) => { const s = stockOf(l.productId); Object.assign(f, { [`line${i + 1}.product`]: l.name, [`line${i + 1}.qty`]: l.quantity, [`line${i + 1}.stock`]: s, [`line${i + 1}.short`]: Math.max(0, l.quantity - s) }) })
  f['order.can_ship'] = o.lines.every((_, i) => f[`line${i + 1}.short`] === 0)
  return f
}
export function triageMock(kind: string, o: MockOrder) {
  const f = orderFacts(o); const short = o.lines.findIndex((_, i) => (f[`line${i + 1}.short`] as number) > 0); const n = short + 1
  if (kind === 'explain') return assist('triage', 'triage-explain', short >= 0
    ? `Needs attention: line ${n} ${f[`line${n}.product`]} has ${f[`line${n}.stock`]} in stock but needs ${f[`line${n}.qty`]} [line${n}.short]. This is the customer's first order [customer.prior_orders].`
    : `Ready to approve: all ${f['order.lines']} lines are in stock [order.can_ship]; ${f['line1.product']} needs ${f['line1.qty']} with ${f['line1.stock']} on hand [line1.stock]. It has waited ${f['order.status_age_days']} days vs a queue median of ${f['queue.median_age_days']} [order.status_age_days] [queue.median_age_days]; first order for this customer [customer.prior_orders].`, f)
  if (kind === 'approve-note') return assist('triage', 'triage-approve-note', `Approved ${o.number} [order.number]: all ${f['order.lines']} lines in stock [order.can_ship], ${f['order.total_due']} due [order.total_due], ships via ${f['order.ship_method']} [order.ship_method].`, f)
  return assist('triage', 'triage-backorder-note', short >= 0 ? `Backordered ${o.number} [order.number]: ${f[`line${n}.product`]} short by ${f[`line${n}.short`]} [line${n}.short]. Ship once stock arrives.` : `Backordered ${o.number} [order.number] at the customer's request; all ${f['order.lines']} lines are in stock [order.can_ship].`, f)
}

export function aiMock() {
  let left = 20, tokens = 40000
  const status = () => ({ enabled: true, mode: 'mock', chatModel: 'amazon.nova-pro-v1:0', embeddingModel: 'amazon.titan-embed-text-v2:0', rowLimit: 200, timeoutSeconds: 15,
    questionsLeft: left, tokensLeft: tokens, warehouseConnected: true })
  return (p: string, m: string, url: URL, body: () => Record<string, unknown>): { status?: number; json: unknown } | null => {
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

// C2-6 watchdog stand-in: the same recorded scenarios and rules as the server (Ai/watchdog/*.json, WatchRules.Classify).
const scenarios = {"dlq": {"scenario": "dlq", "status": {"paused": false, "queued": 3, "appliedEvents": 18240, "dlq": 7, "lagMs": {"last": 1300, "p50": 980, "max": 3100}, "source": "replay"}, "changes": [{"table": "Production.Product", "op": "update", "lagMs": 1300}, {"table": "Sales.SalesOrderHeader", "op": "update", "lagMs": 990}], "dlqSamples": [{"table": "Sales.SalesOrderDetail", "op": "insert", "error": "parent ORDER#75124 not found after 5 lookups", "attempts": 5, "position": "0000A8C1:0003B2F0:0004"}, {"table": "Sales.SalesOrderDetail", "op": "insert", "error": "parent ORDER#75124 not found after 5 lookups", "attempts": 5, "position": "0000A8C1:0003B2F0:0005"}, {"table": "Person.EmailAddress", "op": "update", "error": "ConditionalCheckFailed: stale src_lsn", "attempts": 5, "position": "0000A8C2:00001A10:0002"}]}, "lag-spike": {"scenario": "lag-spike", "status": {"paused": false, "queued": 4820, "appliedEvents": 18240, "dlq": 0, "lagMs": {"last": 186000, "p50": 1150, "max": 192000}, "source": "replay"}, "changes": [{"table": "Sales.SalesOrderDetail", "op": "insert", "lagMs": 186000}, {"table": "Sales.SalesOrderDetail", "op": "insert", "lagMs": 184500}, {"table": "Sales.SalesOrderHeader", "op": "update", "lagMs": 181200}], "dlqSamples": []}, "healthy": {"scenario": "healthy", "status": {"paused": false, "queued": 0, "appliedEvents": 18240, "dlq": 0, "lagMs": {"last": 840, "p50": 910, "max": 2400}, "source": "replay"}, "changes": [{"table": "Sales.SalesOrderHeader", "op": "update", "lagMs": 840}, {"table": "Sales.SalesOrderDetail", "op": "insert", "lagMs": 870}, {"table": "Production.ProductInventory", "op": "update", "lagMs": 930}], "dlqSamples": []}, "paused": {"scenario": "paused", "status": {"paused": true, "queued": 1260, "appliedEvents": 18240, "dlq": 0, "lagMs": {"last": 0, "p50": 900, "max": 2500}, "source": "replay"}, "changes": [], "dlqSamples": []}} as Record<string, { scenario: string; status: { paused: boolean; queued: number; appliedEvents: number; dlq: number; lagMs: { last: number; p50: number; max: number }; source: string }; changes: unknown[]; dlqSamples: { error: string }[] }>
const RB = 'docs/runbooks/replication-watchdog.md'
function classify(s: (typeof scenarios)[string]) {
  const st = s.status
  if (st.paused) return { key: 'paused', title: 'The consumer is paused', severity: 'warn', nextStep: 'Resume the consumer (POST /api/resume) once the maintenance is over', runbook: RB + '#paused' }
  if (st.dlq > 0) return s.dlqSamples.some(d => /not found/i.test(d.error))
    ? { key: 'dlq-orphans', title: 'Child rows reached the dead-letter queue before their parent order', severity: 'danger', nextStep: 'Wait for the parent to replicate, then redrive the DLQ', runbook: RB + '#dead-letter-orphans' }
    : { key: 'dlq', title: 'Changes failed to apply and wait in the dead-letter queue', severity: 'danger', nextStep: 'Read the error on each message, fix the cause, then redrive', runbook: RB + '#dead-letter-queue' }
  if (st.lagMs.last > 60000) return st.queued > 1000
    ? { key: 'backlog', title: 'A burst of changes built a backlog: lag is above the 60 s target', severity: 'warn', nextStep: 'Watch the queue drain; scale the consumer if it keeps growing', runbook: RB + '#backlog' }
    : { key: 'slow-apply', title: 'Changes apply slowly: lag is above the 60 s target with a short queue', severity: 'warn', nextStep: 'Check DynamoDB throttling and the consumer logs', runbook: RB + '#slow-apply' }
  return { key: 'healthy', title: 'Replication is healthy', severity: 'ok', nextStep: 'Nothing to do', runbook: RB + '#healthy' }
}
export function watchdogMock(path: string, scenario: string | null) {
  const s = scenarios[scenario ?? 'healthy'] ?? scenarios.healthy; const c = classify(s)
  if (path.endsWith('/explain')) {
    const f = { 'cause.key': c.key, 'cause.title': c.title, 'cause.next_step': c.nextStep, 'cause.runbook': c.runbook, 'status.dlq': s.status.dlq, 'status.queued': s.status.queued,
      'status.lag_last_ms': s.status.lagMs.last, 'status.lag_p50_ms': s.status.lagMs.p50, 'status.lag_max_ms': s.status.lagMs.max }
    return assist('watchdog', 'watchdog-explain', `${c.title} [cause.key]. Replication lag is ${s.status.lagMs.last} ms (p50 ${s.status.lagMs.p50}, max ${s.status.lagMs.max}) [status.lag_last_ms] and ${s.status.dlq} messages wait in the dead-letter queue [status.dlq]. Next step: ${c.nextStep} [cause.next_step] (runbook: ${c.runbook}) [cause.runbook].`, f)
  }
  return { snapshot: s, cause: c, scenarios: ['healthy', 'lag-spike', 'dlq', 'paused'], replay: true }
}
