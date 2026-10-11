#!/usr/bin/env python3
"""Source of truth for the phase-2 access-pattern catalog.
Emits docs/design/access-patterns.json (machine-readable, feeds the mapping file) and docs/design/access-patterns.md.
Run: python3 scripts/design/access_patterns.py"""
import json, os, collections
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")

DOMAINS = collections.OrderedDict([
 ("Catalog", {"table": "aw-catalog", "owner": "Merchandising", "summary":
   "Everything a shopper browses: categories, products, models, descriptions, photos, reviews, price history and offers. "
   "Read-dominated (browse/detail pages) with rare admin writes; must serve the shopper pages with one request per page."}),
 ("Inventory & Manufacturing", {"table": "aw-inventory", "owner": "Operations", "summary":
   "Stock per location, inventory movements, bills of materials and work orders. Write-heavy back-office data; "
   "only 'is it in stock' reaches the shopper, as a pre-aggregated copy on the product."}),
 ("Sales", {"table": "aw-sales", "owner": "Sales", "summary":
   "Carts, checkout, orders and lines, and the sales organisation (sales people, quotas, territories). "
   "Hot path of the live demo: the order a test customer places flows SQL -> CDC -> DynamoDB here."}),
 ("Customer & Party", {"table": "aw-customer", "owner": "Customer service", "summary":
   "Identity and profile: persons, stores, logins, emails, phones, addresses, payment cards, store contacts. "
   "Serves login, checkout address/card selection and the customer screens."}),
 ("Purchasing", {"table": "aw-purchasing", "owner": "Procurement", "summary":
   "Vendors, which products they supply, and purchase orders. Low volume back-office workload."}),
 ("HR", {"table": "aw-hr", "owner": "HR", "summary":
   "Employees, departments, shifts, pay history, org chart, candidates. Small but sensitive; isolated table and IAM."}),
 ("Reference", {"table": "aw-reference", "owner": "Platform", "summary":
   "Shared lookups: countries, states, currencies and FX rates, tax rates, ship methods, units, cultures. "
   "Read-mostly, cached by apps and copied into other domains' items."}),
 ("Cross-cutting", {"table": "(all)", "owner": "Platform", "summary":
   "Patterns every domain must support for replication and analytics: idempotent CDC upserts/deletes and the zero-ETL feed to Redshift."}),
])

P = []
def ap(id, domain, question, actor, inputs, result, freq, rw="R", consistency="eventual", sort="", filter="",
       source=(), shopper=False, scope="dynamodb", hard=None, notes=""):
    P.append(dict(id=id, domain=domain, question=question, actor=actor, inputs=inputs, result=result,
                  frequency=freq, read_write=rw, consistency=consistency, sort=sort, filter=filter,
                  source=list(source), shopper_page=shopper, scope=scope, hard=hard, notes=notes, status="draft-for-review"))

# ---------------- Catalog ----------------
D = "Catalog"
ap("CAT-01", D, "What product categories (and their subcategories) can I shop?", "Shopper: browse nav; App: ProductCategories Index",
   "–", "4 categories, 37 subcategories with names", "every page view (cacheable); data changes ~never", sort="by name",
   source=["screen:ProductCategories/Index", "screen:Shop (nav)", "table:Production.ProductCategory", "table:Production.ProductSubcategory"], shopper=True)
ap("CAT-02", D, "Show / create / edit / delete a category or subcategory", "Admin: ProductCategories CRUD",
   "categoryId | subcategoryId", "one category/subcategory", "rare (<10/day)", rw="R/W", consistency="strong after write",
   source=["screen:ProductCategories/Details|Create|Edit|Delete"], notes="Delete must be refused while products reference it (was an FK).")
ap("CAT-03", D, "Which products are in this subcategory that I can buy now?", "Shopper: browse by category",
   "subcategoryId, page", "products (name, number, color, size, list price, thumbnail, in-stock flag), ~5–40 per subcategory",
   "high: most frequent shopper read (~10x orders)", sort="name or list price asc/desc", filter="sellable now (SellEndDate null / not discontinued); optional color/size",
   source=["screen:Shop/Index", "screen:Products/Index", "table:Production.Product"], shopper=True,
   notes="504 products total, 197 currently sellable with a no-discount offer. Price sort needs a second ordering.")
