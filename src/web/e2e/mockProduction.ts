import type { Route } from '@playwright/test'

// Stateful stand-in for /api/v2/back-office/production (C2-4), used by mockApi when no real backend is configured.
// The same spec runs against the real app image + DynamoDB Local in after.yml (real INV-04/05/06 data).
type Step = { operationSequence: number; locationId: number; locationName: string; scheduledStartDate: string | null; scheduledEndDate: string | null; actualStartDate: string | null;
  actualEndDate: string | null; actualResourceHrs: number | null; plannedCost: number | null; actualCost: number | null; late: boolean; done: boolean }
type Wo = { id: number; number: string; productId: number; productName: string; orderQty: number; stockedQty: number; scrappedQty: number; startDate: string; endDate: string | null;
  dueDate: string; state: string; scrapReason: string | null; source: string }
type Detail = { order: Wo; version: number; readOnly: boolean; actions: string[]; routing: Step[]; events: { at: string; action: string; actor: string; note: string | null }[] }

const now = () => new Date().toISOString().slice(0, 19)
const addDays = (s: string, d: number) => new Date(Date.parse(s + 'Z') + d * 86_400_000).toISOString().slice(0, 19)
const reasons = ['Brake assembly not as ordered', 'Color incorrect', 'Drill pattern incorrect', 'Gouge in metal', 'Handling damage', 'Paint process failed', 'Thermoform temperature too low', 'Wheel misaligned']
  .map((name, i) => ({ id: i + 1, name }))
const centres: Record<number, [string, number]> = { 10: ['Frame Forming', 22.5], 20: ['Frame Welding', 25], 30: ['Debur and Polish', 14.5], 40: ['Paint', 15.75], 50: ['Subassembly', 12.25], 60: ['Final Assembly', 12.25] }
const assemblies = [{ productId: 749, name: 'Road-150 Red, 62' }, { productId: 771, name: 'Mountain-100 Silver, 38' }, { productId: 717, name: 'HL Road Frame - Red, 62' }]
const comps = [{ productId: 813, name: 'HL Road Handlebars', per: 1 }, { productId: 820, name: 'HL Road Front Wheel', per: 1 }, { productId: 828, name: 'HL Road Rear Wheel', per: 1 },
  { productId: 894, name: 'Rear Derailleur', per: 1 }, { productId: 945, name: 'Front Derailleur', per: 1 }, { productId: 952, name: 'Chain', per: 1 }, { productId: 717, name: 'HL Road Frame - Red, 62', per: 1 }]
const state = (end: string | null, due: string) => (end == null ? 'Open' : end.slice(0, 10) <= due.slice(0, 10) ? 'Closed on time' : 'Closed late')
const step = (seq: number, loc: number, start: string, done = false): Step => ({ operationSequence: seq, locationId: loc, locationName: centres[loc][0], scheduledStartDate: start,
  scheduledEndDate: addDays(start, 1), actualStartDate: done ? start : null, actualEndDate: done ? addDays(start, seq === 2 ? 1.6 : 0.9) : null, actualResourceHrs: done ? 4 : null,
  plannedCost: 4 * centres[loc][1], actualCost: done ? 4 * centres[loc][1] : null, late: done && seq === 2, done })

function history(): Detail[] {
  return Array.from({ length: 30 }, (_, i) => {
    const id = 71_200 + i; const start = `2014-05-${String(1 + (i % 25)).padStart(2, '0')}T00:00:00`; const due = addDays(start, 11); const end = addDays(start, i % 4 === 0 ? 13 : 9)
    const scrap = i % 7 === 0 ? 2 : 0; const a = assemblies[i % 3]
    return { order: { id, number: `WO0${id}`, productId: a.productId, productName: a.name, orderQty: 40, stockedQty: 40 - scrap, scrappedQty: scrap, startDate: start, endDate: end, dueDate: due,
      state: state(end, due), scrapReason: scrap ? reasons[i % 8].name : null, source: 'sql' }, version: 1, readOnly: true, actions: [], events: [],
      routing: i % 3 === 2 ? [10, 20, 30, 40].map((l, k) => step(k + 1, l, addDays(start, k), true)) : [50, 60].map((l, k) => step(k + 1, l, addDays(start, k), true)) }
  })
}

const months = (from: string, to: string) => { const out: string[] = []; let [y, m] = from.split('-').map(Number); const [ty, tm] = to.split('-').map(Number)
  while (y < ty || (y === ty && m <= tm)) { out.push(`${y}-${String(m).padStart(2, '0')}`); m++; if (m > 12) { m = 1; y++ } } return out }

