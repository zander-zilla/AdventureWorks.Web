# Proposed domain split (phase 1 draft)

Source of truth: [`domains.json`](domains.json) (machine-readable, feeds the phase-8 mapping file).
Per-domain ERDs (mermaid) and the full cross-domain FK list are generated into [`domain-diagrams.md`](domain-diagrams.md).

All 71 OLTP tables are assigned: 68 to 7 domains, 3 `dbo` plumbing tables excluded.

| Domain | DynamoDB table | SQL tables | Rows (approx) | Why it is its own domain |
|---|---|---|---|---|
| Catalog | `aw-catalog` | 17 (Product*, categories, models, descriptions, photos, reviews, price/cost history, documents, SpecialOffer/SpecialOfferProduct) | ~5k | Read-heavy, shopper-facing, low change rate; cacheable; the "product page" item collection |
| Inventory & Manufacturing | `aw-inventory` | 8 (ProductInventory, Location, BillOfMaterials, WorkOrder(+Routing), ScrapReason, TransactionHistory(+Archive)) | ~330k | Write-heavy operational data with a different owner/cadence than the catalog; only "stock available" crosses into shopping |
| Sales | `aw-sales` | 9 (orders, lines, reasons, cart, sales people, quotas, territories) | ~200k | Highest write volume, the live CDC demo target; order is the aggregate root |
| Customer & Party | `aw-customer` | 15 (Customer, Store, Person, BusinessEntity*, Email, Phone, Password, Address*, CreditCard*, contacts) | ~200k | The "who": login/profile/addresses/payment; shared identity for customers, store contacts, vendors' contacts and employees |
| Purchasing | `aw-purchasing` | 4 (Vendor, ProductVendor, PO header/detail) | ~13k | Supplier side, independent lifecycle |
| HR | `aw-hr` | 6 | ~1k | Sensitive (pay, national ID, birth date) → separate IAM boundary |
| Reference | `aw-reference` | 9 (CountryRegion, StateProvince, Currency, CountryRegionCurrency, CurrencyRate, SalesTaxRate, ShipMethod, UnitMeasure, Culture) | ~14k (13.5k FX rates) | Tiny shared lookups used by ≥2 domains; cached in-app and copied into consumers |