ap("CAT-04", D, "Show me everything about this product", "Shopper: product detail; App: Products Details",
   "productId (or product number)", "product + model + description (culture) + photos + active offers + review summary + stock flag",
   "high (~5x orders)", sort="reviews newest first", source=["screen:Products/Details", "view:Production.vProductAndDescription",
   "fn:dbo.ufnGetProductListPrice", "fn:dbo.ufnGetStock"], shopper=True,
   notes="Pre-join: model/description/photos/offers fetched with the product in one request; stock is a copied value from Inventory.")
ap("CAT-05", D, "Find a product by its product number (SKU)", "Back office, CDC, order entry", "productNumber",
   "product", "medium", source=["table:Production.Product (AK_Product_ProductNumber)"], notes="ProductNumber and Name are unique in SQL; uniqueness must be enforced on write.")
ap("CAT-06", D, "List all products (admin grid)", "Admin: Products Index", "page", "products with category + model name",
   "low", sort="name", source=["screen:Products/Index"], notes="504 items: paged full listing; fine as a scan of a small type or an index over all products.")
ap("CAT-07", D, "Create / update / retire a product", "Admin: Products CRUD", "product fields", "product written; name & number unique",
   "rare", rw="W", consistency="strong (conditional write for uniqueness)", source=["screen:Products/Create|Edit|Delete", "trigger:none"],
   notes="Price change must also append a list-price history record (CAT-09).")
ap("CAT-08", D, "What products belong to this model, and what is the model's catalog description/instructions?", "Shopper (variants: colors/sizes); Admin",
   "productModelId", "model + its products (variants)", "medium", sort="size/color", source=["view:Production.vProductModelCatalogDescription",
   "view:Production.vProductModelInstructions", "table:Production.ProductModel"], shopper=True)
ap("CAT-09", D, "What was this product's list price / standard cost on a given date?", "Order pricing audit; DW DimProduct SCD2",
   "productId, date", "price/cost effective on that date", "low online; bulk in analytics", sort="by start date",
   source=["fn:dbo.ufnGetProductListPrice", "fn:dbo.ufnGetProductStandardCost", "dw:DimProduct"], notes="395 list + 395 cost history rows.")
ap("CAT-10", D, "Which special offers apply to this product today?", "Shopper: product detail / cart pricing", "productId, date",
   "active offers (discount %, min/max qty)", "high (with CAT-04 / checkout)", filter="StartDate <= today <= EndDate",
   source=["table:Sales.SpecialOffer", "table:Sales.SpecialOfferProduct", "fn:dbo.ufnGetProductDealerPrice"], shopper=True)
ap("CAT-11", D, "Show / add reviews for a product", "Shopper", "productId", "reviews newest first", "low (4 reviews exist)",
   rw="R/W", sort="ReviewDate desc", source=["table:Production.ProductReview"], shopper=True)
ap("CAT-12", D, "Search products by free text (name, description, color)", "Shopper: search box", "text",
   "matching products ranked", "medium", source=["business"], shopper=True, scope="opensearch-or-defer",
   hard={"why": "ad hoc / free-text search; DynamoDB only supports key-prefix matching",
         "approach": "Demo: name-prefix via an index on normalized name (begins_with) or client-side filter over the 197 sellable products. Production: OpenSearch fed by DynamoDB Streams (zero-ETL OpenSearch integration)."})
ap("CAT-13", D, "Show the culture-specific description (en, fr, es, ...)", "Shopper (localized site)", "productModelId, culture",
   "description text", "low", source=["table:Production.ProductModelProductDescriptionCulture"], shopper=True)

# ---------------- Inventory ----------------
D = "Inventory & Manufacturing"
ap("INV-01", D, "How many units of this product are on hand, per location and in total?", "Back office; feeds Catalog stock flag",
   "productId", "qty per location (14 locations), total", "medium; on every inventory change for the copy", source=["fn:dbo.ufnGetStock", "table:Production.ProductInventory"],
   notes="1,069 rows. Total is pushed to Catalog (CAT-04/03) as a denormalized copy via Streams.")
ap("INV-02", D, "Which products are below their reorder point / safety stock?", "Planner (daily)", "–", "products needing reorder",
   "low (daily)", filter="total qty < ReorderPoint", source=["business", "table:Production.Product.ReorderPoint"],
   hard={"why": "filter across all products comparing two values", "approach": "Sparse 'needs reorder' marker maintained when stock changes (written by the same stream that updates totals); or Redshift report."})
