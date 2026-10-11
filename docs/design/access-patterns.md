# Access-pattern catalog (phase 2)

Generated from `scripts/design/access_patterns.py` (source of truth) together with [`access-patterns.json`](access-patterns.json). Status: **approved by John (2026-10-11)** with decisions D1–D10 below — no key design here (phase 3).

## Decisions (2026-10-11)

| ID | Decision |
|---|---|
| D1 | Shopper read multipliers (x10 browse, x5 detail, x3 history per order) and a demo peak of ~1 order/s are accepted for sizing. |
| D2 | Product search (CAT-12): case-insensitive name-prefix in DynamoDB for the demo; OpenSearch (zero-ETL) later. |
| D3 | Carts (SAL-01) only for logged-in customers (cartId = customerId); items expire via TTL after 7 days. |
| D4 | The .NET 10 app writes orders directly to DynamoDB; the old app keeps writing SQL, which flows one-way via CDC (side-by-side cutover). |
| D5 | DynamoDB-created orders get ids from a range above SQL's, with a source prefix on the order number. |
| D6 | Phase 3 key design covers all 7 domains, including back-office patterns. |
| D7 | Territory and sales-person lists (SAL-08, SAL-09, CUS-10) are served by Redshift only. |
| D8 | Strong consistency only for login (CUS-01), cart (SAL-01) and read-after-checkout (SAL-04 right after SAL-02); everything else eventual. |
| D9 | Product descriptions kept in all 6 cultures (CAT-13). |
| D10 | SQL deletes become tombstone items in DynamoDB (TTL later) so Redshift sees deletes (CDC-02). |

Frequency estimates come from AdventureWorks2022 row counts: 31,465 orders over 37 months (2011-05-31 → 2014-06-30) ≈ 28 orders/day (27,659 online), 121,317 lines (max 72/order), max 28 orders per customer, 19,820 customers, 504 products (197 sellable with the no-discount offer), 4,012 POs, 72,591 work orders. Shopper read multipliers (×10 browse, ×5 detail, ×3 history per order) are assumptions to confirm.

Scope: **dynamodb** = must be served by the domain table's keys/indexes in phase 3 · **redshift** = served via zero-ETL, no keys · **opensearch-or-defer** / **out-of-scope** as marked.

## Counts

| Domain | Table | Patterns | DynamoDB | Redshift | Other | Shopper | Hard |
|---|---|---|---|---|---|---|---|
| Catalog | `aw-catalog` | 13 | 13 | 0 | 0 | 8 | 1 |
| Inventory & Manufacturing | `aw-inventory` | 7 | 6 | 1 | 0 | 0 | 4 |
| Sales | `aw-sales` | 13 | 10 | 3 | 0 | 4 | 1 |
| Customer & Party | `aw-customer` | 11 | 10 | 1 | 0 | 4 | 1 |
| Purchasing | `aw-purchasing` | 7 | 7 | 0 | 0 | 0 | 0 |
| HR | `aw-hr` | 6 | 5 | 0 | 1 | 0 | 2 |
| Reference | `aw-reference` | 5 | 5 | 0 | 0 | 3 | 0 |
| Cross-cutting | `(all)` | 8 | 4 | 4 | 0 | 0 | 2 |
| **Total** | | **70** | 60 | 9 | 1 | 19 | 11 |

## Shopper journey coverage

| Page | Patterns |
|---|---|
| Browse by category | CAT-01, CAT-03, (CAT-12 search) |
| Product detail | CAT-04, CAT-08, CAT-10, CAT-11, CAT-13, INV-01 (copied stock) |
| Cart | SAL-01 (+ CAT-10 pricing) |
| Login / account | CUS-01, CUS-02, CUS-09 |
| Checkout | CUS-03, REF-01, REF-02, REF-04, CAT-10, SAL-02 |
| Order history | SAL-03, SAL-04 |

## Hard for single-table design → proposed approach

