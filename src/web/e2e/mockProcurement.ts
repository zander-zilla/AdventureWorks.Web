import type { Route } from '@playwright/test'

// Stateful stand-in for /api/v2/back-office/procurement (C2-3), used by mockApi when no real backend is configured.
// The same spec runs against the real app image + DynamoDB Local in after.yml (real INV-02 / PUR-0x data).
type Line = { detailId: number; productId: number; productName: string; orderQty: number; unitPrice: number; lineTotal: number; receivedQty: number; rejectedQty: number; stockedQty: number; dueDate: string }
type Ev = { at: string; action: string; fromStatus: number | null; toStatus: number; actor: string; note: string | null }
type Po = { id: number; number: string; vendorId: number; vendorName: string; employeeId: number | null; employeeName: string | null; status: number; statusText: string; revisionNumber: number;
  version: number; orderDate: string; shipDate: string | null; shipMethodId: number; shipMethodName: string; subTotal: number; taxAmt: number; freight: number; totalDue: number; source: string;
  readOnly: boolean; lines: Line[]; events: Ev[]; actions: string[] }

const now = () => new Date().toISOString().slice(0, 19)
const statusText = ['', 'Pending', 'Approved', 'Rejected', 'Complete']
const vendors = [
  { id: 1492, name: 'Australia Bike Retailer', accountNumber: 'AUSTRALI0001', creditRating: 1, preferred: true, active: true },
  { id: 1496, name: 'Advanced Bicycles', accountNumber: 'ADVANCED0001', creditRating: 1, preferred: true, active: true },
  { id: 1500, name: 'Morgan Bike Accessories', accountNumber: 'MORGANB0001', creditRating: 1, preferred: false, active: true },
]
const vp = (v: (typeof vendors)[number], productId: number, productName: string, price: number, lead: number, onOrder = 0) => ({ vendorId: v.id, vendorName: v.name, productId, productName,
  productNumber: `PN-${productId}`, averageLeadTime: lead, standardPrice: price, lastReceiptCost: price * 1.05, lastReceiptDate: '2014-08-12T00:00:00', minOrderQty: 1, maxOrderQty: 1000,
  onOrderQty: onOrder, unitMeasureCode: 'EA', preferred: v.preferred, active: v.active })
const low = [
  { productId: 4, name: 'Headset Ball Bearings', stockQty: 410, reorderPoint: 600, safetyStockLevel: 800, vendors: [vp(vendors[0], 4, 'Headset Ball Bearings', 41.9, 17), vp(vendors[2], 4, 'Headset Ball Bearings', 44.1, 15)] },
  { productId: 317, name: 'LL Crankarm', stockQty: 300, reorderPoint: 375, safetyStockLevel: 500, vendors: [vp(vendors[0], 317, 'LL Crankarm', 28.5, 15)] },
  { productId: 359, name: 'Thin-Jam Hex Nut 9', stockQty: 640, reorderPoint: 750, safetyStockLevel: 1000, vendors: [vp(vendors[1], 359, 'Thin-Jam Hex Nut 9', 37.7, 19, 400)] },
  { productId: 2, name: 'Bearing Ball', stockQty: 380, reorderPoint: 750, safetyStockLevel: 1000, vendors: [vp(vendors[1], 2, 'Bearing Ball', 39.2, 19)] },
  { productId: 994, name: 'LL Bottom Bracket', stockQty: 0, reorderPoint: 375, safetyStockLevel: 500, vendors: [] },
]

// C2-6 smart reorder stand-in: 24 months of seasonal history per product, forecast = 0.5·last year·growth + 0.5·3-month mean.
const history = (pid: number) => Array.from({ length: 24 }, (_, i) => {
  const d = new Date(Date.UTC(2012, 6 + i, 1)); return { month: d.toISOString().slice(0, 7), qty: Math.round((pid % 7 + 4) * 10 * (1 + 0.35 * Math.sin((i + pid) / 1.9)) * (1 + i / 30)), orders: 10 + (i % 5) } })