ap("INV-03", D, "Record a stock movement and list movements for a product over a date range", "Warehouse, order fulfilment (trigger today), DW",
   "productId, date range", "transactions newest first", "~370/day writes (113k + 89k archive rows / ~16 months)", rw="R/W", sort="TransactionDate desc",
   source=["table:Production.TransactionHistory", "table:Production.TransactionHistoryArchive", "trigger:Sales.iduSalesOrderDetail", "dw:FactProductInventory"],
   notes="In SQL the order-detail trigger writes a TransactionHistory row per order line; in the target this becomes an event from Sales, not a cross-table write.")
ap("INV-04", D, "Explode the bill of materials for an assembly (all levels, as of a date)", "Engineering", "productAssemblyId, date",
   "component tree with quantities", "low", source=["proc:dbo.uspGetBillOfMaterials", "table:Production.BillOfMaterials"],
   hard={"why": "recursive (multi-level) traversal", "approach": "Store BOM edges per assembly; app iterates levels (max depth ~4, 2,679 edges) or keep a materialized flattened tree per top-level assembly, rebuilt on change."})
ap("INV-05", D, "Where is this component used?", "Engineering", "componentId, date", "assemblies using it (multi-level)", "low",
   source=["proc:dbo.uspGetWhereUsedProductID"], hard={"why": "reverse recursive traversal", "approach": "Inverted index on BOM edges (component -> assembly), iterate levels in app."})
ap("INV-06", D, "Which work orders are open / due, and what are a work order's routing steps?", "Production planner", "date range | workOrderId",
   "work orders by due date; one WO with routings", "~66 WOs/day (72,591 over 3 years)", rw="R/W", sort="DueDate", filter="not finished (EndDate null)",
   source=["table:Production.WorkOrder", "table:Production.WorkOrderRouting", "trigger:iWorkOrder/uWorkOrder"])
ap("INV-07", D, "Daily inventory balance per product (history)", "Analyst", "date range", "product x day quantities", "batch",
   source=["dw:FactProductInventory (776,286 rows)"], scope="redshift", hard={"why": "large aggregate over time", "approach": "Redshift: rebuild from zero-ETL'd transaction history (phase 6). No DynamoDB keys."})

# ---------------- Sales ----------------
D = "Sales"
ap("SAL-01", D, "Add / change / remove an item in my cart, and show my cart", "Shopper: cart", "cartId (= customer or anonymous session), productId, qty",
   "cart lines with current product name/price", "~10x orders", rw="R/W", consistency="strong (read-your-writes)", sort="date added",
   source=["table:Sales.ShoppingCartItem", "shopper:cart"], shopper=True, notes="Only 3 rows today; cart is short-lived (TTL). Product name/price read from Catalog at render time.")
ap("SAL-02", D, "Check out: turn my cart into an order (header + lines) with tax, freight, totals", "Shopper: checkout; demo Shop/Order",
   "customerId, cart, ship-to/bill-to address, ship method, card", "new order id/number", "~28/day historic (31,465 orders / 37 months); demo bursts",
   rw="W", consistency="strong; atomic (transaction)", source=["screen:Shop/Order (demo)", "trigger:Sales.iduSalesOrderDetail (SubTotal)", "table:Sales.SalesOrderHeader", "table:Sales.SalesOrderDetail"],
   shopper=True, notes="Needs product price/offer (CAT-10), tax rate (REF-02), ship method (REF-04), address/card snapshot (CUS-03). Header SubTotal maintained in the same transaction (replaces trigger). Max 72 lines/order today.")
ap("SAL-03", D, "Show my order history, newest first", "Shopper: My orders", "customerId, page", "orders (number, date, status, total, line summary)",
   "~3x orders", sort="OrderDate desc", source=["screen:Shop/MyOrders (demo)", "table:Sales.SalesOrderHeader"], shopper=True,
   notes="Max 28 orders per customer today; bounded.")
ap("SAL-04", D, "Show one order with its lines (and sales reasons)", "Shopper; customer service", "salesOrderId or SalesOrderNumber",
   "header + lines + reasons", "~3x orders", source=["table:Sales.SalesOrderDetail", "table:Sales.SalesOrderHeaderSalesReason"], shopper=True)
