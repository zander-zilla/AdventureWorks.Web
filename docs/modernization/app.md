# Phase 5: AdventureWorks.Web on .NET 10 + DynamoDB

The modernized app is in `src/AdventureWorks.Web`. The original ASP.NET Core 2.1 + EF Core app stays at the repo root as the
**before** baseline: the old app keeps writing SQL, and CDC carries those writes to DynamoDB (D4, side-by-side cutover).

| | Before (repo root) | After (`src/AdventureWorks.Web`) |
|---|---|---|
| Runtime | ASP.NET Core 2.1, `Startup` class | .NET 10, minimal hosting (`Program.cs`), nullable on |
| Data | EF Core over AdventureWorksLT (admin) + ADO.NET over AdventureWorks2022 (demo shop) | AWS SDK for .NET (`AWSSDK.DynamoDBv2`), one repository per domain table |
| Tables | SQL Server | `aw-catalog`, `aw-customer`, `aw-sales` (Phase 3 designs) |
| Login | 5 demo customers, cookie auth, mapped in code | the same 5 customers, resolved in `aw-customer` with strong reads (CUS-01) |
| Orders | `SO<n>` from IDENTITY, in SQL | `SO-DDB-<n>`, n ≥ 1,000,000,000 from one atomic counter increment (D5, P3-1); never written back to SQL (D4) |
| Image | SDK 2.1 runtime image | `aspnet:10.0-noble-chiseled-extra`, non-root UID 1654, read-only filesystem |
| Tracing | none | OpenTelemetry (ASP.NET Core + HTTP/SDK spans; console exporter with `OTEL_CONSOLE=true`) |

## Screens

| Screen | Before | After | Access patterns |
|---|---|---|---|
| Products (admin) | LT `SalesLT.Product` CRUD, flat category | List (paged), filter by name prefix, details, create, edit, delete. Category → subcategory, model, stock copy, active flag | CAT-04, CAT-05, CAT-06, CAT-07, CAT-12 |
| Categories (admin) | LT self-referencing `ProductCategory` | Category → subcategory tree (the `CATALOG` collection); create/edit/move/delete | CAT-01, CAT-02, CAT-03 |
| Customers (admin) | LT `Customer` CRUD | Person, store and store-contact customers sorted by last name; details with emails, phones, addresses, cards; create; edit name | CUS-02, CUS-04, CUS-05 |
| Shop: browse | product list (demo) | categories → subcategory (sort by name/price) → product | CAT-01, CAT-03 |
| Product detail | – | descriptions in 6 cultures (en, fr, ar, he, th, zh-cht) with a culture switcher (cookie); RTL for ar/he | CAT-04 (D9) |
| Search | – | product name prefix (D2) | CAT-12 |
| Cart | – (one-click order) | logged-in customers only, 7-day TTL refreshed on change (D3), strong reads | SAL-01 |
| Checkout | 1 product per order | whole cart becomes one `TransactWriteItems` (header + lines + cart deletes); ≤ 95 lines (P3-5) | SAL-02 |
| My orders / order | list in SQL | history from GSI1, newest first; detail read strongly right after checkout | SAL-03, SAL-04 |

## Data layer → access patterns

| Repository method | Operation | Pattern |
|---|---|---|
| `CatalogRepository.GetCategoryTreeAsync` | `Query PK='CATALOG'` | CAT-01 |
| `GetSubcategoryAsync` | `Query GSI1 SUBCAT#s / #META` | CAT-02 |
| `GetProductsBySubcategoryAsync` | `Query GSI1 SUBCAT#s begins_with PRODUCT#A#` | CAT-03 |
| `GetProductAsync` + `GetDescriptionsAsync` | `Query PRODUCT#p`, `Query MODEL#m begins_with DESC#` | CAT-04 |
| `GetByNumberAsync` | `GetItem PRODUCTNUMBER#n` | CAT-05 |
| `ListProductsAsync` | `Query PRODUCTNAMES` paged | CAT-06 |
| `Create/Update/DeleteProductAsync` | `TransactWriteItems` product + unique name + unique number items (`ver` check) | CAT-07 |
| `SearchByPrefixAsync` | `Query PRODUCTNAMES begins_with(prefix)` | CAT-12 |
| `CustomerRepository.FindLoginAsync` | `GetItem EMAIL#e` + `Query BE#id`, **ConsistentRead** | CUS-01 |
| `GetCustomerAsync` | `Query GSI1 CUSTOMER#c`, `Query BE#owner` (+ the store's addresses) | CUS-02/03 |
| `CreateAsync` | counter + `TransactWriteItems` BE/PERSON/CUSTOMER/EMAIL (unique email) | CUS-04 |
| `ListAsync` | `Query GSI2 CUSTOMERS` paged | CUS-05 |
| `UpdateNameAsync` | `TransactWriteItems` PERSON + customer copy (`display_name`, `GSI2SK`) | – (admin edit) |
| `SalesRepository.Get/Add/SetQuantity/Remove` | `Query CART#c` **ConsistentRead**, `UpdateItem ITEM#p` (ttl = now + 7 days) | SAL-01 |
| `CheckoutAsync` | `UpdateItem COUNTER/ORDER ADD next_id 1` + `TransactWriteItems` | SAL-02 |
| `GetOrdersForCustomerAsync` | `Query GSI1 CUSTOMER#c begins_with ORDER#` descending | SAL-03 |
| `GetOrderAsync` | `Query ORDER#id` (ConsistentRead only right after checkout) | SAL-04 |

Strong reads are used only for login, the cart, and the order detail right after checkout (D8). GSI1 is eventually
consistent, so My orders also merges in the order that was just placed.

## Behaviour differences vs the before app
- **Order IDs and numbers:** orders are `SO-DDB-1000000001…`, not SQL `SO7xxxx`. They live only in DynamoDB and reach
  Redshift through zero-ETL. The before app's SQL orders still reach `aw-sales` through CDC, and My orders shows both,
  labelled by source.
- **Totals:** checkout adds 8% tax and 2.5% freight. The before app's demo order wrote 0 for both (SQL's trigger only
  computes the subtotal). Both are demo values.