Rationale notes
- **Sales.Customer / Store / CreditCard live in Customer & Party, not Sales.** The SQL schema names follow the original ownership, but the access patterns (log in, show profile/addresses/cards, list a store's contacts) are identity patterns; Sales only needs `customerId` + a name/account-number snapshot.
- **SpecialOffer moves to Catalog**: offers are product-pricing data read on product pages; Sales copies the applied discount onto the line.
- **SalesTerritory stays in Sales** (it is the sales org: people, quotas, territory history); Reference keeps geography (country/state) which carries a `TerritoryID` snapshot.
- **BusinessEntity super-type** (Person/Store/Vendor share `BusinessEntityID`) is kept as an id space in Customer & Party; Vendor (Purchasing) and Employee (HR) reference it by id and copy name/contact fields.
- Inventory was split from Catalog because `TransactionHistory` (~200k rows incl. archive) and work orders would dominate a catalog table and have very different write patterns.

## Cross-domain relationships: break or duplicate

31 cross-domain FKs exist (list in `domain-diagrams.md`). Proposed handling:

| Relationship | Decision | Copied attributes (snapshot) / mechanism |
|---|---|---|
| Order line → Product / SpecialOfferProduct | **Duplicate** onto line at order time (immutable history) | productId, name, productNumber, color, size, unitPrice, discount, offer description |
| Order → Customer | Break FK, **duplicate** small snapshot | customerId, accountNumber, display name, store name |
| Order → Bill/Ship Address | **Duplicate** the address value onto the order (address at time of order) | full address lines, city, state code, postal code, country |
| Order → CreditCard | Break; keep `creditCardId` + last-4 + type only | (never copy card number) |
| Order → ShipMethod / CurrencyRate | Duplicate code+name / rate value | shipMethodName, rate, currency codes |
| Cart item → Product | Reference by id; read price/name from Catalog at render time (cart is short-lived) | – |
| Customer → SalesTerritory; Store → SalesPerson | Reference by id + name snapshot; refreshed by Sales events | territoryName, salesPersonName |
| Address → StateProvince/CountryRegion | **Duplicate** codes+names into address (lookups are near-static) | stateCode, stateName, countryCode, countryName |
| Inventory / BOM / WorkOrder / TransactionHistory → Product | Reference by id + name/number snapshot | productNumber, name |
| Catalog "in stock" ← ProductInventory | **Pre-aggregate**: Inventory publishes total qty per product; Catalog stores `stockQty` on product item | event-driven (Streams/EventBridge) |
| Vendor → BusinessEntity; ProductVendor/PO → Product | Reference by id + snapshot | vendor name; product name/number |
| PO → Employee; Document → Employee; SalesPerson → Employee | Reference by id + employee display name | name, jobTitle |
| Employee → Person | Employee item embeds name/contact copy (HR owns its own copy, refreshed from Customer & Party events) | first/last name, email, phone |
| Product → UnitMeasure; *Culture | Duplicate codes (they are already natural keys) | unit code / culture code |

## LT → full mapping (what backs each AdventureWorks.Web screen)

The app is built on AdventureWorksLT (`SalesLT` schema). LT is a flattened subset of the full OLTP DB:

| LT table | Full OLTP source(s) | Notes |
|---|---|---|
| SalesLT.Customer | Sales.Customer ⨝ Person.Person ⨝ Person.EmailAddress ⨝ Person.PersonPhone ⨝ Person.Password; CompanyName from Sales.Store; SalesPerson from Sales.SalesPerson → Person.Person (login) | LT customers are **store contacts**; CustomerIDs **match** full-DB `Sales.Customer.CustomerID` (verified: 29485 → PersonID 293 Catherine Abel, StoreID 294), so the demo users map 1:1 to full-DB customers |
| SalesLT.Address | Person.Address ⨝ StateProvince ⨝ CountryRegion | State/country flattened to names |
| SalesLT.CustomerAddress | Person.BusinessEntityAddress ⨝ AddressType | AddressType as text |
| SalesLT.Product | Production.Product (+ ProductProductPhoto/ProductPhoto for ThumbNailPhoto) | ProductIDs match the full DB. LT `ProductCategoryID` is at the full `ProductSubcategory` level, same names but **different ids** (LT id = full subcategory id + 4, e.g. Road Frames 18 ↔ 14) → map by name |
| SalesLT.ProductCategory | Production.ProductCategory (top level) + ProductSubcategory (children via ParentProductCategoryID) | 2-level hierarchy flattened into one self-referencing table |
| SalesLT.ProductModel | Production.ProductModel | CatalogDescription XML kept |
| SalesLT.ProductDescription / ProductModelProductDescription | Production.ProductDescription / ProductModelProductDescriptionCulture | |
| SalesLT.SalesOrderHeader / Detail | Sales.SalesOrderHeader / SalesOrderDetail (+ ShipMethod name) | LT has 32 seeded orders (SalesOrderIDs 71774–71946; the full DB has those same ids, max 75123). New LT orders get identity 71947+, which **collides** with existing full-DB orders → demo orders need a separate id namespace when merged into `aw-sales`; full has 31,465 |

| Screen (controller/action) | LT tables today | Full-domain source after phase 5 |
|---|---|---|
| ProductCategories Index/Details/CRUD (home page) | ProductCategory (self-ref parent) | Catalog: Category + Subcategory items |
| Products Index/Details/CRUD (incl. category + model dropdowns) | Product, ProductCategory, ProductModel | Catalog: Product, Subcategory, Category, Model |
| Customers Index/Details/CRUD | Customer | Customer & Party: Customer + Person (+ Store) + Email/Phone |
| Account/Login (demo) | (seeded list → Customer) | Customer & Party: login by email |
| Shop Index (demo) | Product | Catalog (+ Inventory stock snapshot) |
| Shop Order / MyOrders (demo) | SalesOrderHeader, SalesOrderDetail, Product | Sales: order + lines for customer |
| Home/About/Contact/Privacy | – | – |

**Open issue:** the live demo writes LT rows, but the target DynamoDB tables are modelled on the full DB. See open questions in the PR.
