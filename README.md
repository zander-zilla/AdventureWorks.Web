# AdventureWorks Modernization (SQL Server → DynamoDB + Redshift zero-ETL)

Fork of [Azure-Samples/AdventureWorks.Web](https://github.com/Azure-Samples/AdventureWorks.Web) (archived; MIT, © Microsoft — see LICENSE.md).
This fork is used for an AWS modernization demo; see [docs/modernization/PLAN.md](docs/modernization/PLAN.md).

Original description: *AdventureWorks Sample Web App. This App connects to the sample database Adventure Works.*

## Before environment

The **before** baseline is the original ASP.NET Core 2.1 MVC + EF Core app over `AdventureWorksLT2022`,
plus the full `AdventureWorks2022` (OLTP) and `AdventureWorksDW2022` databases on SQL Server 2022.

| Piece | Detail |
|---|---|
| App | Original code, `netcoreapp2.1` **unchanged target**. Built with .NET SDK 2.1.818 (pinned in `global.json`); container uses `mcr.microsoft.com/dotnet/core/sdk:2.1` / `aspnet:2.1`. On hosts without ICU set `DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1`. |
| SQL Server | `mcr.microsoft.com/mssql/server:2022-latest`, Developer, `MSSQL_AGENT_ENABLED=true` (needed by CDC jobs) |
| Databases | Official `.bak` files from microsoft/sql-server-samples release `adventureworks`: AdventureWorksLT2022, AdventureWorks2022, AdventureWorksDW2022 (`scripts/fetch-baks.sh`, git-ignored) |
| CDC | `docker/before/sql/02-enable-cdc.sql` – `sys.sp_cdc_enable_db` on AdventureWorks2022 and AdventureWorksLT2022; tables: Sales.{SalesOrderHeader, SalesOrderDetail, Customer, Store, SpecialOfferProduct, ShoppingCartItem, CreditCard, PersonCreditCard}, Person.{Person, Address, BusinessEntityAddress, EmailAddress, PersonPhone}, Production.{Product, ProductCategory, ProductSubcategory, ProductModel, ProductInventory, ProductListPriceHistory, ProductReview}; LT: SalesLT.{Customer, SalesOrderHeader, SalesOrderDetail, Product}. All with `@supports_net_changes=1`. |
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

- `Demo/DemoCustomers.cs` – 5 seeded demo users mapped to existing `SalesLT.Customer` rows (password `Demo!2026`), e.g. `catherine0@adventure-works.com` → CustomerID 29485.
- `Controllers/AccountController.cs` – cookie auth login/logout; `Controllers/ShopController.cs` – product list, **Order** (writes `SalesLT.SalesOrderHeader` + `SalesOrderDetail` in one transaction, `Comment='demo-order'`), My orders.
- `Startup.cs` – cookie auth, TempData cookie marked essential, optional `DisableHttpsRedirection=true` for containers/CI. Nav links in `_Layout.cshtml`.
- `scripts/reset-demo.sql` – deletes demo orders.

CI: `.github/workflows/before.yml` builds the app with the 2.1 SDK and brings up the full stack (restore, health check, CDC, smoke HTTP check incl. login + order + CDC row check).
