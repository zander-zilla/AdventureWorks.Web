import type { Page, Route } from '@playwright/test'

// Stateful in-memory stand-in for /api/v2 (C2-2 shop + back office), used when no real backend is configured.
// Shapes follow the generated OpenAPI types; the real flow runs the same spec against the app image (after.yml).
type Order = Record<string, unknown> & { id: number; number: string; status: number; version: number; lines: Line[]; events: Ev[] }
type Line = { lineNo: number; productId: number; name: string; productNumber: string; quantity: number; unitPrice: number; lineTotal: number; unitPriceDiscount: number; specialOfferId: number; carrierTrackingNumber: string | null }
type Ev = { at: string; action: string; fromStatus: number | null; toStatus: number; actor: string; note: string | null }

const now = () => new Date().toISOString().slice(0, 19)
const helmet = { id: 707, name: 'Sport-100 Helmet, Red', productNumber: 'HL-U509-R', color: 'Red', size: null, listPrice: 34.99, standardCost: 13.08, subcategoryId: 31,
  subcategoryName: 'Helmets', categoryId: 4, categoryName: 'Accessories', modelId: 33, modelName: 'Sport-100', weight: null, weightUnit: null, sellStartDate: '2011-05-31T00:00:00',
  sellEndDate: null, stockQty: 288, active: true, thumbnailFileName: null, version: 1, source: 'sql' }
const bike = { ...helmet, id: 749, name: 'Road-150 Red, 62', productNumber: 'BK-R93R-62', listPrice: 3578.27, subcategoryId: 2, subcategoryName: 'Road Bikes', categoryId: 1, categoryName: 'Bikes', weight: 14.68, weightUnit: 'LB', stockQty: 40 }
const offers = [{ id: 1, description: 'No Discount', discountPct: 0, type: 'No Discount', category: 'No Discount', start: '2011-05-01T00:00:00', end: '2014-11-30T00:00:00', minQty: 0, maxQty: null },
  { id: 2, description: 'Volume Discount 11 to 14', discountPct: 0.02, type: 'Volume Discount', category: 'Reseller', start: '2011-05-31T00:00:00', end: '2014-05-30T00:00:00', minQty: 11, maxQty: 14 }]
const methods = [{ id: 1, name: 'XRQ - TRUCK GROUND', shipBase: 3.95, shipRate: 0.99 }, { id: 5, name: 'CARGO TRANSPORT 5', shipBase: 8.99, shipRate: 1.49 }]
const cats = [{ id: 1, name: 'Bikes', subcategories: [{ id: 2, categoryId: 1, name: 'Road Bikes', categoryName: 'Bikes' }] },
  { id: 2, name: 'Components', subcategories: [{ id: 14, categoryId: 2, name: 'Road Frames', categoryName: 'Components' }] },
  { id: 3, name: 'Clothing', subcategories: [{ id: 21, categoryId: 3, name: 'Jerseys', categoryName: 'Clothing' }] },
  { id: 4, name: 'Accessories', subcategories: [{ id: 31, categoryId: 4, name: 'Helmets', categoryName: 'Accessories' }] }]