ap("SAL-05", D, "Which orders are in status X (e.g. in process / to ship) by date?", "Fulfilment", "status, date range",
   "orders", "low-medium", sort="OrderDate", filter="status", rw="R", source=["fn:dbo.ufnGetSalesOrderStatusText", "business"],
   notes="All 31,465 historical orders are status 5 (shipped) → only new orders are 'open'; sparse.")
ap("SAL-06", D, "Ship / cancel / revise an order", "Fulfilment; customer service", "salesOrderId", "order updated (status, ship date, revision)",
   "~orders", rw="W", consistency="strong; conditional on current status/revision", source=["trigger:Sales.uSalesOrderHeader (RevisionNumber/ModifiedDate)"])
ap("SAL-07", D, "Orders for a store / reseller over a date range", "Sales rep; store portal", "customerId (store) , date range",
   "orders", "low", sort="OrderDate desc", source=["dw:FactResellerSales", "table:Sales.SalesOrderHeader"])
ap("SAL-08", D, "Orders taken by a sales person over a date range", "Sales manager", "salesPersonId, date range", "orders", "low",
   sort="OrderDate desc", source=["business", "dw:FactResellerSales"])
ap("SAL-09", D, "Orders in a territory over a date range", "Sales manager", "territoryId, date range", "orders", "low",
   sort="OrderDate desc", source=["business"], notes="10 territories → coarse partitions; consider date-bucketed key in phase 3 or Redshift.")
ap("SAL-10", D, "Sales person profile with quota history and YTD/last-year sales", "Sales manager", "salesPersonId",
   "sales person, territory, quotas by quarter, YTD figures", "low", sort="QuotaDate", source=["view:Sales.vSalesPerson", "table:Sales.SalesPersonQuotaHistory"],
   notes="SalesYTD/SalesLastYear are stored aggregates in SQL → maintain as pre-aggregated counters on order write.")
ap("SAL-11", D, "Sales by sales person by fiscal year", "Sales manager", "–", "pivot of sales per person per FY", "low",
   source=["view:Sales.vSalesPersonSalesByFiscalYears"], scope="redshift",
   hard={"why": "large aggregate / pivot across all orders", "approach": "Redshift view over zero-ETL data (phase 6); not a DynamoDB key."})
ap("SAL-12", D, "Which sales people cover a territory (now and historically)?", "Sales manager", "territoryId", "sales people with start/end",
   "low", sort="StartDate", source=["table:Sales.SalesTerritoryHistory", "table:Sales.SalesTerritory"])
ap("SAL-13", D, "Find an order by purchase order number or card approval code", "Customer service", "PO number | approval code",
   "order", "low", source=["business"], notes="Candidate for a sparse lookup; or accept Redshift for rare lookups (decide in phase 3).")

# ---------------- Customer & Party ----------------
D = "Customer & Party"
ap("CUS-01", D, "Log me in with my email and password", "Shopper: login; demo Account/Login", "email, password",
   "customer id, display name, default address", "~orders x 2", consistency="strong", source=["screen:Account/Login (demo)", "table:Person.EmailAddress", "table:Person.Password"],
   shopper=True, notes="Email must be unique across persons (19,972 emails). Password hash/salt in SQL; demo uses a shared password.")
ap("CUS-02", D, "Show my profile: name, emails, phones, addresses, saved cards (masked)", "Shopper: account / checkout", "customerId",
   "profile with addresses & cards", "~orders x 2", source=["screen:Customers/Details", "view:Sales.vIndividualCustomer", "fn:dbo.ufnGetContactInformation"], shopper=True)
ap("CUS-03", D, "Which addresses / cards can I use at checkout?", "Shopper: checkout", "customerId", "addresses by type (billing/shipping/home), cards (type, last4, expiry)",
   "~orders", source=["table:Person.BusinessEntityAddress", "table:Sales.PersonCreditCard"], shopper=True)
ap("CUS-04", D, "Register / update / delete a customer (unique account number and email)", "Shopper sign-up; Admin Customers CRUD",
   "customer fields", "customer written", "low", rw="W", consistency="strong; conditional (uniqueness)", source=["screen:Customers/Create|Edit|Delete", "trigger:Person.iuPerson"])
ap("CUS-05", D, "List customers (admin grid), paged", "Admin: Customers Index", "page", "customers", "low", sort="name",
   source=["screen:Customers/Index"], notes="19,820 customers; paged scan of one type is acceptable for admin.")