| ID | Pattern | Why hard | Proposed approach |
|---|---|---|---|
| CAT-12 | Search products by free text (name, description, color) | ad hoc / free-text search; DynamoDB only supports key-prefix matching | DECIDED (D2): demo = case-insensitive name-prefix (begins_with on a normalized name key). Later: OpenSearch via DynamoDB zero-ETL for full text. |
| INV-02 | Which products are below their reorder point / safety stock? | filter across all products comparing two values | Sparse 'needs reorder' marker maintained when stock changes (written by the same stream that updates totals); or Redshift report. |
| INV-04 | Explode the bill of materials for an assembly (all levels, as of a date) | recursive (multi-level) traversal | Store BOM edges per assembly; app iterates levels (max depth ~4, 2,679 edges) or keep a materialized flattened tree per top-level assembly, rebuilt on change. |
| INV-05 | Where is this component used? | reverse recursive traversal | Inverted index on BOM edges (component -> assembly), iterate levels in app. |
| INV-07 | Daily inventory balance per product (history) | large aggregate over time | Redshift: rebuild from zero-ETL'd transaction history (phase 6). No DynamoDB keys. |
| SAL-11 | Sales by sales person by fiscal year | large aggregate / pivot across all orders | Redshift view over zero-ETL data (phase 6); not a DynamoDB key. |
| CUS-11 | Contact info for any business entity (person, store, vendor contact, employee) | polymorphic lookup across domains (vendor contacts, employees, store contacts) | Customer & Party owns all persons, so keep a person item keyed by businessEntityId; Purchasing/HR keep copies of what they display. |
| HR-03 | Who reports to this manager (all levels) / what is this employee's management chain? | recursive hierarchy (hierarchyid) | Store the materialized org path (e.g. /1/4/3/) as a sort key → subtree = begins_with; chain = parse path. 290 employees, so client-side is also fine. |
| HR-06 | List job candidates; search résumés by text | full-text search over XML résumés (13 rows) | Out of scope for keys; if needed, OpenSearch or a client-side filter over 13 items. |
| CDC-03 | Fan out a source change to denormalized copies in other items/domains | cross-domain joins replaced by copies | Event-driven refresh via DynamoDB Streams/EventBridge; immutable snapshots (order lines, order addresses) are never refreshed. |
| DW-04 | Any aggregate report (sales by period/territory/category, top products, inventory balance) | large aggregates / ad hoc analytics | Redshift + QuickSight only; no GSIs for reporting. |

## Catalog — `aw-catalog`

**One-page summary.** Everything a shopper browses: categories, products, models, descriptions, photos, reviews, price history and offers. Read-dominated (browse/detail pages) with rare admin writes; must serve the shopper pages with one request per page. Owner: Merchandising. 13 patterns (8 shopper-facing, 0 served from Redshift).