export async function mockApi(page: Page) {
  let me: Record<string, unknown> = { authenticated: false, name: null, email: null, customerId: null, roles: [] }
  let cart: { productId: number; name: string; productNumber: string; unitPrice: number; quantity: number; added: string }[] = []
  const orders: Order[] = []
  const feed: Record<string, unknown>[] = []
  const reviews: Record<string, unknown>[] = [{ id: 1, date: '2013-09-18T00:00:00', reviewerName: 'John Smith', rating: 5, comments: 'I can’t believe I’m singing the praises of a helmet.', source: 'sql' }]
  let price = { listPrice: helmet.listPrice, version: 1, history: [{ startDate: '2011-05-31T00:00:00', endDate: null as string | null, listPrice: 34.99, source: 'sql' }] }
  const json = (r: Route, body: unknown, status = 200) => r.fulfill({ status, json: body })
  const problem = (r: Route, status: number, title: string) => r.fulfill({ status, contentType: 'application/problem+json', body: JSON.stringify({ title, status }) })
  const quote = (shipId: number) => {
    const m = methods.find(x => x.id === shipId) ?? methods[0]
    const lines = cart.map((c, i) => { const d = c.quantity >= 11 && c.quantity <= 14 ? 0.02 : 0
      return { lineNo: i + 1, productId: c.productId, name: c.name, productNumber: c.productNumber, quantity: c.quantity, unitPrice: c.unitPrice, unitPriceDiscount: d,
        specialOfferId: d ? 2 : 1, offerDescription: d ? 'Volume Discount 11 to 14' : null, lineTotal: +(c.unitPrice * (1 - d) * c.quantity).toFixed(6), taxAllocated: 0, freightAllocated: 0 } })
    const sub = +lines.reduce((a, l) => a + l.lineTotal, 0).toFixed(4)
    const tax = +(sub * 0.088).toFixed(4); const weight = cart.reduce((a, c) => a + (c.productId === 749 ? 14.68 : 1) * c.quantity, 0)
    const freight = +(m.shipBase + m.shipRate * weight).toFixed(4)
    return { lines, subTotal: sub, discount: +(cart.reduce((a, c) => a + c.unitPrice * c.quantity, 0) - sub).toFixed(4), tax: { stateProvinceId: 79, stateCode: 'WA', stateName: 'Washington', territoryId: 1, rate: 0.088, name: 'Washington State Sales Tax' },
      taxAmt: tax, shipMethod: m, weightLb: weight, freight, totalDue: +(sub + tax + freight).toFixed(4), offerDate: '2014-05-01' }
  }
  const push = (event: string, subject: string, writes: string[]) => feed.unshift({ id: `${now()}#${feed.length}`, at: now(), event, subject, actor: String(me.email), writes })

  await page.route('**/api/v2/**', async r => {
    const req = r.request(); const url = new URL(req.url()); const p = url.pathname.replace('/api/v2', ''); const m = req.method()
    const body = () => req.postDataJSON() ?? {}
    if (m !== 'GET' && req.headers()['x-aw-client'] !== 'spa') return problem(r, 400, 'Missing X-AW-Client header')
    const staff = (me.roles as string[]).includes('Fulfilment')
    if (p === '/me') return json(r, me)
    if (p === '/auth/login') {
      const b = body(); if (b.password !== 'Demo!2026') return problem(r, 401, 'Unknown demo customer or wrong password')
      me = String(b.email).startsWith('ops@') ? { authenticated: true, name: 'Ops manager (demo)', email: b.email, customerId: null, roles: ['Fulfilment', 'CatalogAdmin'] }
        : { authenticated: true, name: 'Walter Brian', email: b.email, customerId: 29568, roles: ['Customer'] }
      return json(r, me)
    }
    if (p === '/auth/logout') { me = { authenticated: false, name: null, email: null, customerId: null, roles: [] }; return r.fulfill({ status: 204 }) }
    if (p === '/categories') return json(r, cats)
    const sub = p.match(/^\/subcategories\/(\d+)\/products$/); if (sub) return json(r, Number(sub[1]) === 2 ? [bike] : [{ ...helmet, listPrice: price.listPrice }])
    if (p === '/products') return json(r, { items: [helmet, bike].map(x => ({ id: x.id, name: x.name, productNumber: x.productNumber, listPrice: x.listPrice, active: true })), next: null })
    const det = p.match(/^\/products\/(\d+)\/detail$/)
    if (det) { const x = Number(det[1]) === 749 ? bike : { ...helmet, listPrice: price.listPrice, version: price.version }; return json(r, { product: x, offers, priceHistory: price.history }) }
    if (/^\/products\/\d+\/reviews$/.test(p)) {
      if (m === 'GET') return json(r, reviews)
      if (!me.customerId) return problem(r, 401, 'Sign in required')
      if (reviews.some(x => x.reviewerName === me.name)) return problem(r, 409, 'You have already reviewed this product.')
      const b = body(); const rv = { id: 10001 + reviews.length, date: now(), reviewerName: me.name, rating: b.rating, comments: b.comments, source: 'ddb' }
      reviews.unshift(rv); push('review.added', 'product 707', ['aw-catalog PRODUCT#000707 REVIEW# (ProductReview -> stg.product_review)']); return json(r, rv, 201)
    }
    if (p === '/ship-methods') return json(r, methods)
    if (p.startsWith('/cart') || p.startsWith('/checkout') || p === '/orders' || /^\/orders\/\d+$/.test(p)) {
      if (!me.customerId) return problem(r, me.authenticated ? 403 : 401, 'Sign in required')
      if (p === '/cart') return json(r, cart.map(c => ({ ...c, lineTotal: c.unitPrice * c.quantity })))
      if (p === '/cart/items') { const b = body(); const x = b.productId === 749 ? bike : helmet; const e = cart.find(c => c.productId === x.id)
        if (e) e.quantity += b.quantity; else cart.push({ productId: x.id, name: x.name, productNumber: x.productNumber, unitPrice: x.id === 707 ? price.listPrice : x.listPrice, quantity: b.quantity, added: now() })
        return json(r, cart) }
      const ci = p.match(/^\/cart\/items\/(\d+)$/)
      if (ci) { const q = m === 'DELETE' ? 0 : body().quantity; cart = cart.map(c => (c.productId === Number(ci[1]) ? { ...c, quantity: q } : c)).filter(c => c.quantity > 0); return json(r, cart) }
      if (p === '/checkout/quote') return json(r, quote(Number(url.searchParams.get('shipMethodId') ?? 1)))
      if (p === '/checkout') {
        const q = quote(body().shipMethodId ?? 1); const id = 1_000_000_001 + orders.length
        const o: Order = { id, number: `SO-DDB-${id}`, customerId: 29568, customerName: 'Walter Brian', orderDate: now(), status: 1, version: 1, revisionNumber: 1, subTotal: q.subTotal, taxAmt: q.taxAmt,
          freight: q.freight, totalDue: q.totalDue, shipTo: '7943 Walnut Ave, Renton WA 98055', source: 'ddb', territoryId: 1, shipMethodId: q.shipMethod.id, shipMethodName: q.shipMethod.name,
          carrierTrackingNumber: null, shipDate: null, lines: q.lines.map(l => ({ ...l, carrierTrackingNumber: null })), events: [{ at: now(), action: 'place', fromStatus: null, toStatus: 1, actor: String(me.email), note: null }] }
        orders.unshift(o); cart = []
        push('order.placed', o.number, [`aw-sales ORDER#${id} ORDER (Order -> stg.order)`, `aw-sales ORDER#${id} LINE#0000001..${String(o.lines.length).padStart(7, '0')} (OrderLine -> stg.order_line)`])
        return json(r, o, 201)
      }
      if (p === '/orders') return json(r, { items: orders, next: null })
      const mo = orders.find(o => o.id === Number(p.split('/')[2])); return mo ? json(r, mo) : r.fulfill({ status: 404 })
    }
    if (p.startsWith('/back-office')) {
      if (!me.authenticated) return problem(r, 401, 'Sign in required')
      if (!staff) return problem(r, 403, 'Forbidden')
      if (p === '/back-office/orders') { const s = Number(url.searchParams.get('status') ?? 1); return json(r, { items: orders.filter(o => o.status === s), next: null }) }
      if (p === '/back-office/orders/counts') return json(r, [1, 2, 3].map(s => ({ status: s, text: ['', 'In process', 'Approved', 'Backordered'][s], count: orders.filter(o => o.status === s).length })))
      if (p === '/back-office/changes') return json(r, feed)
      if (p === '/back-office/orders/bulk-approve') return json(r, body().orders.map((x: { id: number }) => { const o = orders.find(y => y.id === x.id)!; o.status = 2; o.version++; return { id: x.id, ok: true, message: 'approved' } }))
      const pr = p.match(/^\/back-office\/products\/(\d+)\/price$/)
      if (pr) { const b = body(); if (b.version !== price.version) return problem(r, 409, 'Changed meanwhile'); const d = now().slice(0, 10)
        price = { listPrice: b.listPrice, version: price.version + 1, history: [...price.history.map(h => (h.endDate ? h : { ...h, endDate: `${d}T00:00:00` })), { startDate: `${d}T00:00:00`, endDate: null, listPrice: b.listPrice, source: 'ddb' }] }
        push('product.price', 'HL-U509-R', ['aw-catalog PRODUCT#000707 PRICE# (ListPriceHistory -> stg.list_price_history -> dw.dim_product SCD2)'])
        return json(r, { product: { ...helmet, listPrice: price.listPrice, version: price.version }, offers: [], priceHistory: price.history }) }
      const tr = p.match(/^\/back-office\/orders\/(\d+)(?:\/(\w+))?$/)
      const o = tr && orders.find(x => x.id === Number(tr[1]))
      if (!o) return r.fulfill({ status: 404 })
      const allowed: Record<number, string[]> = { 1: ['approve', 'reject', 'backorder', 'cancel'], 2: ['backorder', 'ship', 'cancel'], 3: ['ship', 'cancel'] }
      if (!tr![2]) return json(r, { order: o, statusText: '', actions: allowed[o.status] ?? [], stock: o.lines.map(l => ({ productId: l.productId, onHand: 288, reorderPoint: 3, locations: [{ locationId: 7, name: 'Finished Goods Storage', quantity: 288 }] })) })
      const op = tr![2]; const b = body()
      if (b.version !== o.version) return problem(r, 409, `${o.number} was changed by someone else. Reload and retry.`)
      if (!(allowed[o.status] ?? []).includes(op)) return problem(r, 409, `Cannot ${op} ${o.number}`)
      const to = { approve: 2, reject: 4, backorder: 3, ship: 5, cancel: 6 }[op]!
      o.events.push({ at: now(), action: op, fromStatus: o.status, toStatus: to, actor: String(me.email), note: op === 'ship' ? `${b.trackingNumber}` : null })
      o.status = to; o.version++
      if (op === 'ship') { o.carrierTrackingNumber = b.trackingNumber; o.lines = o.lines.map(l => ({ ...l, carrierTrackingNumber: b.trackingNumber }))
        push('order.ship', o.number, [`aw-sales ORDER#${o.id} ORDER status 2->5, ship_date, tracking (Order -> stg.order)`, ...o.lines.map(l => `aw-inventory PRODUCT#000${l.productId} TXN# type S qty ${l.quantity} (InventoryTransaction -> stg.inventory_transaction)`)]) }
      else push(`order.${op}`, o.number, [`aw-sales ORDER#${o.id} ORDER status -> ${to} (Order -> stg.order)`])
      return json(r, { order: o, outcome: op === 'ship' ? 'shipped' : op, shortages: [] })
    }
    return r.fulfill({ status: 404 })
  })
}