ap("CUS-06", D, "Find a customer by account number", "Customer service; CDC; DW", "accountNumber (AW000xxxxx)", "customer", "medium",
   source=["dw:DimCustomer.CustomerAlternateKey", "table:Sales.Customer (AK_Customer_AccountNumber)"])
ap("CUS-07", D, "Show a store with its contacts, addresses and demographics", "Sales rep", "storeId", "store + contacts (role) + addresses + demographics",
   "low", source=["view:Sales.vStoreWithContacts", "view:Sales.vStoreWithAddresses", "view:Sales.vStoreWithDemographics"])
ap("CUS-08", D, "Show a person's demographics", "Marketing; DW", "personId", "income, education, occupation, cars, children, ...",
   "low", source=["view:Sales.vPersonDemographics", "dw:DimCustomer"], notes="Keep the XML as a map; DW needs it.")
ap("CUS-09", D, "Add / update my address, email, phone or card", "Shopper: account", "customerId, value", "updated profile", "low",
   rw="W", source=["shopper:account"], shopper=True, notes="Changing an address does not change past orders (orders carry a snapshot).")
ap("CUS-10", D, "Customers in a territory", "Sales manager", "territoryId", "customers", "low", source=["business"],
   notes="10 territories x ~2k customers; candidate for Redshift instead of an index.")
ap("CUS-11", D, "Contact info for any business entity (person, store, vendor contact, employee)", "Back office", "businessEntityId",
   "name, job title, type, phone, email", "low", source=["fn:dbo.ufnGetContactInformation", "view:Person.vAdditionalContactInfo"],
   hard={"why": "polymorphic lookup across domains (vendor contacts, employees, store contacts)", "approach": "Customer & Party owns all persons, so keep a person item keyed by businessEntityId; Purchasing/HR keep copies of what they display."})

# ---------------- Purchasing ----------------
D = "Purchasing"
ap("PUR-01", D, "Show a vendor with addresses and contacts", "Buyer", "vendorId", "vendor + addresses + contacts", "low",
   source=["view:Purchasing.vVendorWithAddresses", "view:Purchasing.vVendorWithContacts"])
ap("PUR-02", D, "Who can supply this product, at what price and lead time?", "Buyer", "productId", "vendors with std price, lead time, min/max qty",
   "low", source=["table:Purchasing.ProductVendor"])
ap("PUR-03", D, "What does this vendor supply?", "Buyer", "vendorId", "products", "low", source=["table:Purchasing.ProductVendor"],
   notes="Many-to-many with PUR-02 (460 edges).")
ap("PUR-04", D, "Create a purchase order and show it with its lines", "Buyer", "vendorId, lines | poId", "PO + lines",
   "~3 POs/day (4,012 / 41 months)", rw="R/W", consistency="strong (totals maintained in same transaction)", source=["trigger:iPurchaseOrderDetail/uPurchaseOrderDetail/uPurchaseOrderHeader"])
ap("PUR-05", D, "Purchase orders for a vendor, newest first, optionally by status", "Buyer", "vendorId, status?", "POs", "low",
   sort="OrderDate desc", filter="status", source=["fn:dbo.ufnGetPurchaseOrderStatusText"])
ap("PUR-06", D, "Purchase orders raised by an employee", "Purchasing manager", "employeeId", "POs", "low", sort="OrderDate desc", source=["business"])
ap("PUR-07", D, "Open purchase orders (pending/approved) to receive", "Warehouse", "status", "POs", "low", filter="status in (1,2)",
   source=["business"], notes="Sparse: few open POs.")

# ---------------- HR ----------------
D = "HR"
ap("HR-01", D, "Show an employee with current department, shift, job title and pay", "HR; manager", "employeeId", "employee profile",
   "low", consistency="strong for pay edits", source=["view:HumanResources.vEmployee", "view:HumanResources.vEmployeeDepartment"])
ap("HR-02", D, "Show an employee's department and pay history", "HR", "employeeId", "history newest first", "low", sort="StartDate/RateChangeDate desc",
   source=["view:HumanResources.vEmployeeDepartmentHistory", "table:HumanResources.EmployeePayHistory"])
ap("HR-03", D, "Who reports to this manager (all levels) / what is this employee's management chain?", "Manager; org chart", "employeeId",
   "subtree / chain", "low", source=["proc:dbo.uspGetManagerEmployees", "proc:dbo.uspGetEmployeeManagers", "column:Employee.OrganizationNode (hierarchyid)"],
   hard={"why": "recursive hierarchy (hierarchyid)", "approach": "Store the materialized org path (e.g. /1/4/3/) as a sort key → subtree = begins_with; chain = parse path. 290 employees, so client-side is also fine."})