| ID | Question (business words) | Actor / screen | Inputs | Expected result | Frequency / volume | R/W | Consistency | Sort / filter | Scope | Source |
|---|---|---|---|---|---|---|---|---|---|---|
| CAT-01 | What product categories (and their subcategories) can I shop? 🛒 | Shopper: browse nav; App: ProductCategories Index | – | 4 categories, 37 subcategories with names | every page view (cacheable); data changes ~never | R | eventual | sort: by name | dynamodb | screen:ProductCategories/Index<br>screen:Shop (nav)<br>table:Production.ProductCategory<br>table:Production.ProductSubcategory |
| CAT-02 | Show / create / edit / delete a category or subcategory | Admin: ProductCategories CRUD | categoryId \| subcategoryId | one category/subcategory | rare (<10/day) | R/W | strong after write | – | dynamodb | screen:ProductCategories/Details\|Create\|Edit\|Delete |
| CAT-03 | Which products are in this subcategory that I can buy now? 🛒 | Shopper: browse by category | subcategoryId, page | products (name, number, color, size, list price, thumbnail, in-stock flag), ~5–40 per subcategory | high: most frequent shopper read (~10x orders) | R | eventual | sort: name or list price asc/desc; filter: sellable now (SellEndDate null / not discontinued); optional color/size | dynamodb | screen:Shop/Index<br>screen:Products/Index<br>table:Production.Product |
| CAT-04 | Show me everything about this product 🛒 | Shopper: product detail; App: Products Details | productId (or product number) | product + model + description (culture) + photos + active offers + review summary + stock flag | high (~5x orders) | R | eventual | sort: reviews newest first | dynamodb | screen:Products/Details<br>view:Production.vProductAndDescription<br>fn:dbo.ufnGetProductListPrice<br>fn:dbo.ufnGetStock |
| CAT-05 | Find a product by its product number (SKU) | Back office, CDC, order entry | productNumber | product | medium | R | eventual | – | dynamodb | table:Production.Product (AK_Product_ProductNumber) |
| CAT-06 | List all products (admin grid) | Admin: Products Index | page | products with category + model name | low | R | eventual | sort: name | dynamodb | screen:Products/Index |
| CAT-07 | Create / update / retire a product | Admin: Products CRUD | product fields | product written; name & number unique | rare | W | strong (conditional write for uniqueness) | – | dynamodb | screen:Products/Create\|Edit\|Delete<br>trigger:none |
| CAT-08 | What products belong to this model, and what is the model's catalog description/instructions? 🛒 | Shopper (variants: colors/sizes); Admin | productModelId | model + its products (variants) | medium | R | eventual | sort: size/color | dynamodb | view:Production.vProductModelCatalogDescription<br>view:Production.vProductModelInstructions<br>table:Production.ProductModel |
| CAT-09 | What was this product's list price / standard cost on a given date? | Order pricing audit; DW DimProduct SCD2 | productId, date | price/cost effective on that date | low online; bulk in analytics | R | eventual | sort: by start date | dynamodb | fn:dbo.ufnGetProductListPrice<br>fn:dbo.ufnGetProductStandardCost<br>dw:DimProduct |
| CAT-10 | Which special offers apply to this product today? 🛒 | Shopper: product detail / cart pricing | productId, date | active offers (discount %, min/max qty) | high (with CAT-04 / checkout) | R | eventual | filter: StartDate <= today <= EndDate | dynamodb | table:Sales.SpecialOffer<br>table:Sales.SpecialOfferProduct<br>fn:dbo.ufnGetProductDealerPrice |
| CAT-11 | Show / add reviews for a product 🛒 | Shopper | productId | reviews newest first | low (4 reviews exist) | R/W | eventual | sort: ReviewDate desc | dynamodb | table:Production.ProductReview |
| CAT-12 | Search products by free text (name, description, color) ⚠ 🛒 | Shopper: search box | text | matching products ranked | medium | R | eventual | – | dynamodb | business |
| CAT-13 | Show the culture-specific description (en, fr, es, ...) 🛒 | Shopper (localized site) | productModelId, culture | description text | low | R | eventual | – | dynamodb | table:Production.ProductModelProductDescriptionCulture |

Notes: **CAT-02** Delete must be refused while products reference it (was an FK). **CAT-03** 504 products total, 197 currently sellable with a no-discount offer. Price sort needs a second ordering. **CAT-04** Pre-join: model/description/photos/offers fetched with the product in one request; stock is a copied value from Inventory. **CAT-05** ProductNumber and Name are unique in SQL; uniqueness must be enforced on write. **CAT-06** 504 items: paged full listing; fine as a scan of a small type or an index over all products. **CAT-07** Price change must also append a list-price history record (CAT-09). **CAT-09** 395 list + 395 cost history rows. **CAT-12** Name-prefix only for the demo (D2). **CAT-13** All 6 cultures kept (D9).

## Inventory & Manufacturing — `aw-inventory`

**One-page summary.** Stock per location, inventory movements, bills of materials and work orders. Write-heavy back-office data; only 'is it in stock' reaches the shopper, as a pre-aggregated copy on the product. Owner: Operations. 7 patterns (0 shopper-facing, 1 served from Redshift).