function forecastOf(pid: number, lead: number) {
  const h = history(pid); const y = h.map(x => x.qty); const n = y.length
  const last3 = y.slice(n - 3).reduce((a, b) => a + b, 0); const same3 = y.slice(n - 15, n - 12).reduce((a, b) => a + b, 0)
  const g = Math.min(2, Math.max(0.5, last3 / same3)); const step = (w: number[]) => 0.5 * w[w.length - 12] * g + 0.5 * (w.slice(-3).reduce((a, b) => a + b, 0) / 3)
  const monthly = +step(y).toFixed(1); const w = [...y]; const next = [1, 2, 3].map(k => { const f = +step(w).toFixed(1); w.push(f); const d = new Date(Date.UTC(2014, 5 + k, 1)); return { month: d.toISOString().slice(0, 7), qty: f } })
  return { productId: pid, history: h, next, monthly, baseline: +(y.slice(-12).reduce((a, b) => a + b, 0) / 12).toFixed(1), growth: +g.toFixed(2), last3, same3LastYear: same3,
    leadTimeDays: lead, leadTimeDemand: +(monthly * lead / 30).toFixed(1), method: 'seasonal naive with trend (0.5·last year·growth + 0.5·3-month mean)' }
}
type Sug = { productId: number; stockQty: number; safetyStockLevel: number; onOrder: number; suggestedQty: number; note: string | null; vendor: { averageLeadTime: number; minOrderQty: number; maxOrderQty: number } | null }
function smartOf<T extends Sug>(rule: T) {
  const f = forecastOf(rule.productId, rule.vendor?.averageLeadTime ?? 30)
  const need = Math.max(0, Math.ceil(rule.safetyStockLevel + f.leadTimeDemand - rule.stockQty - rule.onOrder))
  const smartQty = rule.vendor ? Math.min(Math.max(need, need ? rule.vendor.minOrderQty : 0), rule.vendor.maxOrderQty) : 0
  const reason = !rule.vendor ? (rule.note ?? 'No active vendor') : smartQty > rule.suggestedQty ? 'Forecast demand is above the reorder rule' : smartQty < rule.suggestedQty ? 'Forecast demand is below the reorder rule' : 'Forecast agrees with the reorder rule'
  return { rule, forecast: f, smartQty, reason }
}
const assistOf = (feature: string, kind: string, text: string, facts: Record<string, unknown>) => ({ feature, kind, text, facts,
  cites: [...text.matchAll(/\[([a-z0-9_.]+)\]/g)].map(m => m[1]), blocked: null, error: null, inputTokens: 610, outputTokens: 90, questionsLeft: 17, tokensLeft: 38000, mode: 'mock' })

