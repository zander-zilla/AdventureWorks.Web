"""Authored source for docs/business-processes (Chapter 2 research).

render.py turns this + docs/business-processes/evidence.json into business-processes.json and the markdown files.
Every step/claim carries basis: "evidenced" (row counts / status distributions / FKs / triggers in the live DB) or
"inferred" (what a real business would do that the data implies but does not prove).
"""

SOH_STATUS = {1: "In process", 2: "Approved", 3: "Backordered", 4: "Rejected", 5: "Shipped", 6: "Cancelled"}
POH_STATUS = {1: "Pending", 2: "Approved", 3: "Rejected", 4: "Complete"}

PROCESSES = [
# ---------------------------------------------------------------------------------------------------------------
{
 "id": "o2c-internet", "name": "Order-to-cash: internet (B2C)", "domain": "Sales",
 "summary": "An individual customer browses, fills a cart, checks out with a credit card; the order is approved, picked from finished-goods stock, shipped by truck ground and settled on the card.",
 "actors": ["Shopper (Person.PersonType = IN)", "Web storefront", "Fulfilment / warehouse", "Payment processor (card approval code)"],
 "trigger": "Shopper places an order on the web site (OnlineOrderFlag = 1).",
 "steps": [
  {"name": "Browse catalog", "actor": "Shopper", "reads": ["Production.ProductCategory", "Production.ProductSubcategory", "Production.Product", "Production.ProductModelProductDescriptionCulture", "Sales.SpecialOfferProduct"], "writes": [], "basis": "evidenced", "note": "Only sellable products (SellEndDate null)."},
  {"name": "Add to cart", "actor": "Shopper", "reads": ["Sales.ShoppingCartItem"], "writes": ["Sales.ShoppingCartItem"], "basis": "evidenced", "note": "Cart table exists but holds only 3 rows: carts are transient."},
  {"name": "Check out (address, card, ship method)", "actor": "Shopper", "reads": ["Person.BusinessEntityAddress", "Person.Address", "Sales.PersonCreditCard", "Sales.CreditCard", "Purchasing.ShipMethod", "Sales.SalesTaxRate", "Sales.CurrencyRate"], "writes": ["Sales.SalesOrderHeader", "Sales.SalesOrderDetail", "Sales.SalesOrderHeaderSalesReason"], "basis": "evidenced", "note": "Every internet order uses XRQ - TRUCK GROUND; DueDate = OrderDate + 12 days; ~46% carry a currency rate (foreign-currency web shop)."},
  {"name": "Ask why the shopper bought (sales reasons)", "actor": "Shopper", "reads": ["Sales.SalesReason"], "writes": ["Sales.SalesOrderHeaderSalesReason"], "basis": "evidenced", "note": "Survey-style reasons (Price dominates). AdventureWorksDW models them as internet-only (FactInternetSalesReason)."},
  {"name": "Authorise card", "actor": "Payment processor", "reads": [], "writes": ["Sales.SalesOrderHeader.CreditCardApprovalCode"], "basis": "inferred", "note": "Approval code column exists; there is no payment / settlement table, so capture and settlement are outside the DB."},
  {"name": "Approve and pick", "actor": "Fulfilment", "reads": ["Production.ProductInventory"], "writes": ["Sales.SalesOrderHeader.Status (1→2)", "Production.TransactionHistory (type S)"], "basis": "evidenced", "note": "Trigger iduSalesOrderDetail writes one TransactionHistory row of type S per order line: S rows (current+archive) = order lines exactly. It does NOT decrement ProductInventory."},
  {"name": "Ship", "actor": "Fulfilment", "reads": [], "writes": ["Sales.SalesOrderHeader.ShipDate", "Sales.SalesOrderHeader.Status (→5)"], "basis": "evidenced", "note": "Every historical order is Shipped; ShipDate = OrderDate + 7 days for all internet orders; no carrier tracking on internet lines."},
  {"name": "Invoice / collect", "actor": "Finance", "reads": ["Sales.SalesOrderHeader (SubTotal, TaxAmt, Freight, TotalDue)"], "writes": [], "basis": "inferred", "note": "TotalDue is a computed column; there is no invoice, payment or AR table. Cash side lives only in DW FactFinance (static)."},
 ],
 "state_entity": "Sales.SalesOrderHeader.Status", "state_values": SOH_STATUS,
 "state_diagram": """stateDiagram-v2
    [*] --> InProcess: checkout (status 1)
    InProcess --> Approved: card authorised / credit ok (2)
    InProcess --> Rejected: card declined (4)
    InProcess --> Cancelled: shopper cancels (6)
    Approved --> Backordered: no stock (3)
    Backordered --> Approved: stock arrives
    Approved --> Shipped: ShipDate set (5)
    Shipped --> [*]
    Rejected --> [*]
    Cancelled --> [*]
    note right of Shipped: evidenced - all 27,659 internet orders are status 5\\nother states come from ufnGetSalesOrderStatusText (inferred transitions)""",
 "flowchart": """flowchart LR
  subgraph Shopper
    A([Browse catalog]) --> B[Add to cart] --> C[Checkout: address, card, ship method]
    C --> R[Pick sales reasons]
  end
  subgraph Storefront
    C --> D[(SalesOrderHeader + Details\\nstatus 1)]
    D --> E{Card approved?}
  end
  subgraph Fulfilment
    E -- yes --> F[Approve, status 2] --> G{In stock?}
    G -- no --> H[Backorder, status 3] --> G
    G -- yes --> I[Pick: TransactionHistory S] --> J[Ship: ShipDate, status 5]
  end
  E -- no --> K[Reject, status 4]
  J --> L([Invoice / settle - outside DB])""",
 "evidence": [
  {"metric": "soh.status_by_channel", "keys": ["internet:5"], "note": "every internet order is Shipped: the DB holds only completed history"},
  {"metric": "soh.ship_minus_order_days", "keys": ["internet:7"], "note": "constant 7-day ship lag (synthetic)"},
  {"metric": "soh.due_minus_order_days", "keys": ["internet:12"]},
  {"metric": "soh.with_creditcard", "keys": ["internet"], "note": "of 27,659; the rest have no card on file"},
  {"metric": "soh.with_currencyrate", "keys": ["internet"]},
  {"metric": "soh.shipmethod", "keys": ["internet:XRQ - TRUCK GROUND"]},
  {"metric": "sales_reason.orders"},
  {"metric": "sod.discounted_lines", "keys": ["internet"], "note": "internet lines are never discounted"},
  {"metric": "th.type", "keys": ["current:S", "archive:S"], "note": "S rows = 121,317 = SalesOrderDetail rows: one stock-out transaction per order line"},
  {"metric": "cart.items"},
 ],
 "coverage": {
  "access_patterns": ["CAT-01", "CAT-03", "CAT-04", "SAL-01", "SAL-02", "SAL-03", "SAL-04", "SAL-05", "SAL-06", "SAL-13", "CUS-01", "CUS-03", "REF-02", "REF-04"],
  "app_pages": ["Shop: browse", "Product detail", "Search", "Cart", "Checkout", "My orders / order"],
  "redshift": ["dw.fact_internet_sales", "dw.fact_internet_sales_reason", "dw.v_sales (QuickSight)"],
 },
 "gaps": [
  "No back-office order screen: orders stay at status 1 forever; SAL-05 (orders by status) and SAL-06 (ship/cancel/revise) are designed but no page uses them.",
  "Checkout uses flat demo tax (8%) and freight (2.5%) instead of Sales.SalesTaxRate (REF-02) and ShipMethod rates (REF-04).",
  "No special-offer pricing at checkout (CAT-10 designed, unused).",
  "Sales reasons are not captured at checkout (SalesOrderHeaderSalesReason only arrives via CDC for SQL orders).",
  "No stock check / stock movement on order: SQL wrote TransactionHistory type S per line; DynamoDB checkout writes nothing to aw-inventory (INV-03 unused).",
  "No multi-currency: CurrencyRate (REF-03) is loaded but the shop prices in USD only.",
  "Payment, invoice and cash receipt have no OLTP tables at all (gap in the source schema, not just the app).",
 ],
},
# ---------------------------------------------------------------------------------------------------------------
{
 "id": "o2c-reseller", "name": "Order-to-cash: reseller (B2B)", "domain": "Sales",
 "summary": "A sales person takes an order from a reseller store against the store's purchase order number; volume discounts apply; the order ships by cargo with carrier tracking per line and counts toward the sales person's quota.",
 "actors": ["Sales person (Person.PersonType = SP)", "Store contact / purchasing agent (SC)", "Sales manager", "Fulfilment / shipping"],
 "trigger": "Reseller sends a purchase order to its assigned sales person (OnlineOrderFlag = 0, PurchaseOrderNumber set).",
 "steps": [
  {"name": "Receive reseller PO", "actor": "Sales person", "reads": ["Sales.Store", "Person.BusinessEntityContact", "Person.ContactType"], "writes": [], "basis": "inferred", "note": "Contacts typed Purchasing Agent / Purchasing Manager (487 of 909) are the store's buyers."},
  {"name": "Enter order with PO number", "actor": "Sales person", "reads": ["Sales.Customer (StoreID)", "Sales.SalesPerson", "Sales.SalesTerritory", "Person.Address (Main Office / Shipping)"], "writes": ["Sales.SalesOrderHeader (SalesPersonID, TerritoryID, PurchaseOrderNumber)", "Sales.SalesOrderDetail"], "basis": "evidenced", "note": "All 3,806 reseller orders have a sales person and a PO number; 0 internet orders do."},
  {"name": "Apply volume / reseller promotions", "actor": "Sales person", "reads": ["Sales.SpecialOffer", "Sales.SpecialOfferProduct"], "writes": ["Sales.SalesOrderDetail (SpecialOfferID, UnitPriceDiscount)"], "basis": "evidenced", "note": "3,282 discounted reseller lines; Volume Discount 11-14 alone is on 3,428 lines."},
  {"name": "Credit approval (card or terms)", "actor": "Sales manager", "reads": ["Sales.CreditCard"], "writes": ["Sales.SalesOrderHeader.Status (1→2 or 4)"], "basis": "inferred", "note": "3,799 of 3,806 reseller orders carry a card id; terms/credit limit do not exist in the schema."},
  {"name": "Pick and ship with tracking", "actor": "Fulfilment", "reads": ["Production.ProductInventory"], "writes": ["Production.TransactionHistory (S)", "Sales.SalesOrderDetail.CarrierTrackingNumber", "Sales.SalesOrderHeader (ShipDate, Status 5)"], "basis": "evidenced", "note": "Every reseller line has a carrier tracking number; all ship by CARGO TRANSPORT 5."},
  {"name": "Revise order", "actor": "Sales person", "reads": [], "writes": ["Sales.SalesOrderHeader.RevisionNumber"], "basis": "evidenced", "note": "Trigger uSalesOrderHeader bumps RevisionNumber; 30 orders are at revision 9 (one extra revision) vs 8 for the rest."},
  {"name": "Credit sales person / territory YTD", "actor": "System", "reads": [], "writes": ["Sales.SalesPerson (SalesYTD)", "Sales.SalesTerritory (SalesYTD)"], "basis": "inferred", "note": "Stored YTD aggregates exist; nothing in the DB maintains them (probably a batch)."},
 ],
 "state_entity": "Sales.SalesOrderHeader.Status", "state_values": SOH_STATUS,
 "state_diagram": """stateDiagram-v2
    [*] --> InProcess: order keyed by sales person (1)
    InProcess --> Approved: credit ok (2)
    InProcess --> Rejected: credit refused (4)
    Approved --> Backordered: short stock (3)
    Backordered --> Approved
    Approved --> Shipped: tracking number + ShipDate (5)
    InProcess --> Cancelled: reseller cancels (6)
    Approved --> Approved: revision (RevisionNumber+1)
    Shipped --> [*]
    note right of Shipped: evidenced - all 3,806 reseller orders are status 5""",
 "flowchart": """flowchart LR
  subgraph Reseller
    P([Store purchasing agent sends PO])
  end
  subgraph Sales
    P --> Q[Sales person keys order\\nPO number, territory]
    Q --> O[Apply volume / reseller offers]
    O --> M{Credit approval}
  end
  subgraph Fulfilment
    M -- ok --> S[Pick: TransactionHistory S]
    S --> T[Ship: CARGO TRANSPORT 5\\ntracking per line, status 5]
  end
  M -- no --> X[Rejected, status 4]
  T --> Y[Quota attainment / SalesYTD]""",
 "evidence": [
  {"metric": "soh.status_by_channel", "keys": ["reseller:5"]},
  {"metric": "soh.with_salesperson"}, {"metric": "soh.with_purchaseorder"},
  {"metric": "sod.with_tracking"}, {"metric": "sod.discounted_lines", "keys": ["reseller"]},
  {"metric": "sod.lines_by_offer"}, {"metric": "soh.revision"},
  {"metric": "soh.shipmethod", "keys": ["reseller:CARGO TRANSPORT 5"]},
  {"metric": "store.with_orders", "note": "of 701 stores"},
  {"metric": "contact.type"},
 ],
 "coverage": {
  "access_patterns": ["SAL-04", "SAL-05", "SAL-06", "SAL-07", "SAL-08", "SAL-09", "SAL-10", "SAL-13", "CUS-07", "CAT-10"],
  "app_pages": ["My orders shows SQL reseller orders only if a demo customer is a store contact (none are)"],
  "redshift": ["dw.fact_reseller_sales", "dw.dim_reseller", "dw.dim_employee", "dw.dim_promotion", "dw.v_sales"],
 },
 "gaps": [
  "No sales-person workspace: no screen to key a reseller order, look up a store (CUS-07), or find an order by PO number (SAL-13).",
  "Volume-discount pricing (SpecialOfferProduct with Min/MaxQty) is not implemented anywhere in the app.",
  "No order revision / ship-with-tracking workflow (SAL-06).",
  "SalesYTD on SalesPerson/SalesTerritory is a stale copy; the design (SAL-10) says maintain counters on order write; not built.",
 ],
},
# ---------------------------------------------------------------------------------------------------------------
{
 "id": "procure-to-pay", "name": "Procure-to-pay", "domain": "Purchasing",
 "summary": "A buyer raises a purchase order to an approved vendor for a purchased component; the PO is approved, goods are received (with quality rejects) into stock, and the vendor is paid.",
 "actors": ["Buyer (12 distinct employees: Buyer, Purchasing Assistant, Purchasing Manager)", "Purchasing manager (approver)", "Vendor", "Receiving / inspection", "Accounts payable"],
 "trigger": "Stock of a purchased product (MakeFlag = 0) falls below ReorderPoint, or a work order needs components (inferred).",
 "steps": [
  {"name": "Detect need (below reorder point)", "actor": "Buyer", "reads": ["Production.Product (ReorderPoint, SafetyStockLevel)", "Production.ProductInventory"], "writes": [], "basis": "inferred", "note": "60 sellable products are below reorder point today; nothing in the DB links a PO to that signal."},
  {"name": "Choose vendor", "actor": "Buyer", "reads": ["Purchasing.ProductVendor (AverageLeadTime, StandardPrice, Min/MaxOrderQty, OnOrderQty)", "Purchasing.Vendor (CreditRating, PreferredVendorStatus, ActiveFlag)"], "writes": [], "basis": "evidenced", "note": "460 product-vendor offers for 265 products; 93 of 104 vendors preferred."},
  {"name": "Raise PO", "actor": "Buyer", "reads": ["Purchasing.ShipMethod"], "writes": ["Purchasing.PurchaseOrderHeader (Status 1, EmployeeID)", "Purchasing.PurchaseOrderDetail"], "basis": "evidenced", "note": "Trigger iPurchaseOrderDetail recalculates SubTotal and writes TransactionHistory type P."},
  {"name": "Approve / reject", "actor": "Purchasing manager", "reads": [], "writes": ["Purchasing.PurchaseOrderHeader.Status (2 or 3)", "RevisionNumber"], "basis": "evidenced", "note": "uPurchaseOrderHeader bumps RevisionNumber; revisions 4..20 show repeated edits."},
  {"name": "Vendor ships", "actor": "Vendor", "reads": [], "writes": ["Purchasing.PurchaseOrderHeader.ShipDate"], "basis": "evidenced", "note": "ShipDate = OrderDate + 9 days on 4,000 of 4,012 POs."},
  {"name": "Receive and inspect", "actor": "Receiving", "reads": ["Purchasing.PurchaseOrderDetail"], "writes": ["PurchaseOrderDetail (ReceivedQty, RejectedQty → StockedQty computed)", "Production.TransactionHistory (P)"], "basis": "evidenced", "note": "380 lines partially received; 563 lines with rejects; 72,700 units rejected of 2.33M received."},
  {"name": "Put away", "actor": "Receiving", "reads": [], "writes": ["Production.ProductInventory"], "basis": "inferred", "note": "No trigger moves stock into ProductInventory on receipt."},
  {"name": "Close PO / pay vendor", "actor": "Accounts payable", "reads": ["PurchaseOrderHeader (TotalDue)"], "writes": ["Status 4 Complete"], "basis": "inferred", "note": "No invoice, 3-way-match or payment table."},
 ],
 "state_entity": "Purchasing.PurchaseOrderHeader.Status", "state_values": POH_STATUS,
 "state_diagram": """stateDiagram-v2
    [*] --> Pending: PO raised (1)
    Pending --> Approved: manager approves (2)
    Pending --> Rejected: manager rejects (3)
    Pending --> Pending: edit (RevisionNumber+1)
    Approved --> Complete: all lines received (4)
    Approved --> Approved: partial receipt
    Complete --> [*]
    Rejected --> [*]
    note right of Pending: evidenced distribution 225 / 12 / 86 / 3,689\\nreceipt quantities do not respect status (synthetic data)""",
 "flowchart": """flowchart LR
  subgraph Buyer
    A([Stock below reorder point]) --> B[Pick vendor: ProductVendor\\nlead time, price, preferred]
    B --> C[Raise PO, status 1]
  end
  subgraph Manager
    C --> D{Approve?}
  end
  D -- no --> R[Rejected, status 3]
  D -- yes --> E[Approved, status 2]
  subgraph Vendor
    E --> F[Ship: ShipDate = +9d]
  end
  subgraph Receiving
    F --> G[Receive: ReceivedQty]
    G --> H{Inspection}
    H -- reject --> I[RejectedQty]
    H -- accept --> J[StockedQty → TransactionHistory P\\nput away to ProductInventory]
  end
  J --> K{All received?}
  K -- no --> G
  K -- yes --> L[Complete, status 4] --> M([AP pays - outside DB])""",
 "evidence": [
  {"metric": "poh.status"}, {"metric": "poh.revision"}, {"metric": "poh.ship_minus_order_days"},
  {"metric": "poh.buyers"}, {"metric": "poh.buyer_titles"},
  {"metric": "pod.receipt"}, {"metric": "pod.receipt_by_status", "note": "pending/rejected POs show receipts: status is not consistent with receipts, so the transitions are inferred"},
  {"metric": "pod.rejected_lines"}, {"metric": "pod.qty"},
  {"metric": "th.type", "keys": ["current:P", "archive:P"], "note": "8,788 P transactions vs 8,845 PO lines"},
  {"metric": "vendor.flags"}, {"metric": "vendor.credit_rating"}, {"metric": "vendor.with_pos"},
  {"metric": "productvendor.products"}, {"metric": "inv.below_reorder"},
 ],
 "coverage": {
  "access_patterns": ["PUR-01", "PUR-02", "PUR-03", "PUR-04", "PUR-05", "PUR-06", "PUR-07", "INV-02"],
  "app_pages": [],
  "redshift": ["landed in Redshift via zero-ETL but no purchasing fact or report (AdventureWorksDW has none)"],
 },
 "gaps": [
  "Entire process has no UI: all 7 PUR patterns are designed and load-tested but unused by the app.",
  "No approval workflow, receiving or inspection screen; StockedQty never reaches ProductInventory in either system.",
  "No purchasing analytics (spend by vendor, vendor on-time / reject rate) in Redshift.",
  "No reorder suggestion linking INV-02 (below reorder point) to PUR-02 (who can supply).",
 ],
},
# ---------------------------------------------------------------------------------------------------------------
{
 "id": "plan-to-produce", "name": "Plan-to-produce (work orders, BOM, routing, scrap)", "domain": "Production",
 "summary": "Production planning releases a work order for a manufactured product; it is routed through up to 7 work centres (frame forming → final assembly), consumes components per the bill of materials, and stocks finished units with some scrap.",
 "actors": ["Production planner (Production Control)", "Work-centre supervisors / technicians (Manufacturing, 185 current staff)", "Quality assurance"],
 "trigger": "Demand or stock for a MakeFlag = 1 product (inferred: no link from sales orders to work orders).",
 "steps": [
  {"name": "Explode bill of materials", "actor": "Planner", "reads": ["Production.BillOfMaterials", "Production.Product", "Production.UnitMeasure"], "writes": [], "basis": "evidenced", "note": "238 assemblies, up to 5 levels (BOMLevel 0-4); 199 BOM edges end-dated (engineering changes). uspGetBillOfMaterials / uspGetWhereUsedProductID."},
  {"name": "Release work order", "actor": "Planner", "reads": ["Production.Product"], "writes": ["Production.WorkOrder (OrderQty, StartDate, DueDate)", "Production.TransactionHistory (W)"], "basis": "evidenced", "note": "Trigger iWorkOrder writes a type-W transaction: W rows (current+archive) = 72,591 = work orders exactly."},
  {"name": "Schedule routing operations", "actor": "Planner", "reads": ["Production.Location (CostRate, Availability)"], "writes": ["Production.WorkOrderRouting (ScheduledStart/End, PlannedCost)"], "basis": "evidenced", "note": "42,625 work orders are routed; OperationSequence 1-7 maps to the 7 work-centre locations."},
  {"name": "Execute operations", "actor": "Supervisor", "reads": [], "writes": ["WorkOrderRouting (ActualStart/End, ActualResourceHrs, ActualCost)"], "basis": "evidenced", "note": "39,212 operations finished after ScheduledEndDate; ActualCost = PlannedCost in total (synthetic)."},
  {"name": "Issue components", "actor": "Supervisor", "reads": ["Production.ProductInventory"], "writes": ["Production.ProductInventory"], "basis": "inferred", "note": "No component-issue transaction type exists; consumption is not recorded."},
  {"name": "Record scrap", "actor": "QA", "reads": ["Production.ScrapReason"], "writes": ["WorkOrder (ScrappedQty, ScrapReasonID)"], "basis": "evidenced", "note": "729 work orders with scrap, 10,651 units, 16 reasons fairly evenly used."},
  {"name": "Complete and stock", "actor": "Supervisor", "reads": [], "writes": ["WorkOrder (EndDate, StockedQty computed)", "Production.ProductInventory (Finished Goods Storage)", "TransactionHistory (W via uWorkOrder)"], "basis": "evidenced", "note": "All 72,591 work orders are closed; 22,790 closed after DueDate."},
 ],
 "state_entity": "Production.WorkOrder (derived from StartDate / EndDate / DueDate; no status column)", "state_values": {"open": "EndDate null", "closed_on_time": "EndDate <= DueDate", "closed_late": "EndDate > DueDate", "with_scrap": "ScrappedQty > 0"},
 "state_diagram": """stateDiagram-v2
    [*] --> Released: WorkOrder insert (+TransactionHistory W)
    Released --> InOperation: routing op 1 ActualStartDate
    InOperation --> InOperation: next OperationSequence
    InOperation --> Scrapped: ScrappedQty / ScrapReasonID
    Scrapped --> InOperation
    InOperation --> ClosedOnTime: EndDate <= DueDate
    InOperation --> ClosedLate: EndDate > DueDate
    ClosedOnTime --> [*]
    ClosedLate --> [*]
    note right of Released: derived states - no Status column; 0 open today""",
 "flowchart": """flowchart LR
  subgraph Planning
    A([Demand for make product]) --> B[Explode BOM\\nmulti-level, as-of date]
    B --> C[Release WorkOrder\\n+TransactionHistory W]
    C --> D[Schedule routing\\nops 1..7 by Location]
  end
  subgraph floor[Shop floor]
    D --> E[Frame Forming / Welding / Debur / Paint]
    E --> F[Subassembly] --> G[Final Assembly]
    G --> H{Quality check}
  end
  H -- defect --> S[Scrap: ScrapReason]
  H -- pass --> I[EndDate, StockedQty\\nFinished Goods Storage]""",
 "evidence": [
  {"metric": "wo.state"}, {"metric": "wo.qty"}, {"metric": "wo.with_scrap"}, {"metric": "wo.scrap_reason"},
  {"metric": "wo.with_routing"}, {"metric": "wo.products"}, {"metric": "wor.location"}, {"metric": "wor.late_ops"}, {"metric": "wor.cost"},
  {"metric": "bom.level"}, {"metric": "bom.assemblies"}, {"metric": "bom.ended"},
  {"metric": "th.type", "keys": ["current:W", "archive:W"]}, {"metric": "location.costrate", "note": "CostRate / Availability (hours) for work centres"},
  {"metric": "edh.current_by_group", "keys": ["Manufacturing", "Quality Assurance"]},
 ],
 "coverage": {
  "access_patterns": ["INV-04", "INV-05", "INV-06", "INV-03"],
  "app_pages": [],
  "redshift": ["none: AdventureWorksDW has no manufacturing fact; WorkOrder items land in Redshift via zero-ETL only"],
 },
 "gaps": [
  "No production UI: BOM explosion (INV-04), where-used (INV-05) and work-order/routing (INV-06) are designed but unused.",
  "No work-order status column: open/late must be derived from dates (the design uses a sparse index on open WOs).",
  "No component consumption (backflush) and no link from sales demand to work orders in either system.",
  "No production KPIs (on-time rate, scrap rate by reason, planned vs actual cost) in Redshift.",
 ],
},
# ---------------------------------------------------------------------------------------------------------------
{
 "id": "inventory", "name": "Inventory management", "domain": "Production / Inventory",
 "summary": "Stock is held per product per location (14 locations, shelf/bin); every sale, purchase receipt and work order writes a stock transaction; old transactions are archived; reorder points and safety stock drive replenishment.",
 "actors": ["Inventory controller (Inventory Management, 18 staff)", "Buyer", "Planner", "System triggers"],
 "trigger": "Any stock movement (sale S, purchase P, work order W) or a periodic stock review.",
 "steps": [
  {"name": "Record movement", "actor": "System (triggers)", "reads": [], "writes": ["Production.TransactionHistory (S/P/W)"], "basis": "evidenced", "note": "S = sales lines, W = work orders, P = PO receipts; written by triggers, not by users."},
  {"name": "Adjust on-hand per location/bin", "actor": "Inventory controller", "reads": ["Production.Location"], "writes": ["Production.ProductInventory (Quantity, Shelf, Bin)"], "basis": "inferred", "note": "Nothing links transactions to ProductInventory quantities; they are maintained separately (cycle counts)."},
  {"name": "Review reorder / safety stock", "actor": "Inventory controller", "reads": ["Production.Product (ReorderPoint, SafetyStockLevel)", "Production.ProductInventory", "dbo.ufnGetStock"], "writes": [], "basis": "evidenced", "note": "60 sellable products below reorder point, 122 below safety stock (current snapshot)."},
  {"name": "Archive old transactions", "actor": "DBA / batch", "reads": ["Production.TransactionHistory"], "writes": ["Production.TransactionHistoryArchive"], "basis": "evidenced", "note": "Archive covers 2011-04-16..2013-07-30, current 2013-07-31..2014-08-03: a clean date cut-over."},
 ],
 "state_entity": "Production.Product stock level vs ReorderPoint / SafetyStockLevel (derived)", "state_values": {"ok": "on hand >= ReorderPoint", "reorder": "SafetyStockLevel <= on hand < ReorderPoint", "below_safety": "on hand < SafetyStockLevel"},
 "state_diagram": """stateDiagram-v2
    [*] --> OK
    OK --> Reorder: on hand < ReorderPoint
    Reorder --> BelowSafety: on hand < SafetyStockLevel
    Reorder --> OK: receipt (P) / work order (W)
    BelowSafety --> OK: receipt / work order
    note right of BelowSafety: derived; 122 sellable products today""",
 "flowchart": """flowchart LR
  S[Sales line] -->|trigger: S| TH[(TransactionHistory)]
  P[PO receipt] -->|trigger: P| TH
  W[Work order] -->|trigger: W| TH
  TH -->|nightly cut-over| AR[(TransactionHistoryArchive)]
  C[Cycle count / adjust] --> PI[(ProductInventory\\nper location, shelf, bin)]
  PI --> R{below ReorderPoint?}
  R -- yes, MakeFlag=0 --> PO[Procure-to-pay]
  R -- yes, MakeFlag=1 --> WO[Plan-to-produce]""",
 "evidence": [
  {"metric": "th.type"}, {"metric": "th.daterange"}, {"metric": "inv.by_location"},
  {"metric": "inv.products_with_stock"}, {"metric": "inv.below_reorder"}, {"metric": "inv.below_safety"},
  {"metric": "edh.current_by_group", "keys": ["Inventory Management"]},
 ],
 "coverage": {
  "access_patterns": ["INV-01", "INV-02", "INV-03", "INV-07"],
  "app_pages": ["Products admin shows a stock copy (total on hand) only"],
  "redshift": ["dw.fact_product_inventory (daily balance, INV-07)"],
 },
 "gaps": [
  "No stock-by-location page, no low-stock dashboard (INV-02 sparse index exists, unused).",
  "Checkout does not reserve or decrement stock and writes no S transaction, so DynamoDB-native orders break the S-rows = order-lines invariant.",
  "No stock adjustment / transfer between locations.",
 ],
},
# ---------------------------------------------------------------------------------------------------------------
{
 "id": "sales-management", "name": "Sales management (territories, quotas, special offers)", "domain": "Sales",
 "summary": "Sales management assigns sales people to territories, sets quarterly quotas, tracks attainment, and runs promotions (volume, seasonal, clearance, new-product) for resellers and customers.",
 "actors": ["VP / sales managers", "Sales people (17)", "Marketing (promotions)"],
 "trigger": "Fiscal quarter start (quota), territory reorganisation, product lifecycle event (promotion).",
 "steps": [
  {"name": "Assign territory", "actor": "Sales manager", "reads": ["Sales.SalesTerritory"], "writes": ["Sales.SalesTerritoryHistory (StartDate/EndDate)", "Sales.SalesPerson.TerritoryID"], "basis": "evidenced", "note": "4 territory assignments ended (re-assignments); 3 sales people have no territory (managers)."},
  {"name": "Assign stores to sales person", "actor": "Sales manager", "reads": [], "writes": ["Sales.Store.SalesPersonID"], "basis": "evidenced", "note": "All 701 stores have an account manager."},
  {"name": "Set quarterly quota", "actor": "Sales manager", "reads": [], "writes": ["Sales.SalesPersonQuotaHistory", "Sales.SalesPerson.SalesQuota"], "basis": "evidenced", "note": "163 quotas, quarterly 2011-05-31..2014-03-01 for 17 people."},
  {"name": "Track attainment", "actor": "Sales manager", "reads": ["Sales.SalesOrderHeader", "Sales.SalesPerson (SalesYTD, SalesLastYear, Bonus, CommissionPct)"], "writes": [], "basis": "evidenced", "note": "DW FactSalesQuota + vSalesPersonSalesByFiscalYears view."},
  {"name": "Create promotion", "actor": "Marketing", "reads": [], "writes": ["Sales.SpecialOffer (Type, Category, DiscountPct, Min/MaxQty, dates)", "Sales.SpecialOfferProduct"], "basis": "evidenced", "note": "16 offers: 5 volume tiers, seasonal, clearance (discontinued product), excess inventory, new product."},
 ],
 "state_entity": "Sales.SpecialOffer (derived from StartDate/EndDate)", "state_values": {"scheduled": "today < StartDate", "active": "StartDate <= today <= EndDate", "expired": "today > EndDate"},
 "state_diagram": """stateDiagram-v2
    [*] --> Scheduled: offer created
    Scheduled --> Active: StartDate reached
    Active --> Expired: EndDate passed
    Expired --> [*]
    state Quota {
      [*] --> Set: quarter start
      Set --> Attained: sales >= quota
      Set --> Missed: quarter end, sales < quota
    }""",
 "flowchart": """flowchart LR
  subgraph Management
    A([Quarter start]) --> B[Set quota per sales person]
    C([Reorg]) --> D[Territory assignment\\nSalesTerritoryHistory]
    D --> E[Assign stores]
  end
  subgraph Marketing
    F([Lifecycle event: new / excess / discontinued]) --> G[SpecialOffer + products]
  end
  G --> H[Reseller order lines get discount]
  B --> I[Attainment = orders vs quota]
  H --> I""",
 "evidence": [
  {"metric": "quota.range"}, {"metric": "territoryhistory.ended"}, {"metric": "salesperson.no_territory"},
  {"metric": "store.no_salesperson"}, {"metric": "specialoffer.type_category"}, {"metric": "specialoffer.products"},
  {"metric": "sod.lines_by_offer"},
 ],
 "coverage": {
  "access_patterns": ["SAL-08", "SAL-09", "SAL-10", "SAL-11", "SAL-12", "CAT-10"],
  "app_pages": [],
  "redshift": ["dw.fact_sales_quota", "dw.dim_sales_territory", "dw.dim_promotion", "dw.dim_employee (SCD2)", "QuickSight dashboard over dw.v_sales"],
 },
 "gaps": [
  "Analytics exist (Redshift/QuickSight) but no operational UI: no quota entry, territory reassignment, or promotion maintenance.",
  "Offers are never applied by the DynamoDB checkout (CAT-10 unused), so a new promotion has no effect on the shop.",
  "Promotion offers with zero sales (e.g. Mountain Tire Sale, LL Road Frame Sale, Half-Price Pedal Sale) are visible in the data: a promotion-effectiveness report is an easy add.",
 ],
},
# ---------------------------------------------------------------------------------------------------------------
{
 "id": "customer-person", "name": "Customer / person management", "domain": "Person / Customer",
 "summary": "Every party (individual, store, vendor, employee, contact) is a BusinessEntity with addresses, emails, phones and contact roles; individuals register as customers, stores get contacts, cards are saved for checkout.",
 "actors": ["Shopper (self-service)", "Customer service / admin", "Sales person (store contacts)", "Marketing (email promotion opt-in)"],
 "trigger": "Registration, profile change, new store account, or a new vendor/employee contact.",
 "steps": [
  {"name": "Create business entity + person", "actor": "Shopper / admin", "reads": [], "writes": ["Person.BusinessEntity", "Person.Person (PersonType, EmailPromotion, Demographics)", "Person.Password"], "basis": "evidenced", "note": "Trigger iuPerson maintains Demographics XML; all 19,972 people have it."},
  {"name": "Add contact channels", "actor": "Shopper", "reads": ["Person.PhoneNumberType", "Person.AddressType", "Person.StateProvince"], "writes": ["Person.EmailAddress", "Person.PersonPhone", "Person.Address", "Person.BusinessEntityAddress"], "basis": "evidenced", "note": "Addresses typed Home 18,774, Main Office 805, Shipping 35."},
  {"name": "Become a customer", "actor": "System", "reads": ["Sales.SalesTerritory"], "writes": ["Sales.Customer (PersonID and/or StoreID, TerritoryID, AccountNumber)"], "basis": "evidenced", "note": "18,484 individuals, 701 stores, 635 store contacts as customers; 19,119 have ordered."},
  {"name": "Save a card", "actor": "Shopper", "reads": [], "writes": ["Sales.CreditCard", "Sales.PersonCreditCard"], "basis": "evidenced", "note": "19,118 cards across 4 card types."},
  {"name": "Maintain store and its contacts", "actor": "Sales person", "reads": ["Person.ContactType"], "writes": ["Sales.Store (Demographics)", "Person.BusinessEntityContact"], "basis": "evidenced", "note": "909 contacts in 7 roles (Owner, Purchasing Agent/Manager...)."},
  {"name": "Marketing opt-in", "actor": "Marketing", "reads": ["Person.Person.EmailPromotion"], "writes": [], "basis": "inferred", "note": "EmailPromotion 0/1/2 (none / AW / AW + partners) suggests campaign targeting; DW ProspectiveBuyer / vTargetMail support it."},
 ],
 "state_entity": "Sales.Customer (derived)", "state_values": {"prospect": "Person without Customer", "registered": "Customer, no orders", "active": "has orders"},
 "state_diagram": """stateDiagram-v2
    [*] --> Person: BusinessEntity + Person
    Person --> Registered: Sales.Customer row
    Registered --> Active: first order
    Active --> Active: repeat order
    Person --> Employee: PersonType EM
    Person --> StoreContact: BusinessEntityContact (SC)
    Person --> VendorContact: BusinessEntityContact (VC)""",
 "flowchart": """flowchart LR
  A([Register]) --> B[BusinessEntity + Person + Password]
  B --> C[Email / phone / address]
  C --> D[Sales.Customer, AccountNumber]
  D --> E[Save credit card]
  F([New store]) --> G[Store + BusinessEntityContact roles]
  G --> D
  D --> H([Order-to-cash])""",
 "evidence": [
  {"metric": "person.type"}, {"metric": "customer.kind"}, {"metric": "customer.with_orders"}, {"metric": "address.type"},
  {"metric": "contact.type"}, {"metric": "creditcard.type"}, {"metric": "person.email_promotion"}, {"metric": "person.with_demographics"},
 ],
 "coverage": {
  "access_patterns": ["CUS-01", "CUS-02", "CUS-03", "CUS-04", "CUS-05", "CUS-06", "CUS-07", "CUS-08", "CUS-09", "CUS-10", "CUS-11"],
  "app_pages": ["Login (demo)", "Customers admin: list, details, create, edit name"],
  "redshift": ["dw.dim_customer", "dw.dim_geography", "dw.dim_reseller"],
 },
 "gaps": [
  "No self-service profile: shopper cannot add an address, email, phone or card (CUS-09 designed, unused).",
  "No store / contact management screen (CUS-07, CUS-11).",
  "Login accepts only 5 demo customers with a shared password; real registration + password hash not used.",
  "No customer 360 (orders + demographics + territory) in the app.",
 ],
},
# ---------------------------------------------------------------------------------------------------------------
{
 "id": "hr", "name": "Human resources (hire, department moves, pay, shifts)", "domain": "HumanResources",
 "summary": "Candidates apply, are hired into a department and shift with a pay rate; employees move departments/shifts and get pay changes; the org chart is a hierarchy.",
 "actors": ["HR (Human Resources dept)", "Hiring manager", "Employee", "Job candidate"],
 "trigger": "Vacancy / application, transfer, pay review.",
 "steps": [
  {"name": "Receive application", "actor": "Candidate", "reads": [], "writes": ["HumanResources.JobCandidate (Resume XML)"], "basis": "evidenced", "note": "13 candidates; uspSearchCandidateResumes."},
  {"name": "Hire", "actor": "HR", "reads": ["HumanResources.Department", "HumanResources.Shift"], "writes": ["Person.BusinessEntity / Person.Person (EM)", "HumanResources.Employee (HireDate, JobTitle, OrganizationNode)", "EmployeeDepartmentHistory", "EmployeePayHistory", "JobCandidate.BusinessEntityID"], "basis": "evidenced", "note": "2 of 13 candidates are linked to an employee; hires peak 2008-2009. uspUpdateEmployeeHireInfo writes Employee + PayHistory together."},
  {"name": "Transfer department / shift", "actor": "HR", "reads": [], "writes": ["EmployeeDepartmentHistory (close EndDate, insert new)"], "basis": "evidenced", "note": "5 employees have moved (6 ended assignments)."},
  {"name": "Change pay", "actor": "HR", "reads": [], "writes": ["EmployeePayHistory (RateChangeDate, Rate, PayFrequency)"], "basis": "evidenced", "note": "13 employees have 3 rates; others 1."},
  {"name": "Update login / personal info", "actor": "HR / employee", "reads": [], "writes": ["HumanResources.Employee"], "basis": "evidenced", "note": "uspUpdateEmployeeLogin, uspUpdateEmployeePersonalInfo."},
  {"name": "Terminate", "actor": "HR", "reads": [], "writes": ["Employee.CurrentFlag = 0"], "basis": "inferred", "note": "dEmployee blocks deletes; CurrentFlag is 1 for all 290, so no terminations recorded."},
 ],
 "state_entity": "HumanResources.Employee (CurrentFlag) + JobCandidate", "state_values": {"candidate": "JobCandidate, BusinessEntityID null", "employed": "CurrentFlag = 1", "terminated": "CurrentFlag = 0 (never seen)"},
 "state_diagram": """stateDiagram-v2
    [*] --> Candidate: JobCandidate
    Candidate --> Employed: hire (Employee, dept, shift, pay)
    Employed --> Employed: transfer (EDH) / pay change (EPH)
    Employed --> Terminated: CurrentFlag = 0 (inferred, 0 rows)
    Terminated --> [*]""",
 "flowchart": """flowchart LR
  A([Application]) --> B[JobCandidate]
  B --> C{Hire?}
  C -- yes --> D[Person EM + Employee\\nOrganizationNode]
  D --> E[Dept + Shift: EDH]
  D --> F[Pay rate: EPH]
  E --> G([Transfer: end EDH, new EDH])
  F --> H([Pay review: new EPH])""",
 "evidence": [
  {"metric": "emp.flags"}, {"metric": "emp.org_level"}, {"metric": "emp.hires_by_year"}, {"metric": "edh.assignments_per_emp"},
  {"metric": "edh.ended"}, {"metric": "edh.current_by_shift"}, {"metric": "edh.current_by_group"}, {"metric": "eph.rates_per_emp"},
  {"metric": "eph.frequency"}, {"metric": "jobcandidate.hired"},
 ],
 "coverage": {
  "access_patterns": ["HR-01", "HR-02", "HR-03", "HR-04", "HR-05", "HR-06 (out of scope)"],
  "app_pages": [],
  "redshift": ["dw.dim_employee (SCD2 per department assignment)"],
 },
 "gaps": [
  "No HR UI at all; org-chart (HR-03, materialised path) is designed but unused.",
  "Recruiting (JobCandidate résumé search) explicitly out of scope (HR-06).",
  "Hire is a multi-table transaction (Person + Employee + EDH + EPH) that the DynamoDB design has no write pattern for beyond HR-05.",
 ],
},
# ---------------------------------------------------------------------------------------------------------------
{
 "id": "catalog", "name": "Product catalog management", "domain": "Production / Catalog",
 "summary": "Product management introduces products (by model, with multilingual descriptions, photos, documents), maintains list price and standard cost history, and retires products via SellEndDate / DiscontinuedDate.",
 "actors": ["Product manager / marketing", "Engineering (documents, BOM)", "Cost accounting (standard cost)"],
 "trigger": "New model year, price/cost review, product retirement.",
 "steps": [
  {"name": "Create model + descriptions", "actor": "Product manager", "reads": ["Production.Culture"], "writes": ["Production.ProductModel", "Production.ProductDescription", "Production.ProductModelProductDescriptionCulture", "Production.Illustration"], "basis": "evidenced", "note": "128 models, 762 descriptions in 6 cultures."},
  {"name": "Create product (SKU)", "actor": "Product manager", "reads": ["Production.ProductSubcategory", "Production.UnitMeasure"], "writes": ["Production.Product (MakeFlag, FinishedGoodsFlag, SellStartDate)", "Production.ProductProductPhoto"], "basis": "evidenced", "note": "Products introduced in waves: 2008, 2011, 2012, 2013. 209 products have no subcategory (components)."},
  {"name": "Attach documents", "actor": "Engineering", "reads": [], "writes": ["Production.Document (Status)", "Production.ProductDocument"], "basis": "evidenced", "note": "Document status 1 Pending approval / 2 Approved / 3 Obsolete (ufnGetDocumentStatusText)."},
  {"name": "Change list price / standard cost", "actor": "Product manager / cost accounting", "reads": [], "writes": ["Production.Product (ListPrice, StandardCost)", "Production.ProductListPriceHistory", "Production.ProductCostHistory"], "basis": "evidenced", "note": "52 products have 2 price versions, 25 have 3."},
  {"name": "Retire", "actor": "Product manager", "reads": [], "writes": ["Production.Product.SellEndDate / DiscontinuedDate", "Sales.SpecialOffer (clearance)"], "basis": "evidenced", "note": "98 products sell-ended; DiscontinuedDate never used."},
 ],
 "state_entity": "Production.Product (SellStartDate / SellEndDate / DiscontinuedDate)", "state_values": {"planned": "SellStartDate in future", "selling": "SellEndDate null", "sell_ended": "SellEndDate set", "discontinued": "DiscontinuedDate set (0 rows)"},
 "state_diagram": """stateDiagram-v2
    [*] --> Planned: product created
    Planned --> Selling: SellStartDate
    Selling --> Selling: price / cost change (history row)
    Selling --> Clearance: SpecialOffer Discontinued Product
    Clearance --> SellEnded: SellEndDate
    Selling --> SellEnded: SellEndDate
    SellEnded --> Discontinued: DiscontinuedDate (never used)
    state Document {
      [*] --> PendingApproval
      PendingApproval --> Approved
      Approved --> Obsolete
    }""",
 "flowchart": """flowchart LR
  A([New model year]) --> B[ProductModel + descriptions x6 cultures]
  B --> C[Products per size/colour\\nSellStartDate]
  C --> D[Photos, documents]
  E([Price / cost review]) --> F[ListPrice / StandardCost\\n+ history rows]
  G([Retire]) --> H[Clearance offer] --> I[SellEndDate]""",
 "evidence": [
  {"metric": "product.lifecycle"}, {"metric": "product.sellstart_year"}, {"metric": "product.flags"}, {"metric": "product.no_subcategory"},
  {"metric": "pricehistory.versions"}, {"metric": "costhistory.versions"}, {"metric": "document.status"}, {"metric": "photo.nonplaceholder_products"},
 ],
 "coverage": {
  "access_patterns": ["CAT-01", "CAT-02", "CAT-04", "CAT-05", "CAT-06", "CAT-07", "CAT-08", "CAT-09", "CAT-12", "CAT-13"],
  "app_pages": ["Products admin (list, details, create, edit, deactivate)", "Categories admin", "Product detail with 6-culture descriptions"],
  "redshift": ["dw.dim_product (SCD2 on price history)", "dw.dim_product_category / _subcategory"],
 },
 "gaps": [
  "Price edit in Products admin does not append a PRICE# history item (no PRICE#/ListPriceHistory write in src/), although CAT-07 requires it; the Redshift SCD2 dim_product will miss app price changes.",
  "No product model / description editor, no photo or document management, no document approval.",
  "Best-covered process today; Chapter 2 value is small.",
 ],
},
# ---------------------------------------------------------------------------------------------------------------
{
 "id": "reviews-returns", "name": "Product reviews and returns", "domain": "Catalog / Sales",
 "summary": "Reviews: customers rate and comment on products (evidenced but tiny). Returns: NOT evidenced in the OLTP schema - no RMA, credit memo or return-reason tables, no return transaction type.",
 "actors": ["Shopper (reviewer)", "Moderator (inferred)", "Customer service (returns, inferred)"],
 "trigger": "Shopper submits a review after purchase; (returns: customer asks to return - inferred only).",
 "steps": [
  {"name": "Submit review", "actor": "Shopper", "reads": ["Production.Product"], "writes": ["Production.ProductReview (Rating 1-5, Comments, ReviewerName, EmailAddress)"], "basis": "evidenced", "note": "4 reviews only (ratings 2, 4, 5, 5)."},
  {"name": "Moderate / publish", "actor": "Moderator", "reads": [], "writes": [], "basis": "inferred", "note": "No approval/status column on ProductReview."},
  {"name": "Request return (RMA)", "actor": "Customer service", "reads": ["Sales.SalesOrderHeader"], "writes": [], "basis": "inferred", "note": "No table; status 6 Cancelled and 4 Rejected exist only as status text; DW DimAccount has one 'returns' finance account (static)."},
 ],
 "state_entity": "Production.ProductReview (no status column)", "state_values": {"submitted": "row exists"},
 "state_diagram": """stateDiagram-v2
    [*] --> Submitted: ProductReview insert
    Submitted --> Published: moderation (inferred)
    Submitted --> Rejected: moderation (inferred)
    state "Return (not in schema)" as RMA {
      [*] --> Requested
      Requested --> Received
      Received --> Refunded
    }""",
 "flowchart": """flowchart LR
  A([Shopper received order]) --> B[Write review: rating, comment]
  B --> C[(ProductReview)]
  C --> D[Product detail shows reviews + average]
  A -. inferred .-> R[Return request - no table]""",
 "evidence": [
  {"metric": "review.rating"}, {"metric": "returns.tables", "note": "no Return/RMA/Refund/CreditMemo table in AdventureWorks2022"},
  {"metric": "returns.dw_finance_accounts"}, {"metric": "soh.status_by_channel", "note": "no order is Cancelled (6) or Rejected (4)"},
 ],
 "coverage": {
  "access_patterns": ["CAT-11"],
  "app_pages": [],
  "redshift": [],
 },
 "gaps": [
  "Reviews: CAT-11 is designed (REVIEW# items under the product) but product detail neither shows nor accepts reviews.",
  "Returns: would be a net-new DynamoDB entity (RMA under ORDER#), not a migration of existing data.",
 ],
},
]

