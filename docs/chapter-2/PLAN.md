# Chapter 2 – Extend and modernize (plan, for John's sign-off)

Status: **Proposed** (2026-10-12). Docs only; nothing built or applied. Builds on PR #15 (merged)
([docs/business-processes/](../business-processes/README.md)), which is the evidence base for every feature below.

Chapter 1 ("Migration", phases 0-8) is done and frozen at tag **`v1.0-migration`** (`45b8584`, GitHub release):
SQL Server → 7 DynamoDB domain tables, CDC, .NET 10 app, zero-ETL → Redshift, Terraform, showcase. See
[docs/modernization/PLAN.md](../modernization/PLAN.md).

Chapter 2 builds on the same repo and the same `master`. Goal: **a much nicer modern look and feel, plus new features
that light up the business processes Chapter 1 migrated but never gave a UI** (PR #15: 10 processes, ~40 designed access
patterns unused by the app). The story for the audience: *"migration was step one; now the platform pays off."*

## Principles
- **Reuse the Chapter 1 data model.** Prefer existing access patterns (`docs/design/access-patterns.json`); every new
  pattern gets an ID, a load test and a mapping/ADR entry exactly like Chapter 1.
- **Chapter 1 stays reproducible.** The frozen showcase is built from the tag, never from `master`.
- **Each phase is one PR**, CI green, docs + screenshots updated, demo talking points in the PR body.
- Same ground rules: PRs on the fork only (`-R zander-zilla/AdventureWorks.Web --base master`), John merges.

## Phases

| # | Phase | Outcome | Effort |
|---|---|---|---|
| C2-0 | Design system and UX direction | Chosen visual direction, React + Tailwind front end scaffold over the .NET 10 API, tokens/components, ADR 0010 | M (4-6 d) |
| C2-1 | Redesigned showcase + chapter switch | New showcase in the design system; Chapter 1 frozen from `v1.0-migration`, Chapter 2 live | M (4-5 d) |
| C2-2 | Order fulfilment + real pricing + reviews + CAT-07 fix | Back office closes the order loop; checkout uses real offers/tax/freight; reviews on PDP; price history written | L (7-9 d) |
| C2-3 | Procurement workspace | Low stock → suggested PO → approve → receive (partial/reject) | L (6-8 d) |
| C2-4 | Production floor | Open work orders, routing timeline, BOM explorer, where-used, scrap | M (5-6 d) |
| C2-5 | *Optional* Bedrock AI layer | Semantic product search, natural-language Q&A over Redshift | M (5-7 d) |

Total ≈ 26-34 working days without C2-5, 31-41 with it. Estimates are for one engineer plus agent help, incl. tests and docs.

---

## C2-0 Design system and UX direction

**Recommendation: React 19 + TypeScript + Vite + Tailwind CSS v4 SPA, served as static files, calling a JSON API
added to the existing .NET 10 app (`/api/v2/*`, minimal APIs).** Razor pages stay working until each screen is replaced.

Why, and the alternatives considered:
- *React + Tailwind (chosen)*: the audience expects a modern SaaS feel (tables, drawers, charts, Gantt); the component
  ecosystem (TanStack Table/Query, Recharts, Radix/shadcn-style primitives) gets there fastest; Tailwind tokens make the
  three directions below a theme swap; a static bundle hosts on the same S3 + CloudFront as the showcase (ADR 0009).
- *Blazor (.NET 10)*: one language, but smaller component ecosystem, heavier initial payload (WASM) or server
  circuits on Fargate (which scale to 0 between demos, ADR 0008), and less "modern front end" signal for customers.
- *Restyle Razor + HTMX + Tailwind*: cheapest, no API layer, but interactive back-office screens (multi-select ship,
  BOM tree, Gantt) become hand-rolled JS, and there is no clean API to show for Bedrock or mobile.
- *Next.js/SSR*: SSR adds a Node runtime to host; nothing here needs SEO. Rejected.

Steps
1. ADR 0010 (front-end stack, API style, auth: same cookie auth, SPA served from the app origin under `/app/` so the
   `SameSite=Lax` cookie works – this also removes the Chapter 1 "log in only in a new tab" limitation when framed).
2. `web/` workspace: Vite, TS strict, Tailwind v4, ESLint, Vitest, Playwright; `npm ci` pinned lockfile; CI job `web`.
3. Design tokens (colour, type scale, radius, spacing, dark mode) + 12 core components: AppShell, ChapterSwitch,
   NavRail, KpiCard, DataTable (sort/filter/select), StatusPill, Drawer, Form fields, Toast, EmptyState, Chart wrapper, Timeline.