export function procurementMock() {
  const pos: Po[] = [
    { id: 4007, number: 'PO004007', vendorId: 1492, vendorName: 'Australia Bike Retailer', employeeId: 251, employeeName: 'Mikael Sandberg', status: 1, statusText: 'Pending', revisionNumber: 4,
      version: 1, orderDate: '2014-09-22T00:00:00', shipDate: null, shipMethodId: 3, shipMethodName: 'OVERSEAS - DELUXE', subTotal: 5036.15, taxAmt: 402.89, freight: 125.9, totalDue: 5564.94,
      source: 'sql', readOnly: true, lines: [], events: [], actions: [] },
  ]
  const stock: Record<number, number> = Object.fromEntries(low.map(l => [l.productId, l.stockQty]))
  let nextPo = 100_001, nextLine = 100_001
  const suggestion = (l: (typeof low)[number]) => {
    const onOrder = l.vendors.reduce((a, v) => a + v.onOrderQty, 0) + pos.filter(p => p.source === 'ddb' && (p.status === 1 || p.status === 2))
      .flatMap(p => p.lines).filter(x => x.productId === l.productId).reduce((a, x) => a + x.orderQty - x.receivedQty, 0)
    const best = [...l.vendors].sort((a, b) => Number(b.preferred) - Number(a.preferred) || a.standardPrice - b.standardPrice)[0] ?? null
    const need = Math.max(0, Math.ceil(l.safetyStockLevel - stock[l.productId] - onOrder))
    const note = !best ? 'No vendor: manufactured in house (production floor, C2-4)' : need === 0 ? 'Covered by quantities already on order' : null
    return { productId: l.productId, name: l.name, productNumber: `PN-${l.productId}`, stockQty: stock[l.productId], reorderPoint: l.reorderPoint, safetyStockLevel: l.safetyStockLevel,
      onOrder, need, suggestedQty: best ? need : 0, note, vendor: best, vendors: l.vendors }
  }
  return async (r: Route, p: string, m: string, body: () => Record<string, unknown>, me: Record<string, unknown>, push: (e: string, s: string, w: string[]) => void) => {
    const roles = me.roles as string[]
    const json = (b: unknown, status = 200) => r.fulfill({ status, json: b })
    const problem = (status: number, title: string) => r.fulfill({ status, contentType: 'application/problem+json', body: JSON.stringify({ title, status }) })
    if (!roles.includes('Buyer') && !roles.includes('PurchasingManager')) return problem(403, 'Forbidden')
    const q = p.replace('/back-office/procurement', '')
    const url = new URL(r.request().url())
    if (q === '/suggestions') return json(low.filter(l => stock[l.productId] < l.reorderPoint).map(suggestion))
    if (q === '/smart-suggestions') return json(low.filter(l => stock[l.productId] < l.reorderPoint).map(l => smartOf(suggestion(l))))
    const ex = q.match(/^\/smart-suggestions\/(\d+)\/explain$/)
    if (ex) { const l = low.find(x => x.productId === Number(ex[1])); if (!l) return problem(404, 'Not found'); const s = smartOf(suggestion(l))
      const facts = { 'suggested.qty': s.smartQty, 'rule.qty': s.rule.suggestedQty, 'forecast.lead_time_days': s.forecast.leadTimeDays, 'forecast.lead_time_demand': s.forecast.leadTimeDemand,
        'history.last3': s.forecast.last3, 'history.same3_last_year': s.forecast.same3LastYear }
      return json(assistOf('reorder', 'reorder-explain', `Suggest ${s.smartQty} [suggested.qty]: forecast demand over the ${s.forecast.leadTimeDays}-day lead time is ${Math.round(s.forecast.leadTimeDemand)} [forecast.lead_time_demand] against the reorder rule's ${s.rule.suggestedQty} [rule.qty]. The last 3 months sold ${s.forecast.last3} units vs ${s.forecast.same3LastYear} a year earlier [history.last3] [history.same3_last_year].`, facts)) }
    const em = q.match(/^\/orders\/(\d+)\/email-draft$/)
    if (em) { const po = pos.find(x => x.id === Number(em[1])); if (!po) return problem(404, 'Not found')
      const facts: Record<string, unknown> = { 'po.number': po.number, 'vendor.name': po.vendorName, 'vendor.contact': 'Paula Moberly', 'po.need_by': po.lines[0]?.dueDate.slice(0, 10), 'po.total': +po.totalDue.toFixed(2), 'buyer.name': po.employeeName }
      po.lines.forEach((l, i) => Object.assign(facts, { [`line${i + 1}.product`]: l.productName, [`line${i + 1}.qty`]: l.orderQty, [`line${i + 1}.unit_price`]: l.unitPrice }))
      const text = `Subject: Purchase order ${po.number} [po.number]\n\nDear Paula Moberly [vendor.contact],\n\nplease confirm our purchase order ${po.number} to ${po.vendorName} [vendor.name]:\n` +
        po.lines.map((l, i) => `- ${l.orderQty} x ${l.productName} at ${l.unitPrice.toFixed(2)} [line${i + 1}.qty]\n`).join('') +
        `\nRequested delivery by ${facts['po.need_by']} [po.need_by]. Order total ${po.totalDue.toFixed(2)} [po.total].\n\nKind regards,\n${po.employeeName} [buyer.name]\nAdventure Works Cycles, purchasing`
      return json(assistOf('reorder', 'po-email', text, facts)) }
    if (q === '/vendors') return json(vendors)
    if (q === '/locations') return json([[1, 'Tool Crib'], [6, 'Miscellaneous Storage'], [7, 'Finished Goods Storage'], [50, 'Subassembly']].map(([id, n]) => ({ locationId: id, name: n, quantity: 0 })))
    const vd = q.match(/^\/vendors\/(\d+)$/)
    if (vd) {
      const v = vendors.find(x => x.id === Number(vd[1]))!; const mine = pos.filter(x => x.vendorId === v.id); const lines = mine.flatMap(x => x.lines)
      const rec = lines.reduce((a, l) => a + l.receivedQty, 0), rej = lines.reduce((a, l) => a + l.rejectedQty, 0), ord = lines.reduce((a, l) => a + l.orderQty, 0)
      return json({ vendor: v, addresses: [{ type: 'Main Office', line1: '28 San Marino Ct.', city: 'Bellingham', state: 'WA', postalCode: '98225', country: 'US' }],
        contacts: [{ name: 'Paula Moberly', type: 'Sales Associate' }], products: low.flatMap(l => l.vendors).filter(x => x.vendorId === v.id),
        performance: { orders: 41 + mine.length, lines: 41 + lines.length, ordered: 2050 + ord, received: 2050 + rec, rejected: 62 + rej, spend: 112_384.5, rejectRate: (62 + rej) / (2050 + rec || 1),
          fillRate: (2050 + rec) / (2050 + ord), onTimeRate: 0.976, avgLeadDays: 9.2 },
        orders: mine.map(x => ({ id: x.id, number: x.number, vendorId: x.vendorId, vendorName: x.vendorName, status: x.status, statusText: x.statusText, orderDate: x.orderDate, totalDue: x.totalDue,
          employeeId: x.employeeId, employeeName: x.employeeName, source: x.source })) })
    }
    const summary = (x: Po) => ({ id: x.id, number: x.number, vendorId: x.vendorId, vendorName: x.vendorName, status: x.status, statusText: x.statusText, orderDate: x.orderDate,
      totalDue: x.totalDue, employeeId: x.employeeId, employeeName: x.employeeName, source: x.source })
    if (q === '/purchase-orders' && m === 'GET') { const s = Number(url.searchParams.get('status') ?? 1); return json({ items: pos.filter(x => x.status === s).map(summary), next: null }) }
    if (q === '/purchase-orders/counts') return json([1, 2].map(s => ({ status: s, text: statusText[s], count: pos.filter(x => x.status === s).length })))
    if (q === '/purchase-orders/mine') return json({ items: pos.filter(x => x.employeeName === me.name).map(summary), next: null })
    if (q === '/purchase-orders' && m === 'POST') {
      const b = body() as { vendorId: number; shipMethodId: number; lines: { productId: number; quantity: number }[] }
      const v = vendors.find(x => x.id === b.vendorId)!; const id = nextPo++
      const lines = b.lines.map(l => { const o = low.flatMap(x => x.vendors).find(x => x.vendorId === v.id && x.productId === l.productId)!
        return { detailId: nextLine++, productId: l.productId, productName: o.productName, orderQty: l.quantity, unitPrice: o.standardPrice, lineTotal: +(o.standardPrice * l.quantity).toFixed(4),
          receivedQty: 0, rejectedQty: 0, stockedQty: 0, dueDate: now().slice(0, 10) + 'T00:00:00' } })
      const sub = +lines.reduce((a, l) => a + l.lineTotal, 0).toFixed(4)
      const po: Po = { id, number: `PO-DDB-${id}`, vendorId: v.id, vendorName: v.name, employeeId: me.email === 'mikael0@adventure-works.com' ? 251 : 250, employeeName: String(me.name), status: 1, statusText: 'Pending',
        revisionNumber: 0, version: 1, orderDate: now(), shipDate: null, shipMethodId: b.shipMethodId, shipMethodName: 'OVERSEAS - DELUXE', subTotal: sub, taxAmt: +(sub * 0.08).toFixed(4),
        freight: +(sub * 0.025).toFixed(4), totalDue: +(sub * 1.105).toFixed(4), source: 'ddb', readOnly: false, lines, events: [{ at: now(), action: 'create', fromStatus: null, toStatus: 1, actor: String(me.email), note: `${lines.length} lines` }],
        actions: ['approve', 'reject'] }
      pos.unshift(po)
      push('po.create', po.number, [`aw-purchasing PO#${id} PO status 1 Pending (PurchaseOrder -> stg.purchase_order)`, ...lines.map(l => `aw-purchasing PO#${id} LINE#${l.detailId} ${l.productName} x${l.orderQty} (PurchaseOrderLine -> stg.purchase_order_line)`),
        `aw-purchasing POSTATUS#1 (OpenPurchaseOrder, PUR-07)`])
      return json(po, 201)
    }
    const tr = q.match(/^\/purchase-orders\/(\d+)(?:\/(\w+))?$/)
    const po = tr && pos.find(x => x.id === Number(tr[1]))
    if (!po) return r.fulfill({ status: 404 })
    if (!tr![2]) return json(po)
    const op = tr![2]; const b = body() as { version: number; lines?: { detailId: number; receivedQty: number; rejectedQty: number; locationId: number | null }[] }
    if ((op === 'approve' || op === 'reject') && !roles.includes('PurchasingManager')) return problem(403, 'Forbidden')
    if (b.version !== po.version) return problem(409, `${po.number} was changed by someone else. Reload and retry.`)
    if (!po.actions.includes(op)) return problem(409, `Cannot ${op} ${po.number}: it is ${po.statusText}.`)
    const from = po.status
    if (op === 'receive') {
      const writes: string[] = []
      for (const x of b.lines ?? []) {
        const l = po.lines.find(y => y.detailId === x.detailId)!
        if (x.receivedQty > l.orderQty - l.receivedQty) return problem(400, `${l.productName}: received ${x.receivedQty} is more than the ${l.orderQty - l.receivedQty} still open.`)
        l.receivedQty += x.receivedQty; l.rejectedQty += x.rejectedQty; l.stockedQty += x.receivedQty - x.rejectedQty; stock[l.productId] = (stock[l.productId] ?? 0) + x.receivedQty - x.rejectedQty
        writes.push(`aw-purchasing PO#${po.id} LINE#${l.detailId} received +${x.receivedQty}, rejected +${x.rejectedQty} (PurchaseOrderLine -> stg.purchase_order_line)`,
          `aw-inventory PRODUCT#${String(l.productId).padStart(6, '0')} INV#${String(x.locationId ?? 6).padStart(3, '0')} +${x.receivedQty - x.rejectedQty} (ProductInventory -> stg.product_inventory)`,
          `aw-inventory PRODUCT#${String(l.productId).padStart(6, '0')} TXN# type P qty ${x.receivedQty - x.rejectedQty} (InventoryTransaction -> stg.inventory_transaction)`)
      }
      po.shipDate = po.shipDate ?? now()
      if (po.lines.every(l => l.receivedQty >= l.orderQty)) { po.status = 4; po.actions = [] }
      push('po.receive', po.number, writes)
    } else {
      po.status = op === 'approve' ? 2 : 3; po.actions = op === 'approve' ? ['receive'] : []
      push(`po.${op}`, po.number, [`aw-purchasing PO#${po.id} PO status ${from}->${po.status} (PurchaseOrder -> stg.purchase_order)`])
    }
    po.statusText = statusText[po.status]; po.version++; po.revisionNumber++
    po.events.push({ at: now(), action: op, fromStatus: from, toStatus: po.status, actor: String(me.email), note: null })
    return json({ order: po, outcome: op === 'receive' ? (po.status === 4 ? 'complete' : 'partially-received') : op === 'approve' ? 'approved' : 'rejected' })
  }
}