| ID | Question (business words) | Actor / screen | Inputs | Expected result | Frequency / volume | R/W | Consistency | Sort / filter | Scope | Source |
|---|---|---|---|---|---|---|---|---|---|---|
| INV-01 | How many units of this product are on hand, per location and in total? | Back office; feeds Catalog stock flag | productId | qty per location (14 locations), total | medium; on every inventory change for the copy | R | eventual | – | dynamodb | fn:dbo.ufnGetStock<br>table:Production.ProductInventory |
| INV-02 | Which products are below their reorder point / safety stock? ⚠ | Planner (daily) | – | products needing reorder | low (daily) | R | eventual | filter: total qty < ReorderPoint | dynamodb | business<br>table:Production.Product.ReorderPoint |
| INV-03 | Record a stock movement and list movements for a product over a date range | Warehouse, order fulfilment (trigger today), DW | productId, date range | transactions newest first | ~370/day writes (113k + 89k archive rows / ~16 months) | R/W | eventual | sort: TransactionDate desc | dynamodb | table:Production.TransactionHistory<br>table:Production.TransactionHistoryArchive<br>trigger:Sales.iduSalesOrderDetail<br>dw:FactProductInventory |
| INV-04 | Explode the bill of materials for an assembly (all levels, as of a date) ⚠ | Engineering | productAssemblyId, date | component tree with quantities | low | R | eventual | – | dynamodb | proc:dbo.uspGetBillOfMaterials<br>table:Production.BillOfMaterials |
| INV-05 | Where is this component used? ⚠ | Engineering | componentId, date | assemblies using it (multi-level) | low | R | eventual | – | dynamodb | proc:dbo.uspGetWhereUsedProductID |
| INV-06 | Which work orders are open / due, and what are a work order's routing steps? | Production planner | date range \| workOrderId | work orders by due date; one WO with routings | ~66 WOs/day (72,591 over 3 years) | R/W | eventual | sort: DueDate; filter: not finished (EndDate null) | dynamodb | table:Production.WorkOrder<br>table:Production.WorkOrderRouting<br>trigger:iWorkOrder/uWorkOrder |
| INV-07 | Daily inventory balance per product (history) ⚠ | Analyst | date range | product x day quantities | batch | R | eventual | – | redshift | dw:FactProductInventory (776,286 rows) |

Notes: **INV-01** 1,069 rows. Total is pushed to Catalog (CAT-04/03) as a denormalized copy via Streams. **INV-03** In SQL the order-detail trigger writes a TransactionHistory row per order line; in the target this becomes an event from Sales, not a cross-table write.

## Sales — `aw-sales`

**One-page summary.** Carts, checkout, orders and lines, and the sales organisation (sales people, quotas, territories). Hot path of the live demo: the order a test customer places flows SQL -> CDC -> DynamoDB here. Owner: Sales. 13 patterns (4 shopper-facing, 3 served from Redshift).