4. `/api/v2` skeleton in the .NET app (OpenAPI document, generated TS client), first endpoint `GET /api/v2/products`.
5. Rebuild the shopper home + product list in the new UI as the proof (Razor remains at `/`).
6. Visual direction picked by John from the mockups below; Storybook-lite page (`/app/design`) for review.

**Visual direction options** (static HTML mockups, `docs/chapter-2/mockups/`, regenerate with `render.py`; same screen –
the back-office order fulfilment page with the chapter switch – in each direction):

| A · Trail (warm outdoor, light) | B · Ops console (dark, data-dense) | C · Editorial retail (bold, high-contrast) |
|---|---|---|
| ![A](mockups/a-trail.png) | ![B](mockups/b-console.png) | ![C](mockups/c-editorial.png) |
| Fits the outdoor/bike brand, friendly for shoppers and execs; less "enterprise". | Best for back-office density and the technical audience; looks like a modern ops tool; weaker for the shop. | Strong retail brand feel, great for the shop; tables feel stark. |

**Recommendation: B for back-office/showcase with A's palette as the light theme for the shop** (one token set, light/dark
modes), i.e. tokens support both, default dark in back office, light in shop.

DynamoDB: no new access patterns. Risks: front-end stack is new to the repo (supply chain: pinned lockfile, `npm audit` in CI,
Dependabot); two UIs coexist during migration (mitigation: per-screen cut-over, Razor removed only in C2-2+ when replaced).
Demo talking points: "same data, same API, new face"; theme switch live; Lighthouse scores before/after.

## C2-1 Redesigned showcase with a chapter switch

Steps
1. Rebuild the showcase shell in the design system (React, same static S3 + CloudFront hosting, still data-driven from the
   repo's sources of truth; `showcase/build.py` keeps producing `data/`).
2. Chapter switch in the header: **Chapter 1 · Migration** and **Chapter 2 · Extend & modernize**.
3. **Chapter 1 is served frozen** from the `v1.0-migration` build (see *Hosting the frozen Chapter 1* below), unchanged
   8 tabs, so the migration story is exactly what was signed off.
4. Chapter 2 tabs: Story (slides: findings → features → architecture delta), Business processes (PR #15
   `business-processes.json`: landscape, coverage before/after Chapter 2), Back office (embeds/links `/app/`), What changed
   (new access patterns, new Redshift views, ADRs), Ask the data (C2-5, hidden if disabled).
5. Coverage tile: "processes with UI: 2 → 6" computed from `business-processes.json` + a `chapter2` flag per page.
6. Tests: extend `tests/showcase` (both chapters, switch, deep links `/#/c1/...`, `/#/c2/...`).

**Hosting the frozen Chapter 1** (recommended):
- Same bucket and distribution, prefix **`/c1/`**. A one-off workflow `showcase-freeze.yml` checks out tag
  `v1.0-migration`, runs that tag's `showcase/build.py` (with the then-current `config.json` values injected at upload) and
  syncs to `s3://<bucket>/c1/`. Rebuilt only when manually dispatched (immutable otherwise); Chapter 2 lives at `/` and
  `/c2/` and never writes `/c1/`.
- CloudFront: an additional cache behaviour `/c1/*` (long TTL, except `c1/config.json`), the same OAC; `/api/*` unchanged so
  Chapter 1's Live Replication keeps working.
- Also attach `showcase-v1.0-migration.zip` (the built `dist/`) to the GitHub release, so it can be served anywhere offline.
- Alternative: a second distribution / subdomain `c1.` – cleaner isolation, but another cert/DNS and cost. Not needed.
- The Chapter 1 *apps* (Before/After) are live services, not frozen: the frozen site points to the current `after_url`;
  Chapter 2 app changes are additive, so Chapter 1's shopper flows still work (asserted by the existing `tests/after`).

DynamoDB: none. Effort M. Risks: the tag's build script relies on paths that later move (mitigation: build from the tag's
own checkout, never mixed); cache invalidation of `/c1/*` (versioned paths). Demo talking points: one URL, two chapters;
"chapter 1 is literally the signed-off build".

## C2-2 Order fulfilment back office + real checkout pricing + reviews + CAT-07 fix