ap("HR-04", D, "Who is currently in this department?", "Manager", "departmentId", "employees", "low", filter="EndDate null", source=["business"])
ap("HR-05", D, "Update hire info, login, personal info", "HR", "employeeId, fields", "employee updated", "rare", rw="W",
   consistency="strong", source=["proc:HumanResources.uspUpdateEmployeeHireInfo", "proc:HumanResources.uspUpdateEmployeeLogin", "proc:HumanResources.uspUpdateEmployeePersonalInfo"])
ap("HR-06", D, "List job candidates; search résumés by text", "Recruiter", "text", "candidates", "rare",
   source=["view:HumanResources.vJobCandidate*", "proc:dbo.uspSearchCandidateResumes"], scope="out-of-scope",
   hard={"why": "full-text search over XML résumés (13 rows)", "approach": "Out of scope for keys; if needed, OpenSearch or a client-side filter over 13 items."})

# ---------------- Reference ----------------
D = "Reference"
ap("REF-01", D, "List countries, and states/provinces for a country", "Shopper: address forms", "countryCode?", "countries (238) / states (181)",
   "every address form (cache)", sort="name", source=["view:Person.vStateProvinceCountryRegion"], shopper=True)
ap("REF-02", D, "What sales tax applies to a ship-to state?", "Checkout", "stateProvinceId", "tax rates (29 rows)", "~orders",
   source=["table:Sales.SalesTaxRate"], shopper=True)
ap("REF-03", D, "What was the exchange rate between two currencies on a date?", "Checkout (foreign currency); DW", "from, to, date",
   "average & end-of-day rate", "~orders (non-USD)", sort="date", source=["table:Sales.CurrencyRate (13,532)", "dw:FactCurrencyRate"])
ap("REF-04", D, "Which ship methods are available and what do they cost?", "Checkout", "–", "5 ship methods with base/rate", "~orders (cache)",
   source=["table:Purchasing.ShipMethod"], shopper=True)
ap("REF-05", D, "List currencies, units of measure, cultures", "Admin forms", "–", "small lists", "low (cache)",
   source=["table:Sales.Currency", "table:Production.UnitMeasure", "table:Production.Culture"])

# ---------------- Cross-cutting ----------------
D = "Cross-cutting"
ap("CDC-01", D, "Apply a source change (insert/update) to the target item(s), idempotently, keyed by the SQL primary key",
   "CDC Lambda (DMS→Kinesis) / Debezium consumer", "source table, source PK, after-image, LSN/commit ts", "target item(s) upserted",
   "every OLTP write (68 tables); demo bursts", rw="W", consistency="conditional on LSN (ignore older)",
   source=["cdc:all 68 tables"], notes="Requires every target item to be addressable from its source PK (deterministic key) and to carry the last-applied LSN.")
ap("CDC-02", D, "Apply a source delete", "CDC consumer", "source table, PK, LSN", "target item(s) deleted or tombstoned", "low", rw="W",
   consistency="conditional on LSN", source=["cdc:all 68 tables"], notes="e.g. reset-demo deletes demo orders → must remove them from aw-sales.")
ap("CDC-03", D, "Fan out a source change to denormalized copies in other items/domains", "CDC consumer / stream processor",
   "changed entity", "copies refreshed (e.g. product name on catalog listings, person name on employee)", "low-medium", rw="W",
   source=["docs/discovery/domains.md (break/duplicate table)"],
   hard={"why": "cross-domain joins replaced by copies", "approach": "Event-driven refresh via DynamoDB Streams/EventBridge; immutable snapshots (order lines, order addresses) are never refreshed."})
ap("CDC-04", D, "Child row arrives before its parent (e.g. order line before header)", "CDC consumer", "child change", "item written without waiting for parent",
   "per transaction", rw="W", source=["cdc ordering"], notes="Design keys so a child can be written using only its own source columns (no lookup of the parent required).")
ap("DW-01", D, "Land all domain data in Redshift continuously", "DynamoDB zero-ETL → Redshift", "–", "SUPER rows per item",
   "continuous", source=["dw:all facts/dims"], scope="redshift",
   notes="Needs entityType + plain-named business attributes on every item (not only inside PK/SK).")
