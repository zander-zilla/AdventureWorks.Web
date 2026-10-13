// /api/v2 client GENERATED from the OpenAPI document (C2-2, as John decided in C2-0): `npm run gen:api` turns
// openapi/v2.json (written by the .NET API tests in CI, which fail if the committed copy is stale) into
// src/api/schema.d.ts; openapi-fetch gives typed paths, params and bodies. Nothing here is hand-typed.
import createClient, { type Middleware } from 'openapi-fetch'
import type { components, paths } from './schema'

type S = components['schemas']
export type Me = S['MeDto']
export type ProductSummary = S['ProductSummary']
export type ProductPage = S['ProductPage']
export type Product = S['Product']
export type ProductDetail = S['ProductDetail']
export type Category = S['Category']
export type CartLine = S['CartLine']
export type Quote = S['Quote']
export type ShipMethod = S['ShipMethodInfo']
export type Order = S['Order']
export type OrderPage = S['OrderPage']
export type OrderEvent = S['OrderEvent']
export type BackOfficeOrder = S['BackOfficeOrder']
export type TransitionResult = S['TransitionResult']
export type FeedEntry = S['FeedEntry']
export type Review = S['Review']
export type StatusCount = S['StatusCount']
export type BulkResult = S['BulkResult']
export type ReorderSuggestion = S['ReorderSuggestion']
export type VendorSummary = S['VendorSummary']
export type VendorDetail = S['VendorDetail']
export type VendorProduct = S['VendorProductInfo']
export type PurchaseOrder = S['PurchaseOrder']
export type PurchaseOrderSummary = S['PurchaseOrderSummary']
export type PoResult = S['PoResult']
export type WorkOrderSummary = S['WorkOrderSummary']
export type WorkOrderDetail = S['WorkOrderDetail']
export type WorkOrderList = S['WorkOrderList']
export type RoutingStep = S['RoutingStep']
export type BomNode = S['BomNode']
export type BomTree = S['BomTree']
export type ProductionPlan = S['ProductionPlan']
export type ProductionKpis = S['ProductionKpis']
export type WorkOrderResult = S['WorkOrderResult']
export type AiStatus = S['AiStatus']
export type AskResult = S['AskResult']
export type SearchResult = S['SearchResult']
export type SearchHit = S['SearchHit']
export type AssistResult = S['AssistResult']
export type SmartSuggestion = S['SmartSuggestion']
export type DemandForecast = S['DemandForecast']
export type Problem = { title: string; status: number; detail?: string }

export class ApiError extends Error {
  constructor(public status: number, public problem?: Problem) { super(problem?.title ?? `HTTP ${status}`) }
}

// X-AW-Client on every call: the server requires it on unsafe methods (CSRF guard, forces a CORS preflight).
const csrf: Middleware = { onRequest({ request }) { request.headers.set('X-AW-Client', 'spa'); return request } }
export const http = createClient<paths>({ baseUrl: '', credentials: 'same-origin' })
http.use(csrf)

type Res<T> = { data?: T; error?: unknown; response: Response }
async function ok<T>(p: Promise<Res<T>>): Promise<T> {
  const { data, error, response } = await p
  if (!response.ok) throw new ApiError(response.status, (error as Problem | undefined) ?? undefined)
  return data as T
}
const idem = () => ({ 'Idempotency-Key': crypto.randomUUID() })