Steps
1. **Back office orders** (`/app/back-office/orders`): list by status and date (SAL-05, sparse ORDERSTATUS GSI), detail,
   bulk *approve*, *ship* (assign ship method, tracking no.), *cancel*, *backorder* (SAL-06). Ship = one
   `TransactWriteItems`: order status + `ShipDate`, `INV#` quantity decrement per line (INV-01, condition: on hand ≥ qty,
   otherwise backorder), `TransactionHistory` type S item per line (INV-03). Status machine 1-6 from
   `ufnGetSalesOrderStatusText`, transitions enforced server-side, with optimistic concurrency (`Version` attribute).
2. **Real pricing at checkout**: special offers applied per product (CAT-10, denormalised offer items on the product
   partition), tax by ship-to state/province (REF-02), freight by ship method (REF-04); replaces the demo 8%/2.5%.
   Shopper picks a ship method; totals recomputed server-side. Golden-value tests against SQL Server for sample orders.
3. **Reviews** on product detail (CAT-11): show existing `REVIEW#` items, logged-in shopper adds rating + text
   (length/profanity limits, one per customer per product via conditional put).
4. **CAT-07 fix** (PR #15 catalog finding): Products admin price edit writes the product *and* a `PRICE#<start date>` history
   item (closing the previous one's `EndDate`) in one transaction; test asserts Redshift `dim_product` gets a new SCD2 row
   via zero-ETL in the warehouse CI job. Back-fill: none needed (app-made changes only since Chapter 1; script reports any gap).
5. Customer profile self-service (CUS-09) is **out of scope** unless John adds it (decision 6).
6. Tests: unit (status machine, pricing), DynamoDB Local integration (transactions, conditional failures), Playwright
   (shop order → back office ship → My orders shows Shipped).

DynamoDB access patterns: existing SAL-05, SAL-06, INV-01, INV-03, CAT-07, CAT-10, CAT-11, REF-02, REF-04 suffice.
**One addition likely: `SAL-14` "orders by status for one customer/territory"** only if the back office needs a
territory filter (else filter in memory over SAL-05 results); confirm in C2-2 design.
Effort L. Risks: transaction conflicts on hot stock items (condition + retry, idempotency token per click); CDC loop – app
writes to DynamoDB must not be re-applied from SQL (Chapter 1 handles `SO-DDB-` ids; stock/TH items need the same origin
marker); pricing parity with SQL rounding (money as decimal, golden tests).
Demo talking points: place an order in the new shop, ship it in the back office, watch stock drop and the order show up in
Redshift; change a price, show the history in `dim_product`; "the bug the process analysis found is fixed".

## C2-3 Procurement workspace

Steps
1. **Low stock** dashboard (INV-02 sparse index: items below reorder point/safety stock) with on hand by location (INV-01).
2. **Suggested PO**: per product, vendors that supply it with price and lead time (PUR-02); group suggestions by vendor;
   buyer edits quantities.
3. **Create PO** (PUR-04) with lines; status Pending → Approved (approval by a "manager" role) → Received/Rejected/Complete.
4. **Receive** (PUR-07 open POs): partial receipts, rejected quantity; receipt transaction = PO line received/rejected qty
   + stock increment (INV-01) + `TransactionHistory` type P (INV-03).
5. Vendor page (PUR-01, PUR-03, PUR-05 PO history); "my POs" for the logged-in buyer (PUR-06).
6. Roles: add `Buyer` and `PurchasingManager` demo logins (employees from HR, no new auth system).
7. Optional Redshift view `dw.vendor_performance` (on-time, reject rate) as a tile – decision 5.

DynamoDB: existing INV-01/02/03, PUR-01..07 suffice (all designed and load-tested in Chapter 1). Effort L.
Risks: synthetic PO data is inconsistent (PR #15: statuses vs receipt quantities) – new POs follow the clean state machine,
historical ones are shown read-only; role model creep (keep to 2 demo roles).
Demo talking points: a whole domain (`aw-purchasing`) that had no UI goes live with zero schema change – "the Phase 3
design anticipated it"; reorder → PO → receipt chain business people recognise.

## C2-4 Production floor

Steps
1. **Open work orders** (INV-06): due date, status, scrap; filters by product and date.
2. **Routing timeline**: Gantt of a work order's operations by location (scheduled vs actual), from `WorkOrderRouting` items.
3. **BOM explorer**: multi-level tree for an assembly as of a date (INV-04), **where-used** (INV-05) reverse lookup, links
   between them.
4. **Complete a work order / record scrap**: stock in for the product, out for components (INV-01), `TransactionHistory` W
   (INV-03), scrap reason.
5. Tile from Redshift: scrap rate and on-time production (decision 5).

DynamoDB: existing INV-01, INV-03, INV-04, INV-05, INV-06 suffice. Effort M. Risks: deep BOM explosion latency (cap levels,
cache per assembly, parallel queries – measured in the Chapter 1 load test); work-order completion consuming components is
*inferred* (PR #15 marks it I), so we label it a simplification. Demo talking points: recursive BOM and where-used – the
"hard" relational patterns – answered from DynamoDB; visual Gantt.

## C2-5 Optional: Bedrock AI layer

Steps
1. **Semantic product search**: embeddings (Amazon Titan Text Embeddings v2) of product name/description/model/category,
   generated by a Lambda on product change (CDC/DynamoDB stream) and at load; stored in **S3 Vectors** (or OpenSearch
   Serverless – decision 4); `/api/v2/search?q=` blends vector + existing keyword search.
2. **Ask the data**: natural language → SQL over the Redshift `dw` schema with a Bedrock model (Claude/Nova via Bedrock,
   region per data residency), guarded: read-only Redshift user on `dw.*` views only, statement allow-list (SELECT only),
   row limit, timeout, shows the generated SQL and chart; or Bedrock Knowledge Bases structured-data (NL2SQL) if it fits.
3. Guardrails (Bedrock Guardrails: topic deny, PII filter), per-session budget, prompt/response logging to CloudWatch,
   feature flag `enable_ai` (Terraform, default off).
4. Eval set: 30 questions with expected SQL results in CI (mocked model) and a manual live run.

DynamoDB: no new table patterns (search index lives outside DynamoDB). Effort M. Risks: cost and quotas (on-demand,
flag off by default, tear-down); wrong SQL answers (show SQL, eval set, narrow semantic layer of views); data leaving the
account (none: Bedrock in-region, no training on data). Demo talking points: "ask a question, get a chart from the
warehouse migrated in Chapter 1"; vector search finds "lightweight bike for climbing" without keyword match.

---

## Cross-cutting
- **API**: `/api/v2` minimal APIs, OpenAPI, generated TS client; problem+json errors; authorization policies per role.
- **CDC and analytics**: every new write path keeps the Chapter 1 contracts (origin marker so CDC doesn't loop, zero-ETL
  picks up new items automatically; new `stg`/`dw` views where useful).
- **Infra**: SPA bundle built in CI, uploaded with the showcase (`/app/` served by the app container or S3 – ADR 0010);
  `showcase-freeze.yml`; Bedrock IAM only when `enable_ai`.
- **Tests/CI**: new `web` job (lint, unit, build), Playwright journeys per phase, existing jobs unchanged.
- **Docs**: per-phase ADR, screenshots in `docs/showcase-screenshots/chapter-2/`, PR #15 coverage table updated per phase.

## Decisions for John (with recommendations)

| # | Decision | Recommendation |
|---|---|---|
| 1 | Front-end stack | **React + TypeScript + Vite + Tailwind** over a `/api/v2` on the existing .NET 10 app (alternatives above). |
| 2 | Visual direction | **B (ops console) for back office + showcase, A (trail) palette as the light shop theme.** |
| 3 | Frozen Chapter 1 hosting | **Same bucket/distribution, `/c1/` prefix built from tag `v1.0-migration` by a manual workflow, plus a zip on the release.** |
| 4 | C2-5 in scope? Vector store | **Yes, as the last, flag-off-by-default phase; S3 Vectors** (lowest idle cost) over OpenSearch Serverless. |
| 5 | New Redshift views (promotion effectiveness, vendor performance, scrap/on-time) | **Include vendor performance (C2-3) and scrap/on-time (C2-4) as tiles; defer promotion effectiveness.** |
| 6 | Extra candidates from PR #15 (sales-person workspace, customer self-service profile, HR org chart, RMA) | **Defer; customer profile (S) is the first add if time allows.** |
| 7 | Razor UI retirement | **Keep Razor shop until C2-2 is done, then switch `/` to the SPA; Razor kept in the tag only.** |
| 8 | Release tagging | **Tag `v2.0-extend` at the end; optional `v2.0-rcN` after C2-2.** |
| 9 | Order of C2-3 vs C2-4 | **Procurement first** (stronger business story, links to C2-2 stock). |

## Changes to this plan
Tracked in the decisions log of the root [PLAN.md](../../PLAN.md).