| ID | Question (business words) | Actor / screen | Inputs | Expected result | Frequency / volume | R/W | Consistency | Sort / filter | Scope | Source |
|---|---|---|---|---|---|---|---|---|---|---|
| SAL-01 | Add / change / remove an item in my cart, and show my cart 🛒 | Shopper: cart | cartId (= customer or anonymous session), productId, qty | cart lines with current product name/price | ~10x orders | R/W | strong (read-your-writes) | sort: date added | dynamodb | table:Sales.ShoppingCartItem<br>shopper:cart |
| SAL-02 | Check out: turn my cart into an order (header + lines) with tax, freight, totals 🛒 | Shopper: checkout; demo Shop/Order | customerId, cart, ship-to/bill-to address, ship method, card | new order id/number | ~28/day historic (31,465 orders / 37 months); demo bursts | W | strong; atomic (transaction) | – | dynamodb | screen:Shop/Order (demo)<br>trigger:Sales.iduSalesOrderDetail (SubTotal)<br>table:Sales.SalesOrderHeader<br>table:Sales.SalesOrderDetail |
| SAL-03 | Show my order history, newest first 🛒 | Shopper: My orders | customerId, page | orders (number, date, status, total, line summary) | ~3x orders | R | eventual (read-after-checkout uses SAL-04 strong, D8) | sort: OrderDate desc | dynamodb | screen:Shop/MyOrders (demo)<br>table:Sales.SalesOrderHeader |
| SAL-04 | Show one order with its lines (and sales reasons) 🛒 | Shopper; customer service | salesOrderId or SalesOrderNumber | header + lines + reasons | ~3x orders | R | strong right after checkout (D8), else eventual | – | dynamodb | table:Sales.SalesOrderDetail<br>table:Sales.SalesOrderHeaderSalesReason |
| SAL-05 | Which orders are in status X (e.g. in process / to ship) by date? | Fulfilment | status, date range | orders | low-medium | R | eventual | sort: OrderDate; filter: status | dynamodb | fn:dbo.ufnGetSalesOrderStatusText<br>business |
| SAL-06 | Ship / cancel / revise an order | Fulfilment; customer service | salesOrderId | order updated (status, ship date, revision) | ~orders | W | strong; conditional on current status/revision | – | dynamodb | trigger:Sales.uSalesOrderHeader (RevisionNumber/ModifiedDate) |
| SAL-07 | Orders for a store / reseller over a date range | Sales rep; store portal | customerId (store) , date range | orders | low | R | eventual | sort: OrderDate desc | dynamodb | dw:FactResellerSales<br>table:Sales.SalesOrderHeader |
| SAL-08 | Orders taken by a sales person over a date range | Sales manager | salesPersonId, date range | orders | low | R | eventual | sort: OrderDate desc | redshift | business<br>dw:FactResellerSales |
| SAL-09 | Orders in a territory over a date range | Sales manager | territoryId, date range | orders | low | R | eventual | sort: OrderDate desc | redshift | business |
| SAL-10 | Sales person profile with quota history and YTD/last-year sales | Sales manager | salesPersonId | sales person, territory, quotas by quarter, YTD figures | low | R | eventual | sort: QuotaDate | dynamodb | view:Sales.vSalesPerson<br>table:Sales.SalesPersonQuotaHistory |
| SAL-11 | Sales by sales person by fiscal year ⚠ | Sales manager | – | pivot of sales per person per FY | low | R | eventual | – | redshift | view:Sales.vSalesPersonSalesByFiscalYears |
| SAL-12 | Which sales people cover a territory (now and historically)? | Sales manager | territoryId | sales people with start/end | low | R | eventual | sort: StartDate | dynamodb | table:Sales.SalesTerritoryHistory<br>table:Sales.SalesTerritory |
| SAL-13 | Find an order by purchase order number or card approval code | Customer service | PO number \| approval code | order | low | R | eventual | – | dynamodb | business |

Notes: **SAL-01** Logged-in customers only, cartId = customerId; 7-day TTL (D3). Only 3 rows today. Product name/price read from Catalog at render time. **SAL-02** Needs product price/offer (CAT-10), tax rate (REF-02), ship method (REF-04), address/card snapshot (CUS-03). Header SubTotal maintained in the same transaction (replaces trigger). Max 72 lines/order today. The .NET 10 app writes orders directly to DynamoDB; the old app writes SQL and flows via CDC (one-way, side-by-side cutover) (D4). DynamoDB-created orders get ids from a range above SQL's with a source prefix (D5). **SAL-03** Max 28 orders per customer today; bounded. **SAL-05** All 31,465 historical orders are status 5 (shipped) → only new orders are 'open'; sparse. **SAL-08** Redshift only (D7). **SAL-09** Redshift only (D7); 10 territories would be coarse partitions. **SAL-10** SalesYTD/SalesLastYear are stored aggregates in SQL → maintain as pre-aggregated counters on order write. **SAL-13** Candidate for a sparse lookup; or accept Redshift for rare lookups (decide in phase 3).

## Customer & Party — `aw-customer`

**One-page summary.** Identity and profile: persons, stores, logins, emails, phones, addresses, payment cards, store contacts. Serves login, checkout address/card selection and the customer screens. Owner: Customer service. 11 patterns (4 shopper-facing, 1 served from Redshift).