ap("DW-02", D, "Rebuild FactInternetSales / FactResellerSales / FactInternetSalesReason / FactSalesQuota", "Redshift SQL (phase 6)",
   "order + line items, offers, cost at order date", "fact rows", "batch / materialized views", scope="redshift",
   source=["dw:FactInternetSales", "dw:FactResellerSales", "dw:FactInternetSalesReason", "dw:FactSalesQuota"],
   notes="Order/line items must keep: OnlineOrderFlag, CustomerID, StoreID, SalesPersonID, TerritoryID, CurrencyRateID, SpecialOfferID, product standard cost at order date, dates.")
ap("DW-03", D, "Rebuild DimCustomer / DimReseller / DimGeography / DimProduct (SCD2) / DimEmployee / DimPromotion / DimCurrency / DimSalesTerritory", "Redshift SQL",
   "domain items", "dimension rows", "batch", scope="redshift", source=["dw:Dim*"],
   notes="Keep demographics maps, price/cost history and employee history items so dimensions can be derived.")
ap("DW-04", D, "Any aggregate report (sales by period/territory/category, top products, inventory balance)", "Analyst / QuickSight",
   "any", "aggregates", "ad hoc", scope="redshift", source=["dw:views", "view:Sales.vSalesPersonSalesByFiscalYears"],
   hard={"why": "large aggregates / ad hoc analytics", "approach": "Redshift + QuickSight only; no GSIs for reporting."})

def esc(x):
    return str(x).replace("|", "\\|")

