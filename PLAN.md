# AdventureWorks modernization – plan overview

The project runs in two chapters on the same repo (`zander-zilla/AdventureWorks.Web`, `master`).

| Chapter | Name | Phases | Status | Plan |
|---|---|---|---|---|
| 1 | Migration | 0-8: SQL Server → DynamoDB (7 domain tables), CDC, .NET 10 app, zero-ETL → Redshift, Terraform, showcase | **Done**, tag `v1.0-migration` (`45b8584`, GitHub release) | [docs/modernization/PLAN.md](docs/modernization/PLAN.md) |
| 2 | Extend and modernize | C2-0..C2-5: design system (React + Tailwind), redesigned showcase with chapter switch, order fulfilment + pricing + reviews, procurement, production floor, optional Bedrock AI | **In progress**: plan accepted (John, 2026-10-12); C2-0 in PR #17 | [docs/chapter-2/PLAN.md](docs/chapter-2/PLAN.md) |

Chapter 2 is grounded in the business-process analysis in [docs/business-processes/](docs/business-processes/README.md).

## Ground rules (both chapters)
- PRs on this fork only (`gh pr create -R zander-zilla/AdventureWorks.Web --base master`); John merges. The upstream is archived.
- Every phase lands as a PR with docs updated and CI green.
- Chapter 1 stays reproducible: the showcase's Chapter 1 view is built from the `v1.0-migration` tag.

## Decisions log
| Date | Decision |
|---|---|
| 2026-10-12 | Chapter 2 continues in the same repo on `master` (John). |
| 2026-10-12 | John accepted all 9 Chapter 2 recommendations (docs/chapter-2/PLAN.md, *Decisions for John*); recorded in [ADR 0010](docs/adr/0010-chapter-2-front-end.md): |
| 2026-10-12 | 1. Front end: React 19 + TypeScript + Vite + Tailwind over `/api/v2` on the .NET 10 app. |
| 2026-10-12 | 2. Visual style B (dark ops console) for back office and showcase; A's (Trail) colours as the light shop theme. |
| 2026-10-12 | 3. Chapter 1 frozen at `/c1/` (same bucket/distribution, built from `v1.0-migration` by a manual workflow) plus a release zip. |
| 2026-10-12 | 4. C2-5 (Bedrock AI) in scope as the last phase, off by default (`enable_ai`), S3 Vectors. |
| 2026-10-12 | 5. Add Redshift vendor performance (C2-3) and scrap/on-time (C2-4) tiles; defer promotion effectiveness. |
| 2026-10-12 | 6. Defer sales-person workspace, HR org chart, returns (RMA); customer profile (CUS-09) first if time allows. |
| 2026-10-12 | 7. Keep the Razor shop until C2-2 is done, then switch `/` to the SPA. |
| 2026-10-12 | 8. Tag `v2.0-extend` at the end of Chapter 2 (optional `v2.0-rcN` after C2-2). |
| 2026-10-12 | 9. C2-3 (procurement) before C2-4 (production). |
| 2026-10-12 | C2-0 as built: front end in `src/web` (not `web/`), SPA served by the app at `/app/`, framed-login fix via `SameSite=None; Secure` when framed over HTTPS; full list in ADR 0010 *Changes from initial design*. |
| 2026-10-12 | John accepted the C2-0 recommendations: keep the hand-written `/api/v2` client until C2-2 (generate it from OpenAPI then); keep the dependency-free SVG charts until C2-4 (add a chart library there); wire the SPA's *Chapter 1* button to `/c1/` via `VITE_SHOWCASE_URL` in C2-1. |
| 2026-10-12 | C2-1 as built (PR #18): Chapter 2 showcase is a second Vite entry in `src/web` (hash routes `#/c2/...`), Chapter 1 frozen under `/c1/` (release asset `showcase-v1.0-migration.zip`, `showcase-freeze.yml`), CloudFront `c1/*` behaviours + path function; see docs/chapter-2/PLAN.md *C2-1 as built*. |
| 2026-10-12 | John accepted the C2-1 defaults: coverage tile 5 → 9 of 10, darker accent button text in dark mode, `/#/c2/...` hash links, *Ask the data* shown as coming soon. |
| 2026-10-12 | C2-2 as built (PR #19): back office fulfilment (ship = DynamoDB transaction over order, stock and TransactionHistory), real checkout pricing, reviews, CAT-07 fix, OpenAPI-generated client, `/` switched to the React shop (Razor at `/Shop`, `/classic`). SAL-14 not added (territory filter on SAL-05). See docs/chapter-2/PLAN.md *C2-2 as built*. |