| ID | Question (business words) | Actor / screen | Inputs | Expected result | Frequency / volume | R/W | Consistency | Sort / filter | Scope | Source |
|---|---|---|---|---|---|---|---|---|---|---|
| CUS-01 | Log me in with my email and password 🛒 | Shopper: login; demo Account/Login | email, password | customer id, display name, default address | ~orders x 2 | R | strong | – | dynamodb | screen:Account/Login (demo)<br>table:Person.EmailAddress<br>table:Person.Password |
| CUS-02 | Show my profile: name, emails, phones, addresses, saved cards (masked) 🛒 | Shopper: account / checkout | customerId | profile with addresses & cards | ~orders x 2 | R | eventual | – | dynamodb | screen:Customers/Details<br>view:Sales.vIndividualCustomer<br>fn:dbo.ufnGetContactInformation |
| CUS-03 | Which addresses / cards can I use at checkout? 🛒 | Shopper: checkout | customerId | addresses by type (billing/shipping/home), cards (type, last4, expiry) | ~orders | R | eventual | – | dynamodb | table:Person.BusinessEntityAddress<br>table:Sales.PersonCreditCard |
| CUS-04 | Register / update / delete a customer (unique account number and email) | Shopper sign-up; Admin Customers CRUD | customer fields | customer written | low | W | strong; conditional (uniqueness) | – | dynamodb | screen:Customers/Create\|Edit\|Delete<br>trigger:Person.iuPerson |
| CUS-05 | List customers (admin grid), paged | Admin: Customers Index | page | customers | low | R | eventual | sort: name | dynamodb | screen:Customers/Index |
| CUS-06 | Find a customer by account number | Customer service; CDC; DW | accountNumber (AW000xxxxx) | customer | medium | R | eventual | – | dynamodb | dw:DimCustomer.CustomerAlternateKey<br>table:Sales.Customer (AK_Customer_AccountNumber) |
| CUS-07 | Show a store with its contacts, addresses and demographics | Sales rep | storeId | store + contacts (role) + addresses + demographics | low | R | eventual | – | dynamodb | view:Sales.vStoreWithContacts<br>view:Sales.vStoreWithAddresses<br>view:Sales.vStoreWithDemographics |
| CUS-08 | Show a person's demographics | Marketing; DW | personId | income, education, occupation, cars, children, ... | low | R | eventual | – | dynamodb | view:Sales.vPersonDemographics<br>dw:DimCustomer |
| CUS-09 | Add / update my address, email, phone or card 🛒 | Shopper: account | customerId, value | updated profile | low | W | eventual | – | dynamodb | shopper:account |
| CUS-10 | Customers in a territory | Sales manager | territoryId | customers | low | R | eventual | – | redshift | business |
| CUS-11 | Contact info for any business entity (person, store, vendor contact, employee) ⚠ | Back office | businessEntityId | name, job title, type, phone, email | low | R | eventual | – | dynamodb | fn:dbo.ufnGetContactInformation<br>view:Person.vAdditionalContactInfo |

Notes: **CUS-01** Email must be unique across persons (19,972 emails). Password hash/salt in SQL; demo uses a shared password. **CUS-05** 19,820 customers; paged scan of one type is acceptable for admin. **CUS-08** Keep the XML as a map; DW needs it. **CUS-09** Changing an address does not change past orders (orders carry a snapshot). **CUS-10** Redshift only (D7).

## Purchasing — `aw-purchasing`

**One-page summary.** Vendors, which products they supply, and purchase orders. Low volume back-office workload. Owner: Procurement. 7 patterns (0 shopper-facing, 0 served from Redshift).

| ID | Question (business words) | Actor / screen | Inputs | Expected result | Frequency / volume | R/W | Consistency | Sort / filter | Scope | Source |
|---|---|---|---|---|---|---|---|---|---|---|
| PUR-01 | Show a vendor with addresses and contacts | Buyer | vendorId | vendor + addresses + contacts | low | R | eventual | – | dynamodb | view:Purchasing.vVendorWithAddresses<br>view:Purchasing.vVendorWithContacts |
| PUR-02 | Who can supply this product, at what price and lead time? | Buyer | productId | vendors with std price, lead time, min/max qty | low | R | eventual | – | dynamodb | table:Purchasing.ProductVendor |
| PUR-03 | What does this vendor supply? | Buyer | vendorId | products | low | R | eventual | – | dynamodb | table:Purchasing.ProductVendor |
| PUR-04 | Create a purchase order and show it with its lines | Buyer | vendorId, lines \| poId | PO + lines | ~3 POs/day (4,012 / 41 months) | R/W | strong (totals maintained in same transaction) | – | dynamodb | trigger:iPurchaseOrderDetail/uPurchaseOrderDetail/uPurchaseOrderHeader |
| PUR-05 | Purchase orders for a vendor, newest first, optionally by status | Buyer | vendorId, status? | POs | low | R | eventual | sort: OrderDate desc; filter: status | dynamodb | fn:dbo.ufnGetPurchaseOrderStatusText |
| PUR-06 | Purchase orders raised by an employee | Purchasing manager | employeeId | POs | low | R | eventual | sort: OrderDate desc | dynamodb | business |
| PUR-07 | Open purchase orders (pending/approved) to receive | Warehouse | status | POs | low | R | eventual | filter: status in (1,2) | dynamodb | business |