def main():
    ids = [p["id"] for p in P]; assert len(ids) == len(set(ids)), "duplicate ids"
    counts = collections.Counter(p["domain"] for p in P)
    doc = {"version": 1, "phase": 2, "status": "draft-for-review",
           "legend": {"read_write": "R | W | R/W", "consistency": "eventual | strong | conditional", "scope": "dynamodb = must be served by domain table keys (phase 3); redshift = served by zero-ETL/Redshift, no keys; opensearch-or-defer; out-of-scope",
                      "frequency": "estimated from AdventureWorks2022 row counts (orders 2011-05-31..2014-06-30 = 31,465 orders ≈ 28/day; 27,659 online) plus demo bursts"},
           "domains": [{"name": n, **d, "pattern_count": counts[n]} for n, d in DOMAINS.items()],
           "patterns": P}
    json.dump(doc, open(os.path.join(ROOT, "docs/design/access-patterns.json"), "w"), indent=1, ensure_ascii=False)
    L = ["# Access-pattern catalog (phase 2)\n",
         "Generated from `scripts/design/access_patterns.py` (source of truth) together with [`access-patterns.json`](access-patterns.json). "
         "Status: **draft for John's review** — no key design here (phase 3).\n",
         "Frequency estimates come from AdventureWorks2022 row counts: 31,465 orders over 37 months (2011-05-31 → 2014-06-30) ≈ 28 orders/day "
         "(27,659 online), 121,317 lines (max 72/order), max 28 orders per customer, 19,820 customers, 504 products (197 sellable with the no-discount offer), "
         "4,012 POs, 72,591 work orders. Shopper read multipliers (×10 browse, ×5 detail, ×3 history per order) are assumptions to confirm.\n",
         "Scope: **dynamodb** = must be served by the domain table's keys/indexes in phase 3 · **redshift** = served via zero-ETL, no keys · "
         "**opensearch-or-defer** / **out-of-scope** as marked.\n",
         "## Counts\n", "| Domain | Table | Patterns | DynamoDB | Redshift | Other | Shopper | Hard |", "|---|---|---|---|---|---|---|---|"]
    for n, d in DOMAINS.items():
        ps = [p for p in P if p["domain"] == n]
        L.append("| %s | `%s` | %d | %d | %d | %d | %d | %d |" % (n, d["table"], len(ps), sum(p["scope"] == "dynamodb" for p in ps),
                 sum(p["scope"] == "redshift" for p in ps), sum(p["scope"] not in ("dynamodb", "redshift") for p in ps),
                 sum(p["shopper_page"] for p in ps), sum(bool(p["hard"]) for p in ps)))
    L.append("| **Total** | | **%d** | %d | %d | %d | %d | %d |\n" % (len(P), sum(p["scope"] == "dynamodb" for p in P), sum(p["scope"] == "redshift" for p in P),
             sum(p["scope"] not in ("dynamodb", "redshift") for p in P), sum(p["shopper_page"] for p in P), sum(bool(p["hard"]) for p in P)))
    L += ["## Shopper journey coverage\n", "| Page | Patterns |", "|---|---|",
          "| Browse by category | CAT-01, CAT-03, (CAT-12 search) |", "| Product detail | CAT-04, CAT-08, CAT-10, CAT-11, CAT-13, INV-01 (copied stock) |",
          "| Cart | SAL-01 (+ CAT-10 pricing) |", "| Login / account | CUS-01, CUS-02, CUS-09 |",
          "| Checkout | CUS-03, REF-01, REF-02, REF-04, CAT-10, SAL-02 |", "| Order history | SAL-03, SAL-04 |", ""]
    L += ["## Hard for single-table design → proposed approach\n", "| ID | Pattern | Why hard | Proposed approach |", "|---|---|---|---|"]
    for p in P:
        if p["hard"]:
            L.append("| %s | %s | %s | %s |" % tuple(esc(x) for x in (p["id"], p["question"], p["hard"]["why"], p["hard"]["approach"])))
    L.append("")
    for n, d in DOMAINS.items():
        ps = [p for p in P if p["domain"] == n]
        L += ["## %s — `%s`\n" % (n, d["table"]), "**One-page summary.** %s Owner: %s. %d patterns (%d shopper-facing, %d served from Redshift).\n" % (
              d["summary"], d["owner"], len(ps), sum(p["shopper_page"] for p in ps), sum(p["scope"] == "redshift" for p in ps)),
              "| ID | Question (business words) | Actor / screen | Inputs | Expected result | Frequency / volume | R/W | Consistency | Sort / filter | Scope | Source |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        for p in ps:
            sf = "; ".join(x for x in (("sort: " + p["sort"]) if p["sort"] else "", ("filter: " + p["filter"]) if p["filter"] else "") if x)
            q = p["question"] + (" ⚠" if p["hard"] else "") + (" 🛒" if p["shopper_page"] else "")
            L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % tuple(esc(x) for x in (p["id"], q, p["actor"], p["inputs"], p["result"], p["frequency"],
                     p["read_write"], p["consistency"], sf or "–", p["scope"], "<br>".join(p["source"]))))
        notes = [p for p in ps if p["notes"]]
        if notes:
            L.append("\nNotes: " + " ".join("**%s** %s" % (p["id"], p["notes"]) for p in notes))
        L.append("")
    L += ["## Questions for sign-off\n",
          "1. **Shopper multipliers**: OK to size reads at ×10 browse / ×5 product detail / ×3 order-history per order, and demo peak ≈ 1 order/s?",
          "2. **Search (CAT-12)**: demo with name-prefix/client-side filter, or include OpenSearch (zero-ETL) in scope?",
          "3. **Cart (SAL-01)**: carts for logged-in customers only, or anonymous session carts too? TTL (e.g. 7 days)?",
          "4. **Checkout (SAL-02)**: during the live demo SQL stays system of record and DynamoDB is fed only by CDC — so the .NET 10 app (phase 5) writes orders to SQL, or directly to DynamoDB (then CDC direction / dual-write)?",
          "5. **Order ids**: keep SQL SalesOrderID / SalesOrderNumber as the key for orders created in SQL; what id do orders created natively in DynamoDB get?",
          "6. **Back-office patterns**: keep in phase-3 key design or mark out-of-scope for the demo? (Inventory INV-02..06, Purchasing PUR-*, HR-*, SAL-05..13, CUS-07/10/11)",
          "7. **Territory / sales-person lists (SAL-08/09, CUS-10)**: DynamoDB index or Redshift only?",
          "8. **Consistency**: strong reads required only for login, cart and read-after-checkout — agree?",
          "9. **Localisation (CAT-13)**: English-only for the demo, or keep all 6 cultures' descriptions?",
          "10. **Soft vs hard delete** for CDC-02 (e.g. reset-demo deletes): physically delete DynamoDB items, or tombstone so Redshift sees the delete?",
          ""]
    L.append("Legend: ⚠ hard for single-table design (see table above) · 🛒 needed by the shopper pages.\n")
    out = L
    open(os.path.join(ROOT, "docs/design/access-patterns.md"), "w").write("\n".join(out) + "\n")
    print(dict(counts), len(P))
main()
