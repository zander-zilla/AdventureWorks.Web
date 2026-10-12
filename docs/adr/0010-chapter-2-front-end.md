# ADR 0010: Chapter 2 front end – React SPA under /app/ on the app origin, /api/v2 minimal APIs, one token set with two themes

Status: **Accepted** (John, 2026-10-12; all 9 Chapter 2 recommendations, see the decisions log in [PLAN.md](../../PLAN.md)).
Implemented in C2-0 (PR #17). Code only, nothing applied (no AWS calls).

## Context
Chapter 2 ([docs/chapter-2/PLAN.md](../chapter-2/PLAN.md)) needs a modern look and interactive back-office screens
(multi-select tables, drawers, BOM tree, Gantt) over the Chapter 1 DynamoDB model, while the Razor shop keeps working
until each screen is replaced. Chapter 1 also left a known limitation: the showcase's App tab frames the app cross-site,
so the `SameSite=Lax` auth cookie is not sent and sign-in only works in a new tab.

## Decision
1. **React 19 + TypeScript (strict) + Vite + Tailwind CSS v4** in `src/web` (decision 1). Pinned `package-lock.json`,
   `npm ci`, `npm audit --audit-level=high` in CI, Dependabot (weekly). ESLint, Vitest (+ Testing Library), Playwright.
2. **Served by the .NET 10 app under `/app/`** (same origin as `/api/v2` and the auth cookie). The Docker image builds
   the bundle in a `node:22-alpine` stage and copies `dist/` into `wwwroot/app`; `MapFallbackToFile("/app/{*path:nonfile}")`
   serves client-side routes; `/app` redirects to `/app/`. No new AWS resource: the ALB already forwards everything to the
   container. Terraform only gains the `spa_url` output.
3. **`/api/v2` minimal APIs** in `Api/V2.cs`: `GET /me`, `POST /auth/login`, `POST /auth/logout`, `GET /products` (CAT-06,
   DynamoDB cursor paging), `GET /products/{id}`, `GET /categories` (CAT-01), `GET /cart` (first endpoint behind the
   `customer` policy). OpenAPI document at `/api/v2/openapi.json` (Microsoft.AspNetCore.OpenApi, v2 routes only).
   Errors are `application/problem+json`; unauthenticated API calls get **401/403 instead of the Razor login redirect**.
4. **Auth = the existing cookie scheme** (`aw.after`), same demo customers and password; SPA login posts JSON.
   CSRF guard: unsafe methods require an `X-AW-Client` header (cross-site pages cannot send it without a CORS preflight,
   and the API enables no CORS). Claims gain `role=Customer`; back-office roles (Buyer, PurchasingManager) arrive in C2-3.
5. **Framed sign-in fix**: when `Showcase:FrameAncestors` is set and the request is HTTPS (ALB `X-Forwarded-Proto`,
   honoured via `UseForwardedHeaders`), all cookies are written `SameSite=None; Secure`, so sign-in works inside the
   showcase iframe for both the Razor pages and the SPA. Plain HTTP or no framing: unchanged (`Lax`).
6. **Design tokens**: one semantic token set (`bg, panel, raised, ink, mute, line, accent, accent2, ok, warn, danger, info`,
   display font, radius) as CSS variables mapped into Tailwind with `@theme inline`; `[data-theme=dark]` = mockup **B ·
   Ops console** (default for back office and showcase), `[data-theme=light]` = **A · Trail** palette (default for `/shop/*`)
   (decision 2). User choice persists in `localStorage` (`aw.theme`) and is applied before first paint.
7. **12 core components** (`src/web/src/components`): AppShell, ChapterSwitch, NavRail, KpiCard, DataTable (sort, filter,
   multi-select), StatusPill (order status 1-6), Drawer, Form fields (TextField, SelectField, Checkbox, plus Button),
   Toast, EmptyState, Chart wrapper, Timeline. Gallery ("Storybook-lite") at **`/app/design`**.

## Consequences
- Two UIs coexist until C2-2; Razor stays at `/` (decision 7). The SPA links to Chapter 1 via the chapter switch.
- The front end adds a Node toolchain to the build; CI job `web` covers lint, types, unit, build, audit, Playwright.
- `after.yml` now also runs the Playwright suite against the real image (`/app/` + real `/api/v2` + DynamoDB Local).

## Changes from initial design (C2-0 as built)
| Plan (docs/chapter-2/PLAN.md, C2-0) | As built | Why |
|---|---|---|
| Workspace `web/` | **`src/web`** | The app's Docker build context is `src/`; keeps the image build single-context. |
| Generated TS client from OpenAPI | **Hand-written typed client** (`src/api/client.ts`) + OpenAPI document + contract test on its paths | Only 7 endpoints; generator choice deferred to C2-2 when the API grows. |
| Chart wrapper on Recharts | **Dependency-free SVG** wrapper (bar/line) behind the same props | Smaller bundle and audit surface for C2-0; swap in Recharts in C2-4 if needed. |
| Radix/shadcn-style primitives | Own minimal components (accessible roles, Escape-to-close drawer, labelled fields) | 12 components didn't need them yet; revisit for menus/comboboxes. |
| Proof screen: shopper home + product list | **Product list** (`/app/shop/products`, CAT-06) + Chapter 2 home | Shop home redesign moves to C2-2 with the Razor cut-over. |
| "SPA on the app origin fixes framed login" | Same origin fixes the SPA's API calls; framed login needs **`SameSite=None; Secure` when framed over HTTPS** (item 5) | Same-origin alone doesn't help inside a cross-site iframe. |
| Terraform changes | Only output `spa_url` | The ALB already routes `/app/*` to the container. |
| Lighthouse before/after | Not yet | Planned for the C2-1 showcase. |