export const api = {
  me: () => ok(http.GET('/api/v2/me')),
  login: (email: string, password: string) => ok(http.POST('/api/v2/auth/login', { body: { email, password } })),
  logout: () => ok(http.POST('/api/v2/auth/logout')),
  products: (next?: string | null, pageSize = 25) => ok(http.GET('/api/v2/products', { params: { query: { pageSize, next: next ?? undefined } } })),
  product: (id: number) => ok(http.GET('/api/v2/products/{id}/detail', { params: { path: { id } } })),
  categories: () => ok(http.GET('/api/v2/categories')),
  subcategoryProducts: (id: number) => ok(http.GET('/api/v2/subcategories/{id}/products', { params: { path: { id } } })),
  reviews: (id: number) => ok(http.GET('/api/v2/products/{id}/reviews', { params: { path: { id } } })),
  addReview: (id: number, rating: number, comments: string) => ok(http.POST('/api/v2/products/{id}/reviews', { params: { path: { id } }, body: { rating, comments } })),
  cart: () => ok(http.GET('/api/v2/cart')),
  addToCart: (productId: number, quantity: number) => ok(http.POST('/api/v2/cart/items', { body: { productId, quantity } })),
  setQuantity: (productId: number, quantity: number) => ok(http.PUT('/api/v2/cart/items/{productId}', { params: { path: { productId } }, body: { quantity } })),
  removeFromCart: (productId: number) => ok(http.DELETE('/api/v2/cart/items/{productId}', { params: { path: { productId } } })),
  shipMethods: () => ok(http.GET('/api/v2/ship-methods')),
  quote: (shipMethodId?: number) => ok(http.GET('/api/v2/checkout/quote', { params: { query: { shipMethodId } } })),
  checkout: (shipMethodId?: number) => ok(http.POST('/api/v2/checkout', { body: { shipMethodId: shipMethodId ?? null }, headers: idem() })),
  myOrders: () => ok(http.GET('/api/v2/orders', { params: { query: {} } })),
  myOrder: (id: number) => ok(http.GET('/api/v2/orders/{id}', { params: { path: { id } } })),
  queue: (status: number, territoryId?: number) => ok(http.GET('/api/v2/back-office/orders', { params: { query: { status, territoryId } } })),
  queueCounts: () => ok(http.GET('/api/v2/back-office/orders/counts')),
  boOrder: (id: number) => ok(http.GET('/api/v2/back-office/orders/{id}', { params: { path: { id } } })),
  triageAssist: (id: number, kind: 'explain' | 'approve-note' | 'backorder-note') => ok(http.POST('/api/v2/back-office/orders/{id}/assist/{kind}', { params: { path: { id, kind } } })),
  transition: (id: number, op: 'approve' | 'reject' | 'backorder' | 'ship' | 'cancel', version: number, ship?: { shipMethodId: number; trackingNumber: string }, note?: string) =>
    ok(http.POST('/api/v2/back-office/orders/{id}/{op}', {
      params: { path: { id, op } }, headers: idem(),
      body: { version, shipMethodId: ship?.shipMethodId ?? null, trackingNumber: ship?.trackingNumber ?? null, note: note || null },
    })),
  bulkApprove: (orders: { id: number; version: number }[]) => ok(http.POST('/api/v2/back-office/orders/bulk-approve', { body: { orders } })),
  changes: (limit = 50) => ok(http.GET('/api/v2/back-office/changes', { params: { query: { limit } } })),
  // C2-3 procurement
  suggestions: () => ok(http.GET('/api/v2/back-office/procurement/suggestions')),
  smartSuggestions: () => ok(http.GET('/api/v2/back-office/procurement/smart-suggestions')),
  explainReorder: (id: number) => ok(http.POST('/api/v2/back-office/procurement/smart-suggestions/{id}/explain', { params: { path: { id } } })),
  poEmailDraft: (id: number) => ok(http.POST('/api/v2/back-office/procurement/orders/{id}/email-draft', { params: { path: { id } } })),
  vendors: () => ok(http.GET('/api/v2/back-office/procurement/vendors')),
  vendor: (id: number) => ok(http.GET('/api/v2/back-office/procurement/vendors/{id}', { params: { path: { id } } })),
  pos: (status: number) => ok(http.GET('/api/v2/back-office/procurement/purchase-orders', { params: { query: { status } } })),
  poCounts: () => ok(http.GET('/api/v2/back-office/procurement/purchase-orders/counts')),
  myPos: () => ok(http.GET('/api/v2/back-office/procurement/purchase-orders/mine', { params: { query: {} } })),
  po: (id: number) => ok(http.GET('/api/v2/back-office/procurement/purchase-orders/{id}', { params: { path: { id } } })),
  locations: () => ok(http.GET('/api/v2/back-office/procurement/locations')),
  createPo: (vendorId: number, shipMethodId: number | null, lines: { productId: number; quantity: number }[]) =>
    ok(http.POST('/api/v2/back-office/procurement/purchase-orders', { body: { vendorId, shipMethodId, lines }, headers: idem() })),
  poTransition: (id: number, op: 'approve' | 'reject', version: number, note?: string) =>
    ok(http.POST('/api/v2/back-office/procurement/purchase-orders/{id}/{op}', { params: { path: { id, op } }, headers: idem(), body: { version, note: note ?? null } })),
  receive: (id: number, version: number, lines: { detailId: number; receivedQty: number; rejectedQty: number; locationId: number | null }[]) =>
    ok(http.POST('/api/v2/back-office/procurement/purchase-orders/{id}/receive', { params: { path: { id } }, headers: idem(), body: { version, lines } })),
  // C2-4 production floor
  workOrders: (month: string, openOnly = false, productId?: number) =>
    ok(http.GET('/api/v2/back-office/production/work-orders', { params: { query: { month, openOnly, productId } } })),
  openWorkOrders: () => ok(http.GET('/api/v2/back-office/production/work-orders/open')),
  workOrder: (id: number) => ok(http.GET('/api/v2/back-office/production/work-orders/{id}', { params: { path: { id } } })),
  createWorkOrder: (productId: number, orderQty: number, dueDate: string | null) =>
    ok(http.POST('/api/v2/back-office/production/work-orders', { body: { productId, orderQty, dueDate }, headers: idem() })),
  recordOperation: (id: number, version: number, resourceHrs: number) =>
    ok(http.POST('/api/v2/back-office/production/work-orders/{id}/operations', { params: { path: { id } }, headers: idem(), body: { version, resourceHrs } })),
  completeWorkOrder: (id: number, version: number, scrappedQty: number, scrapReasonId: number | null, locationId: number | null) =>
    ok(http.POST('/api/v2/back-office/production/work-orders/{id}/complete', { params: { path: { id } }, headers: idem(), body: { version, scrappedQty, scrapReasonId, locationId } })),
  plan: (productId: number, qty: number) => ok(http.GET('/api/v2/back-office/production/plan/{productId}', { params: { path: { productId }, query: { qty } } })),
  assemblies: () => ok(http.GET('/api/v2/back-office/production/assemblies')),
  bom: (productId: number, asOf?: string) => ok(http.GET('/api/v2/back-office/production/bom/{productId}', { params: { path: { productId }, query: { asOf } } })),
  whereUsed: (productId: number, asOf?: string) => ok(http.GET('/api/v2/back-office/production/where-used/{productId}', { params: { path: { productId }, query: { asOf } } })),
  kpis: (from: string, to: string) => ok(http.GET('/api/v2/back-office/production/kpis', { params: { query: { from, to } } })),
  scrapReasons: () => ok(http.GET('/api/v2/back-office/production/scrap-reasons')),
  aiStatus: () => ok(http.GET('/api/v2/ai/status')),
  semanticSearch: (q: string, top = 12) => ok(http.GET('/api/v2/ai/search', { params: { query: { q, top } } })),
  askExamples: () => ok(http.GET('/api/v2/ai/examples')),
  ask: (question: string) => ok(http.POST('/api/v2/ai/ask', { body: { question } })),
  setPrice: (id: number, listPrice: number, version: number) => ok(http.PUT('/api/v2/back-office/products/{id}/price', { params: { path: { id } }, body: { listPrice, version } })),
}

export const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
export const staffRoles = ['Fulfilment', 'CatalogAdmin', 'Buyer', 'PurchasingManager', 'ProductionSupervisor']
export const isStaff = (me: Me | null) => !!me?.roles?.some(r => staffRoles.includes(r))
export const hasRole = (me: Me | null, role: string) => !!me?.roles?.includes(role)
