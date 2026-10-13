# AdventureWorks Modernization (SQL Server → DynamoDB + Redshift zero-ETL)

Fork of [Azure-Samples/AdventureWorks.Web](https://github.com/Azure-Samples/AdventureWorks.Web) (archived; MIT, © Microsoft — see LICENSE.md).
This fork is used for an AWS modernization demo in two chapters (overview: [PLAN.md](PLAN.md)):

- **Chapter 1 – Migration** (phases 0-8, tag `v1.0-migration`): SQL Server → DynamoDB + CDC, .NET 10 app, zero-ETL → Redshift, Terraform, showcase. [docs/modernization/PLAN.md](docs/modernization/PLAN.md)
- **Chapter 2 – Extend and modernize** (proposed): modern React + Tailwind UI and new back-office features from the [business-process analysis](docs/business-processes/README.md). [docs/chapter-2/PLAN.md](docs/chapter-2/PLAN.md)

Original description: *AdventureWorks Sample Web App. This App connects to the sample database Adventure Works.*

## After environment

The modernized app is in `src/AdventureWorks.Web`: .NET 10 on DynamoDB, with shopper pages and the admin screens. See
[docs/modernization/app.md](docs/modernization/app.md).

```bash
scripts/after-up.sh                       # SQL restore (if needed) -> DynamoDB Local x7 loaded by the Phase 3 loader -> app on :5090
(cd src && dotnet test AdventureWorks.slnx)   # unit tests (AW_DDB_IT=1 adds the DynamoDB Local integration tests)
pip install playwright && python -m playwright install chromium && pytest tests/after   # browser smoke test
```

- Demo logins are the same 5 customers as the before app (for example `catherine0@adventure-works.com`), password `Demo!2026`.
- `/` opens the Chapter 2 React app (`/app/`). The Razor shop was removed in C2-3; the Chapter 1 version of it is still in the frozen showcase under `/c1/` and in tag `v1.0-migration`.
- Back office demo staff (password `Demo!2026`): `fulfilment@adventure-works.com` (orders), `ops@adventure-works.com` (orders + price edits), `mikael0@adventure-works.com` (buyer: creates and receives purchase orders), `sheela0@adventure-works.com` (buyer + purchasing manager: also approves / rejects), `production@adventure-works.com` (production supervisor: creates, operates and completes work orders).
- Purchase orders created here are `PO-DDB-…` (ids from 100,000); SQL-era POs are shown read-only.
- Orders placed here are `SO-DDB-…`. They live only in DynamoDB and flow to Redshift through zero-ETL.
- The image is chiseled and runs as non-root (UID 1654).

## Before environment

The **before** baseline is the original ASP.NET Core 2.1 MVC + EF Core app over `AdventureWorksLT2022`,
plus the full `AdventureWorks2022` (OLTP) and `AdventureWorksDW2022` databases on SQL Server 2022.

| Piece | Detail |
|---|---|
| App | Original code, `netcoreapp2.1` **unchanged target**. Built with .NET SDK 2.1.818 (pinned in `global.json`); container uses `mcr.microsoft.com/dotnet/core/sdk:2.1` / `aspnet:2.1`. On hosts without ICU set `DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1`. |
| SQL Server | `mcr.microsoft.com/mssql/server:2022-latest`, Developer, `MSSQL_AGENT_ENABLED=true` (needed by CDC jobs) |
| Databases | Official `.bak` files from microsoft/sql-server-samples release `adventureworks`: AdventureWorksLT2022, AdventureWorks2022, AdventureWorksDW2022 (`scripts/fetch-baks.sh`, git-ignored) |
| CDC | `docker/before/sql/02-enable-cdc.sql` – `sys.sp_cdc_enable_db` + **all 68 business tables** of AdventureWorks2022 (HumanResources, Person, Production, Purchasing, Sales), `@supports_net_changes=1` (every one has a PK; the script falls back to `0` and warns for any table without one). **Excluded:** `dbo.AWBuildVersion`, `dbo.DatabaseLog`, `dbo.ErrorLog` – housekeeping, and DatabaseLog is written by the DDL trigger (incl. CDC's own DDL), so it would only add noise. AdventureWorksLT2022 also has CDC on SalesLT.{Customer, SalesOrderHeader, SalesOrderDetail, Product} for the original CRUD screens. |
| Networking | Both services use `network_mode: host` (some dev boxes cannot do container-to-container networking). App: http://localhost:5080, SQL: localhost,1433 |

### Run it

```bash
scripts/before-up.sh        # fetch .baks, start SQL, restore 3 DBs, enable CDC, build+start app
scripts/smoke.sh            # pages render, demo login, place an order
docker exec -i aw-before-sqlserver-1 /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P 'AdvWorks!2026' < scripts/reset-demo.sql
```

Default SA password `AdvWorks!2026` (override with `MSSQL_SA_PASSWORD`). Demo only.

### Demo login (before-baseline addition, clearly labelled `BEFORE BASELINE` in code)

The original app has no customer login. Minimal additions so a test customer can create an order:

- `Demo/DemoCustomers.cs` – 5 seeded demo users mapped to existing **AdventureWorks2022** `Sales.Customer` rows (password `Demo!2026`), e.g. `catherine0@adventure-works.com` → CustomerID 29485 (store contact; ids identical in LT).
- `Demo/FullDb.cs` – ADO.NET access to the **full AdventureWorks2022** DB (connection string `AdventureWorks`, default = LT connection with database `AdventureWorks2022`). The demo shop's catalog read (Production.Product with the 'No Discount' offer), order write and My orders all use it, so the live demo's writes land in the database that CDC → DynamoDB models. The original Products/Customers/Categories CRUD screens are unchanged and still use AdventureWorksLT2022.
- `Controllers/AccountController.cs` – cookie auth login/logout; `Controllers/ShopController.cs` – product list, **Order** (writes `Sales.SalesOrderHeader` + `Sales.SalesOrderDetail` in AdventureWorks2022 in one transaction, `Comment='demo-order'`, ShipMethodID 5, SpecialOfferID 1; SubTotal maintained by the table trigger), My orders.
- `Startup.cs` – cookie auth, TempData cookie marked essential, optional `DisableHttpsRedirection=true` for containers/CI. Nav links in `_Layout.cshtml`.
- `scripts/reset-demo.sql` – deletes demo orders from AdventureWorks2022 (and any legacy LT demo orders).

CI: `.github/workflows/before.yml` builds the app with the 2.1 SDK and brings up the full stack (restore, health check, CDC, smoke HTTP check incl. login + order, asserts 68 CDC tables and that the demo order appears in `cdc.Sales_SalesOrderHeader_CT`).

## Showcase (Phase 8)
`scripts/showcase-up.sh` → http://localhost:8088: Presentation, Before/After Architecture, Data Mapping, Access Patterns, Live Replication, Before App, After App. See docs/showcase.md.