CANDIDATES = [
 {"rank": 1, "name": "Back-office order fulfilment (approve → pick → ship, cancel)", "processes": ["o2c-internet", "o2c-reseller", "inventory"],
  "patterns": ["SAL-05", "SAL-06", "INV-03", "INV-01"], "effort": "M",
  "demo_value": "Closes the loop on orders placed in the new shop (they sit at status 1 today). Shows the sparse ORDERSTATUS GSI, a TransactWriteItems status change + stock decrement + S transaction, CDC to the before app and zero-ETL to Redshift in one click.",
  "fills_gaps": ["orders stuck at status 1", "no stock movement on checkout"]},
 {"rank": 2, "name": "Real pricing at checkout: special offers, tax by state, ship-method freight", "processes": ["o2c-internet", "sales-management"],
  "patterns": ["CAT-10", "REF-02", "REF-04"], "effort": "S",
  "demo_value": "Replaces demo 8%/2.5% with the real tables; a new promotion immediately changes shop prices; shows denormalised offer items on the product partition.",
  "fills_gaps": ["flat tax/freight", "offers unused"]},
 {"rank": 3, "name": "Procurement workspace: low-stock → suggested PO → approve → receive", "processes": ["procure-to-pay", "inventory"],
  "patterns": ["INV-02", "PUR-02", "PUR-04", "PUR-05", "PUR-07"], "effort": "L",
  "demo_value": "A whole new domain (aw-purchasing) going live with no UI before; the reorder → vendor → PO → receipt chain is a story business stakeholders understand; status machine with partial receipts and rejects.",
  "fills_gaps": ["no purchasing UI", "receipts never reach stock"]},
 {"rank": 4, "name": "Product reviews on product detail", "processes": ["reviews-returns"], "patterns": ["CAT-11"], "effort": "S",
  "demo_value": "Cheap, visible shopper feature; one-partition read with the product; good warm-up for a write path through CDC.",
  "fills_gaps": ["reviews not shown"]},
 {"rank": 5, "name": "Production floor: open work orders, routing timeline, BOM explorer, scrap", "processes": ["plan-to-produce"],
  "patterns": ["INV-04", "INV-05", "INV-06"], "effort": "M",
  "demo_value": "Shows the 'hard' patterns solved in DynamoDB (recursive BOM, where-used) and a visual routing Gantt; strong technical showcase.",
  "fills_gaps": ["no production UI", "no production KPIs"]},
 {"rank": 6, "name": "Sales-person workspace: my stores, reseller order entry by PO number, quota attainment", "processes": ["o2c-reseller", "sales-management"],
  "patterns": ["CUS-07", "SAL-07", "SAL-10", "SAL-12", "SAL-13", "SAL-08"], "effort": "M",
  "demo_value": "Mixes DynamoDB operational reads with a Redshift attainment tile (D7 split in action).",
  "fills_gaps": ["no B2B channel in app", "SalesYTD stale"]},
 {"rank": 7, "name": "Customer self-service profile (addresses, cards, email opt-in)", "processes": ["customer-person"], "patterns": ["CUS-09", "CUS-03"], "effort": "S",
  "demo_value": "Lets a shopper add a ship-to address before checkout; small but completes the shopper journey.",
  "fills_gaps": ["no profile editing"]},
 {"rank": 8, "name": "Analytics additions: promotion effectiveness, vendor performance, production scrap/on-time", "processes": ["sales-management", "procure-to-pay", "plan-to-produce"],
  "patterns": ["DW-04"], "effort": "M", "demo_value": "New Redshift views over zero-ETL data that AdventureWorksDW never had: shows the warehouse is more than a DW rebuild.",
  "fills_gaps": ["no purchasing/production analytics"]},
 {"rank": 9, "name": "HR: employee directory + org chart", "processes": ["hr"], "patterns": ["HR-01", "HR-03", "HR-04"], "effort": "M",
  "demo_value": "Hierarchy via materialised path is a nice pattern, but HR is far from the shop story.", "fills_gaps": ["no HR UI"]},
 {"rank": 10, "name": "Returns / RMA", "processes": ["reviews-returns"], "patterns": [], "effort": "L",
  "demo_value": "Net-new data model (no source data); only worth it to show green-field DynamoDB design after migration.", "fills_gaps": ["returns absent from schema"]},
]