Notes: **PUR-03** Many-to-many with PUR-02 (460 edges). **PUR-07** Sparse: few open POs.

## HR — `aw-hr`

**One-page summary.** Employees, departments, shifts, pay history, org chart, candidates. Small but sensitive; isolated table and IAM. Owner: HR. 6 patterns (0 shopper-facing, 0 served from Redshift).

| ID | Question (business words) | Actor / screen | Inputs | Expected result | Frequency / volume | R/W | Consistency | Sort / filter | Scope | Source |
|---|---|---|---|---|---|---|---|---|---|---|
| HR-01 | Show an employee with current department, shift, job title and pay | HR; manager | employeeId | employee profile | low | R | strong for pay edits | – | dynamodb | view:HumanResources.vEmployee<br>view:HumanResources.vEmployeeDepartment |
| HR-02 | Show an employee's department and pay history | HR | employeeId | history newest first | low | R | eventual | sort: StartDate/RateChangeDate desc | dynamodb | view:HumanResources.vEmployeeDepartmentHistory<br>table:HumanResources.EmployeePayHistory |
| HR-03 | Who reports to this manager (all levels) / what is this employee's management chain? ⚠ | Manager; org chart | employeeId | subtree / chain | low | R | eventual | – | dynamodb | proc:dbo.uspGetManagerEmployees<br>proc:dbo.uspGetEmployeeManagers<br>column:Employee.OrganizationNode (hierarchyid) |
| HR-04 | Who is currently in this department? | Manager | departmentId | employees | low | R | eventual | filter: EndDate null | dynamodb | business |
| HR-05 | Update hire info, login, personal info | HR | employeeId, fields | employee updated | rare | W | strong | – | dynamodb | proc:HumanResources.uspUpdateEmployeeHireInfo<br>proc:HumanResources.uspUpdateEmployeeLogin<br>proc:HumanResources.uspUpdateEmployeePersonalInfo |
| HR-06 | List job candidates; search résumés by text ⚠ | Recruiter | text | candidates | rare | R | eventual | – | out-of-scope | view:HumanResources.vJobCandidate*<br>proc:dbo.uspSearchCandidateResumes |

## Reference — `aw-reference`

**One-page summary.** Shared lookups: countries, states, currencies and FX rates, tax rates, ship methods, units, cultures. Read-mostly, cached by apps and copied into other domains' items. Owner: Platform. 5 patterns (3 shopper-facing, 0 served from Redshift).

| ID | Question (business words) | Actor / screen | Inputs | Expected result | Frequency / volume | R/W | Consistency | Sort / filter | Scope | Source |
|---|---|---|---|---|---|---|---|---|---|---|
| REF-01 | List countries, and states/provinces for a country 🛒 | Shopper: address forms | countryCode? | countries (238) / states (181) | every address form (cache) | R | eventual | sort: name | dynamodb | view:Person.vStateProvinceCountryRegion |
| REF-02 | What sales tax applies to a ship-to state? 🛒 | Checkout | stateProvinceId | tax rates (29 rows) | ~orders | R | eventual | – | dynamodb | table:Sales.SalesTaxRate |
| REF-03 | What was the exchange rate between two currencies on a date? | Checkout (foreign currency); DW | from, to, date | average & end-of-day rate | ~orders (non-USD) | R | eventual | sort: date | dynamodb | table:Sales.CurrencyRate (13,532)<br>dw:FactCurrencyRate |
| REF-04 | Which ship methods are available and what do they cost? 🛒 | Checkout | – | 5 ship methods with base/rate | ~orders (cache) | R | eventual | – | dynamodb | table:Purchasing.ShipMethod |
| REF-05 | List currencies, units of measure, cultures | Admin forms | – | small lists | low (cache) | R | eventual | – | dynamodb | table:Sales.Currency<br>table:Production.UnitMeasure<br>table:Production.Culture |

