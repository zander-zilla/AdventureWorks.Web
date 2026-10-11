# Seed access patterns (draft for phase 2)

Starting list for John to refine in phase 2 (add frequency, latency, consistency, priority; cut what the demo doesn't need).
Source column: **App** = AdventureWorks.Web screen (incl. demo shop), **SQL** = existing view/proc/function in AdventureWorks2022,
**Biz** = common business operation, **CDC** = needed by the replication pipeline, **DW** = needed to rebuild DW facts.
IDs are stable so phase 3 can reference them.

## Catalog (`aw-catalog`)
| ID | Pattern | Inputs | Source |
|---|---|---|---|
| CAT-01 | List top-level categories with their subcategories | – | App (ProductCategories Index) |
| CAT-02 | Get category/subcategory by id; create/update/delete | id | App (ProductCategories CRUD) |
| CAT-03 | List products (paged) with category + model names | page | App (Products Index) |
| CAT-04 | List products in a subcategory, sellable only (SellEndDate null), sorted by name or price | subcategoryId | App (Shop), Biz |
| CAT-05 | Get product detail page: product + model + description (culture) + photos + reviews + active offers + stock qty | productId, culture | App (Products Details), SQL vProductAndDescription |
| CAT-06 | Get product by ProductNumber (SKU) | productNumber | Biz |
| CAT-07 | Create/update/delete product (with uniqueness on Name and ProductNumber) | product | App (Products CRUD) |
| CAT-08 | List products of a model; get model catalog description / instructions | productModelId | SQL vProductModelCatalogDescription, vProductModelInstructions |
| CAT-09 | Price as of a date (list price / standard cost history) | productId, date | SQL ufnGetProductListPrice, ufnGetProductStandardCost, DW |
| CAT-10 | Active special offers for a product on a date | productId, date | Biz, SQL ufnGetProductDealerPrice |
| CAT-11 | Add / list reviews for a product (newest first) | productId | Biz |
| CAT-12 | Product search by name prefix | text | Biz (shopper pages) |

## Inventory & Manufacturing (`aw-inventory`)
| ID | Pattern | Inputs | Source |
|---|---|---|---|
| INV-01 | Stock for a product across locations (total + per location) | productId | SQL ufnGetStock, Biz |
| INV-02 | Products below reorder point / safety stock | – | Biz |
| INV-03 | Record inventory transaction; list transactions for product by date range | productId, dates | Biz, DW (FactProductInventory) |
| INV-04 | Bill of materials explosion for an assembly (multi-level, as of date) | productAssemblyId, date | SQL uspGetBillOfMaterials |
| INV-05 | Where-used: assemblies that use a component | componentId, date | SQL uspGetWhereUsedProductID |
| INV-06 | Open work orders by due date; work order with routing steps | date / workOrderId | Biz |

## Sales (`aw-sales`)
| ID | Pattern | Inputs | Source |
|---|---|---|---|
| SAL-01 | Place order (header + lines, transactional, compute subtotal/tax/freight) | customerId, lines | App (Shop Order), Biz |
| SAL-02 | List a customer's orders, newest first (paged) | customerId | App (MyOrders) |
| SAL-03 | Get order with lines (+ sales reasons) | salesOrderId / SalesOrderNumber | App, Biz |
| SAL-04 | Update order status (ship, cancel); orders by status + date (e.g. open orders to ship) | status, date | Biz, SQL ufnGetSalesOrderStatusText |
| SAL-05 | Shopping cart: add/update/remove item, get cart | cartId (customer) | Biz (Sales.ShoppingCartItem), shopper pages |
| SAL-06 | Orders for a sales person / store by date range | salesPersonId / storeId | Biz, DW (FactResellerSales) |
| SAL-07 | Orders by territory by date range | territoryId | Biz |
| SAL-08 | Sales person with quota history & YTD sales | salesPersonId | SQL vSalesPerson, vSalesPersonSalesByFiscalYears |
| SAL-09 | Territory with current sales people (history) | territoryId | Biz |
| SAL-10 | Look up order by PurchaseOrderNumber / CreditCardApprovalCode | text | Biz |
| SAL-11 | Apply idempotent CDC upsert/delete for header/detail keyed by SQL PK | source PK + LSN | CDC |

## Customer & Party (`aw-customer`)
| ID | Pattern | Inputs | Source |
|---|---|---|---|
| CUS-01 | Log in by email (unique), verify password hash | email | App (Account/Login) |
| CUS-02 | List customers (paged) | page | App (Customers Index) |
| CUS-03 | Get customer profile: person/store + emails + phones + addresses + cards (masked) | customerId | App (Customers Details), SQL vIndividualCustomer |
| CUS-04 | Create/update/delete customer (uniqueness on AccountNumber, email) | customer | App (Customers CRUD) |
| CUS-05 | Get customer by AccountNumber | accountNumber | Biz, DW |
| CUS-06 | Store with contacts and addresses; store demographics | storeId | SQL vStoreWithContacts, vStoreWithAddresses, vStoreWithDemographics |
| CUS-07 | Person demographics | personId | SQL vPersonDemographics, DW (DimCustomer) |
| CUS-08 | Customers in a territory | territoryId | Biz |
| CUS-09 | Add/update address, email, phone, card | customerId | Biz, shopper pages |
| CUS-10 | Contact info for any business entity (person/store/vendor/employee) | businessEntityId | SQL ufnGetContactInformation |

## Purchasing (`aw-purchasing`)
| ID | Pattern | Inputs | Source |
|---|---|---|---|
| PUR-01 | Vendor with addresses / contacts | vendorId | SQL vVendorWithAddresses, vVendorWithContacts |
| PUR-02 | Vendors that supply a product (with lead time, std price) | productId | Biz |
| PUR-03 | Products supplied by a vendor | vendorId | Biz |
| PUR-04 | Create PO; get PO with lines; POs by vendor by date; POs by status | vendorId / status | Biz, SQL ufnGetPurchaseOrderStatusText |
| PUR-05 | POs raised by an employee | employeeId | Biz |

## HR (`aw-hr`)
| ID | Pattern | Inputs | Source |
|---|---|---|---|
| HR-01 | Employee profile with current department, shift, pay | employeeId | SQL vEmployee, vEmployeeDepartment |
| HR-02 | Department/shift history for employee | employeeId | SQL vEmployeeDepartmentHistory |
| HR-03 | Direct reports / management chain | employeeId | SQL uspGetManagerEmployees, uspGetEmployeeManagers |
| HR-04 | Employees in a department (current) | departmentId | Biz |
| HR-05 | Update hire info / login / personal info | employeeId | SQL uspUpdateEmployeeHireInfo, uspUpdateEmployeeLogin, uspUpdateEmployeePersonalInfo |
| HR-06 | Job candidates; search résumés | text | SQL vJobCandidate*, uspSearchCandidateResumes (full-text → OpenSearch or out of scope) |

## Reference (`aw-reference`)
| ID | Pattern | Inputs | Source |
|---|---|---|---|
| REF-01 | List countries; states for a country | countryCode | SQL vStateProvinceCountryRegion, App (address forms) |
| REF-02 | Tax rate for a state | stateProvinceId | Biz (SAL-01) |
| REF-03 | Currency rate for currency pair on a date | from, to, date | Biz, DW (FactCurrencyRate) |
| REF-04 | List ship methods (with rates) | – | Biz (SAL-01) |
| REF-05 | Units of measure, cultures | – | Biz |

## Cross-cutting (not DynamoDB patterns)
- Reports/aggregates (sales by fiscal year, territory rollups, BOM costing) → Redshift (phase 6), not GSIs.
- Full-text résumé search, ad-hoc queries → out of scope / Redshift / OpenSearch.
