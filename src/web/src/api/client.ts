// Typed client for /api/v2 (same origin; the auth cookie travels automatically).
// Types mirror the C# records in Api/V2.cs; the OpenAPI document is served at /api/v2/openapi.json and a
// contract test (Api_v2_contract) pins its shape. Generated client: deferred to C2-2 (ADR 0010, changes).
export type Me = { authenticated: boolean; name?: string; email?: string; customerId?: number; roles: string[] }
export type ProductSummary = { id: number; name: string; productNumber: string; listPrice: number; active: boolean }
export type ProductPage = { items: ProductSummary[]; next: string | null }
export type Subcategory = { id: number; name: string }
export type Category = { id: number; name: string; subcategories: Subcategory[] }
export type Problem = { title: string; status: number; detail?: string }

export class ApiError extends Error {
  constructor(public status: number, public problem?: Problem) { super(problem?.title ?? `HTTP ${status}`) }
}

const base = '/api/v2'
async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(base + path, {
    credentials: 'same-origin', ...init,
    // X-AW-Client on every call: the server requires it on unsafe methods (CSRF guard, forces a CORS preflight).
    headers: { Accept: 'application/json', 'X-AW-Client': 'spa', ...(init?.body ? { 'Content-Type': 'application/json' } : {}), ...init?.headers },
  })
  if (!r.ok) throw new ApiError(r.status, await r.json().catch(() => undefined))
  return r.status === 204 ? (undefined as T) : r.json()
}

export const api = {
  me: () => call<Me>('/me'),
  login: (email: string, password: string) => call<Me>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  logout: () => call<void>('/auth/logout', { method: 'POST' }),
  products: (next?: string | null, pageSize = 25) => call<ProductPage>(`/products?pageSize=${pageSize}${next ? `&next=${encodeURIComponent(next)}` : ''}`),
  categories: () => call<Category[]>('/categories'),
}