## Cross-cutting — `(all)`

**One-page summary.** Patterns every domain must support for replication and analytics: idempotent CDC upserts/deletes and the zero-ETL feed to Redshift. Owner: Platform. 8 patterns (0 shopper-facing, 4 served from Redshift).

| ID | Question (business words) | Actor / screen | Inputs | Expected result | Frequency / volume | R/W | Consistency | Sort / filter | Scope | Source |
|---|---|---|---|---|---|---|---|---|---|---|
| CDC-01 | Apply a source change (insert/update) to the target item(s), idempotently, keyed by the SQL primary key | CDC Lambda (DMS→Kinesis) / Debezium consumer | source table, source PK, after-image, LSN/commit ts | target item(s) upserted | every OLTP write (68 tables); demo bursts | W | conditional on LSN (ignore older) | – | dynamodb | cdc:all 68 tables |
| CDC-02 | Apply a source delete | CDC consumer | source table, PK, LSN | target item(s) tombstoned | low | W | conditional on LSN | – | dynamodb | cdc:all 68 tables |
| CDC-03 | Fan out a source change to denormalized copies in other items/domains ⚠ | CDC consumer / stream processor | changed entity | copies refreshed (e.g. product name on catalog listings, person name on employee) | low-medium | W | eventual | – | dynamodb | docs/discovery/domains.md (break/duplicate table) |
| CDC-04 | Child row arrives before its parent (e.g. order line before header) | CDC consumer | child change | item written without waiting for parent | per transaction | W | eventual | – | dynamodb | cdc ordering |
| DW-01 | Land all domain data in Redshift continuously | DynamoDB zero-ETL → Redshift | – | SUPER rows per item | continuous | R | eventual | – | redshift | dw:all facts/dims |
| DW-02 | Rebuild FactInternetSales / FactResellerSales / FactInternetSalesReason / FactSalesQuota | Redshift SQL (phase 6) | order + line items, offers, cost at order date | fact rows | batch / materialized views | R | eventual | – | redshift | dw:FactInternetSales<br>dw:FactResellerSales<br>dw:FactInternetSalesReason<br>dw:FactSalesQuota |
| DW-03 | Rebuild DimCustomer / DimReseller / DimGeography / DimProduct (SCD2) / DimEmployee / DimPromotion / DimCurrency / DimSalesTerritory | Redshift SQL | domain items | dimension rows | batch | R | eventual | – | redshift | dw:Dim* |
| DW-04 | Any aggregate report (sales by period/territory/category, top products, inventory balance) ⚠ | Analyst / QuickSight | any | aggregates | ad hoc | R | eventual | – | redshift | dw:views<br>view:Sales.vSalesPersonSalesByFiscalYears |

Notes: **CDC-01** Requires every target item to be addressable from its source PK (deterministic key) and to carry the last-applied LSN. **CDC-02** DECIDED (D10): SQL deletes become tombstone items (deleted flag, TTL later) so zero-ETL/Redshift sees the delete; e.g. reset-demo deletes demo orders. **CDC-04** Design keys so a child can be written using only its own source columns (no lookup of the parent required). **DW-01** Needs entityType + plain-named business attributes on every item (not only inside PK/SK). **DW-02** Order/line items must keep: OnlineOrderFlag, CustomerID, StoreID, SalesPersonID, TerritoryID, CurrencyRateID, SpecialOfferID, product standard cost at order date, dates. **DW-03** Keep demographics maps, price/cost history and employee history items so dimensions can be derived.

Legend: ⚠ hard for single-table design (see table above) · 🛒 needed by the shopper pages.