- **Ship-to and card:** stored as snapshots on the order header (address, card type, last 4 digits). The order does not
  point at the SQL address or card rows.
- **Status:** new orders start at status 1 (In process) and sit in the sparse GSI2 `ORDERSTATUS#1` (SAL-05).
- **Admin screens:** they use the full model (category → subcategory, product model, stock) instead of LT's flat tables.
  - Products with history (photos, offers, reviews) can't be deleted; deactivate them instead.
  - Discontinued (inactive) products don't appear in the shop or search.
  - Customers can't be deleted (they have orders).
  - Stores are renamed in the store screens, not here (Phase 6+).
- **Login:** only the 5 demo customers are accepted, with the shared demo password, as before. The password hashes in
  `aw-customer` aren't used.
- **Cart:** new. Before, an order was one product placed with one click.

## Run it
- `scripts/after-up.sh` restores SQL (before stack, if needed), starts one DynamoDB Local per table, loads them with the
  Phase 3 loader, then builds and starts the app container on http://localhost:5090.
- Tests:
  - `dotnet test src/AdventureWorks.slnx` runs the unit tests.
  - `AW_DDB_IT=1 dotnet test …` adds the integration tests against the loaded DynamoDB Local.
  - `pytest tests/after` runs the Playwright smoke test.
  - CI runs all of these in `.github/workflows/after.yml`.
- In AWS: set only `DynamoDb__Region`. Credentials come from the task role. No endpoints are configured.

## Chapter 2 (C2-2) items written by the app
These are app-only items (no SQL Server source); all carry `src = ddb`, `src_lsn = "~app"` (ADR 0003).

| Table | PK / SK | Type | Written by |
|---|---|---|---|
| aw-sales | `ORDER#<id>` / `EVENT#<iso>#<seq>` | `OrderEvent` | checkout and every back-office action (My orders timeline) |
| aw-sales | `FEED#<yyyy-MM-dd>` / `<iso>#<id>` | `ChangeFeed` (TTL 7 d) | every app write; replication monitor |
| aw-sales | order header | adds `ver`, `territory_id`, `ship_method_id`, `carrier_tracking_number`; GSI2 `ORDERSTATUS#<s>` / `<iso>#<id>` while open | checkout, SAL-06 |
| aw-inventory | `PRODUCT#<id>` / `TXN#<iso>#<id>` | `InventoryTransaction` type S (ids ≥ 10,000,000) | ship (INV-03) |
| aw-catalog | `PRODUCT#<id>` / `REVIEW#…`, `REVIEWER#<customer>` | `ProductReview` + one-per-customer marker | CAT-11 |
| aw-catalog | `PRODUCT#<id>` / `PRICE#<start>` | `ListPriceHistory` | price edit (CAT-07 fix) |

Back-office territory filtering uses a `FilterExpression` on SAL-05; SAL-14 was not added.

## Chapter 2 (C2-3) items written by the app
| Table | PK / SK | Type | Written by |
|---|---|---|---|
| aw-purchasing | `PO#<id>` / `PO`, `LINE#<id>`, `POSTATUS#<s>` marker | `PurchaseOrder`, `PurchaseOrderLine` (ids ≥ 100,000, `PO-DDB-n`) | create / approve / reject / receive |
| aw-purchasing | `PO#<id>` / `EVENT#<iso>#<seq>` | `PurchaseOrderEvent` | every PO action |
| aw-purchasing | `COUNTER` / `PO` | `Counter` | create |
| aw-purchasing | `VENDOR#<id>` / `PRODUCT#<id>` | `VendorProduct` (`on_order_qty`, last receipt) | create, receive |
| aw-inventory | `PRODUCT#<id>` / `INV#<loc>`, `PRODUCT`, `TXN#<iso>#<id>` | stock by location, stock summary (REORDER GSI1), `InventoryTransaction` type P | receive (INV-01/02/03) |
| aw-sales | `FEED#<day>` | `ChangeFeed` | every PO action |

The Razor UI (Controllers/Views) was removed in C2-3; the app serves only `/api/*` and the SPA at `/app/`.