export function productionMock() {
  const wos: Detail[] = history()
  let nextId = 100_000
  const summary = (d: Detail) => d.order
  const tree = (id: number, level = 0): Record<string, unknown> => {
    const a = assemblies.find(x => x.productId === id); const c = comps.find(x => x.productId === id)
    const kids = id === 749 || id === 771 ? comps : id === 717 ? [{ productId: 331, name: 'Long Steel Rod', per: 2.5 }, { productId: 486, name: 'Paint - Red', per: 1 }] : []
    return { productId: id, name: a?.name ?? c?.name ?? `Product ${id}`, perAssemblyQty: (c as { per?: number } | undefined)?.per ?? 1, unitMeasureCode: 'EA', level, startDate: '2010-05-26T00:00:00', endDate: null,
      children: level >= 3 ? [] : kids.map(k => ({ ...tree(k.productId, level + 1), perAssemblyQty: k.per })) }
  }
  const plan = (pid: number, qty: number) => {
    const a = assemblies.find(x => x.productId === pid)!; const start = now().slice(0, 10) + 'T00:00:00'
    const locs = a.name.includes('Frame') ? [10, 20, 30, 40] : [50, 60]
    const routing = locs.map((l, k) => step(k + 1, l, addDays(start, k + 1)))
    const cs = (pid === 717 ? [{ productId: 331, name: 'Long Steel Rod', per: 2.5 }] : comps).map(c => ({ productId: c.productId, name: c.name, perAssemblyQty: c.per, required: Math.ceil(c.per * qty), onHand: 120, locationId: 6, available: true }))
    return { productId: pid, name: a.name, orderQty: qty, startDate: addDays(start, 1), dueDate: addDays(start, locs.length + 3), routing, components: cs, feasible: true, problems: [] }
  }
  const actionsOf = (d: Detail) => (d.readOnly || d.order.endDate ? [] : d.routing.some(s => !s.done) ? ['record-operation', 'complete'] : ['complete'])

  return (r: Route, p: string, m: string, body: () => Record<string, unknown>, me: Record<string, unknown>, push: (e: string, s: string, w: string[]) => void) => {
    const url = new URL(r.request().url())
    const json = (b: unknown, status = 200) => r.fulfill({ status, json: b })
    const problem = (status: number, title: string) => r.fulfill({ status, contentType: 'application/problem+json', body: JSON.stringify({ title, status }) })
    const roles = me.roles as string[]
    if (!roles.some(x => x !== 'Customer')) return problem(403, 'Forbidden')
    const sup = roles.includes('ProductionSupervisor')
    const q = p.replace('/back-office/production', '')
    if (q === '/scrap-reasons') return json(reasons)
    if (q === '/assemblies') return json(assemblies)
    if (q === '/kpis') {
      const ms = months(url.searchParams.get('from') ?? '2013-07', url.searchParams.get('to') ?? '2014-06')
      const rows = ms.map((mo, i) => { const n = mo >= '2020' ? wos.filter(w => w.order.source === 'ddb' && w.order.dueDate.startsWith(mo)).length : 1800 + ((i * 137) % 400)
        const closed = mo >= '2020' ? wos.filter(w => w.order.source === 'ddb' && w.order.endDate && w.order.dueDate.startsWith(mo)).length : n
        return { month: mo, workOrders: n, closed, onTime: Math.round(closed * (0.62 + ((i * 7) % 15) / 100)), orderQty: n * 62, scrappedQty: Math.round(n * 62 * (0.0018 + ((i * 3) % 5) / 2000)),
          scrapRate: 0, onTimeRate: 0 } }).map(x => ({ ...x, scrapRate: x.orderQty ? +(x.scrappedQty / x.orderQty).toFixed(4) : 0, onTimeRate: x.closed ? +(x.onTime / x.closed).toFixed(4) : 0 }))
      const oq = rows.reduce((a, x) => a + x.orderQty, 0); const sq = rows.reduce((a, x) => a + x.scrappedQty, 0); const c = rows.reduce((a, x) => a + x.closed, 0); const on = rows.reduce((a, x) => a + x.onTime, 0)
      return json({ from: ms[0], to: ms[ms.length - 1], months: rows, scrapReasons: reasons.map((x, i) => ({ reason: x.name, workOrders: 40 + i * 3, scrappedQty: 900 - i * 70 })),
        workOrders: rows.reduce((a, x) => a + x.workOrders, 0), orderQty: oq, scrappedQty: sq, scrapRate: oq ? +(sq / oq).toFixed(4) : 0, onTimeRate: c ? +(on / c).toFixed(4) : 0,
        open: wos.filter(w => !w.order.endDate).length })
    }
    if (q === '/work-orders/open') return json(wos.filter(w => !w.order.endDate).map(summary))
    if (q === '/work-orders' && m === 'GET') {
      const mo = url.searchParams.get('month') ?? '2014-06'; const items = wos.filter(w => w.order.dueDate.startsWith(mo)).map(summary)
      return json({ month: mo, items, total: items.length, truncated: false })
    }
    const pl = q.match(/^\/plan\/(\d+)$/); if (pl) return sup ? json(plan(Number(pl[1]), Number(url.searchParams.get('qty') ?? 1))) : problem(403, 'Forbidden')
    const bm = q.match(/^\/bom\/(\d+)$/); if (bm) return json({ root: tree(Number(bm[1])), asOf: now().slice(0, 10), queries: 9, nodes: 10, depthCapped: false })
    const wu = q.match(/^\/where-used\/(\d+)$/)
    if (wu) { const id = Number(wu[1]); const c = comps.find(x => x.productId === id)
      return json({ root: { productId: id, name: c?.name ?? `Product ${id}`, perAssemblyQty: 1, unitMeasureCode: 'EA', level: 0, startDate: null, endDate: null,
        children: assemblies.slice(0, 2).map(a => ({ productId: a.productId, name: a.name, perAssemblyQty: 1, unitMeasureCode: 'EA', level: 1, startDate: '2010-05-26T00:00:00', endDate: null, children: [] })) },
        asOf: now().slice(0, 10), queries: 3, nodes: 3, depthCapped: false }) }
    if (q === '/work-orders' && m === 'POST') {
      if (!sup) return problem(403, 'Forbidden')
      const b = body(); const pn = plan(Number(b.productId), Number(b.orderQty)); const id = nextId++
      const d: Detail = { order: { id, number: `WO-DDB-${id}`, productId: pn.productId, productName: pn.name, orderQty: pn.orderQty, stockedQty: 0, scrappedQty: 0, startDate: pn.startDate,
        endDate: null, dueDate: pn.dueDate, state: 'Open', scrapReason: null, source: 'ddb' }, version: 1, readOnly: false, actions: [], routing: pn.routing,
        events: [{ at: now(), action: 'create', actor: String(me.email), note: `${pn.orderQty} x ${pn.name}` }] }
      d.actions = actionsOf(d); wos.unshift(d)
      push('wo.create', d.order.number, [`aw-inventory WO#${id} WO (WorkOrder -> stg.work_order), GSI2 WODUE#${pn.dueDate.slice(0, 7)} (INV-06)`, `aw-inventory WO#${id} ROUTING x${pn.routing.length}`])
      return json(d, 201)
    }
    const wm = q.match(/^\/work-orders\/(\d+)(?:\/(operations|complete))?$/)
    const d = wm && wos.find(x => x.order.id === Number(wm[1]))
    if (!d) return r.fulfill({ status: 404 })
    if (!wm![2]) return json(d)
    if (!sup) return problem(403, 'Forbidden')
    const b = body()
    if (b.version !== d.version) return problem(409, `${d.order.number} was changed by someone else. Reload and retry.`)
    if (wm![2] === 'operations') {
      const s = d.routing.find(x => !x.done)!; const prev = d.routing.filter(x => x.done).map(x => x.actualEndDate!).sort().pop() ?? d.order.startDate
      Object.assign(s, { actualStartDate: prev < now() ? prev : now(), actualEndDate: now(), actualResourceHrs: b.resourceHrs, actualCost: Number(b.resourceHrs) * centres[s.locationId][1], done: true, late: now() > s.scheduledEndDate! })
      d.version++; d.events.push({ at: now(), action: 'operation', actor: String(me.email), note: `op ${s.operationSequence} ${s.locationName}: ${b.resourceHrs} h` }); d.actions = actionsOf(d)
      push('wo.operation', d.order.number, [`aw-inventory WO#${d.order.id} ROUTING#00${s.operationSequence} actual ${b.resourceHrs} h (WorkOrderRouting -> stg.work_order_routing)`])
      return json({ order: d, outcome: 'operation-recorded' })
    }
    const scrap = Number(b.scrappedQty ?? 0)
    if (scrap > 0 && !b.scrapReasonId) return problem(400, 'A scrap reason is required when units are scrapped.')
    for (const s of d.routing.filter(x => !x.done)) Object.assign(s, { actualStartDate: now(), actualEndDate: now(), actualResourceHrs: 4, actualCost: 4 * centres[s.locationId][1], done: true })
    const end = now()
    Object.assign(d.order, { endDate: end, stockedQty: d.order.orderQty - scrap, scrappedQty: scrap, state: state(end, d.order.dueDate),
      scrapReason: scrap ? reasons.find(x => x.id === b.scrapReasonId)?.name ?? null : null })
    d.version++; d.actions = []
    d.events.push({ at: end, action: 'complete', actor: String(me.email), note: `stocked ${d.order.stockedQty} → Finished Goods Storage${scrap ? `, scrapped ${scrap} (${d.order.scrapReason})` : ''}` })
    const pn = plan(d.order.productId, d.order.orderQty)
    push('wo.complete', d.order.number, [`aw-inventory WO#${d.order.id} WO end, stocked ${d.order.stockedQty}, scrapped ${scrap}`,
      `aw-inventory PRODUCT#000${d.order.productId} INV#007 +${d.order.stockedQty}, TXN# type W +${d.order.stockedQty} (product in)`,
      ...pn.components.map(c => `aw-inventory PRODUCT#000${c.productId} INV#006 -${c.required}, TXN# type W -${c.required} (component consumed, inferred)`)])
    return json({ order: d, outcome: d.order.state === 'Closed on time' ? 'closed-on-time' : 'closed-late' })
  }
}
