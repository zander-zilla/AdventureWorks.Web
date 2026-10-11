# AdventureWorksDW2022 lineage (input for phase 6)

For each DW fact/dimension: the AdventureWorks2022 OLTP tables that feed it, the grain, and notes.
Microsoft does not ship the ETL for AdventureWorksDW, so this lineage is **inferred** from column names/semantics
and spot checks (row counts below are from the live DBs, see `inventory.md`). Items marked ⚠ have no OLTP source
and must be carried over as static data or synthesised.

Target in phase 6: Redshift tables built from the DynamoDB zero-ETL landing (per-domain tables) — the "OLTP sources"
below become `entityType` slices of `aw-*` tables.

## Dimensions

| DW table (rows) | Grain / key | OLTP sources | Domain(s) | Notes |
|---|---|---|---|---|
| DimDate (3,652) | day | – (generated) | – | Calendar + fiscal (FY starts July); generate in Redshift |
| DimCustomer (18,484) | individual customer, `CustomerAlternateKey` = AccountNumber | Sales.Customer (PersonID not null, StoreID null) ⨝ Person.Person (incl. Demographics XML: yearly income, education, occupation, cars, children, home owner, first purchase date) ⨝ EmailAddress ⨝ PersonPhone ⨝ BusinessEntityAddress(Home) ⨝ Address | Customer & Party, Reference | ✔ 18,484 = OLTP customers with StoreID null. Only *individual* (internet) customers; demographics shredded from `Person.Demographics` XML → must survive into DynamoDB as attributes |
| DimGeography (655) | city/state/postal | Person.Address (distinct city+postal) ⨝ StateProvince ⨝ CountryRegion ⨝ Sales.SalesTerritory | Reference, Customer & Party | Localised country names (Spanish/French) ⚠ static |
| DimReseller (701) | store, `ResellerAlternateKey` = Customer AccountNumber | Sales.Store (+ Demographics XML: business type, employees, annual sales/revenue, bank, year opened) ⨝ Sales.Customer ⨝ address | Customer & Party | |
| DimProduct (606) | product **version** (SCD2: StartDate/EndDate/Status) | Production.Product ⨝ ProductModel ⨝ ProductDescription (en/fr/… via ProductModelProductDescriptionCulture) ⨝ ProductListPriceHistory / ProductCostHistory (drive SCD2 rows) ⨝ ProductPhoto (LargePhoto) | Catalog | 606 rows vs 504 products = price/cost history versions; DealerPrice = ufnGetProductDealerPrice logic (60% list) |
| DimProductSubcategory (37) / DimProductCategory (4) | | Production.ProductSubcategory / ProductCategory | Catalog | Localised names ⚠ static |
| DimPromotion (16) | special offer | Sales.SpecialOffer | Catalog | Localised names ⚠ |
| DimSalesTerritory (11) | territory | Sales.SalesTerritory (+ "NA" row) | Sales | |
| DimEmployee (296) | employee version (SCD2 on department/pay/territory) | HumanResources.Employee ⨝ Person.Person ⨝ EmployeeDepartmentHistory ⨝ EmployeePayHistory ⨝ Sales.SalesPerson / SalesTerritoryHistory ⨝ EmailAddress/PersonPhone | HR, Sales, Customer & Party | Parent key from OrganizationNode hierarchy |
| DimCurrency (105) | currency | Sales.Currency | Reference | |
| DimSalesReason (10) | reason | Sales.SalesReason | Sales | |
| DimAccount (99), DimOrganization (14), DimDepartmentGroup (7), DimScenario (3) | finance chart of accounts / org | ⚠ none (finance not in OLTP) | – | **Decision: carried over to Redshift as static data** |

## Facts

| DW table (rows) | Grain | OLTP sources | Domain(s) | Notes |
|---|---|---|---|---|
| FactInternetSales (60,398) | order line, `OnlineOrderFlag = 1` | Sales.SalesOrderHeader ⨝ SalesOrderDetail; ProductKey via product version at OrderDate; CustomerKey; PromotionKey = SpecialOfferID; CurrencyKey via CurrencyRate; ProductStandardCost from ProductCostHistory | Sales (+ Catalog, Customer lookups) | ✔ verified: OLTP has exactly 60,398 lines with OnlineOrderFlag=1. DW dates are shifted vs OLTP |
| FactInternetSalesReason (64,515) | order line × reason | Sales.SalesOrderHeaderSalesReason ⨝ SalesOrderDetail | Sales | |
| FactResellerSales (60,855) | order line, `OnlineOrderFlag = 0` | Sales.SalesOrderHeader/Detail; ResellerKey from Customer.StoreID; EmployeeKey from SalesPersonID | Sales, Customer & Party, HR | OLTP has 60,919 offline lines vs 60,855 in DW (64 diff) → reconcile in phase 6 |
| FactSalesQuota (163) | sales person × quarter | Sales.SalesPersonQuotaHistory | Sales | |
| FactProductInventory (776,286) | product × day | Production.ProductInventory (snapshot) + TransactionHistory(+Archive) movements, daily balances | Inventory | Synthesised daily snapshots; in phase 6 rebuild from inventory transactions |
| FactCurrencyRate (14,264) | currency × day | Sales.CurrencyRate | Reference | |
| FactCallCenter (120), FactSurveyResponse (2,727), FactFinance (39,409), FactAdditionalInternationalProductDescription (15,168), NewFactCurrencyRate (50), ProspectiveBuyer (2,059) | | ⚠ none / static (call center, survey, finance, translations, data-mining samples) | – | **Decision: carried over to Redshift as static data** (one-time load from AdventureWorksDW2022, not via zero-ETL) |

## Views
`vDMPrep`, `vAssocSeqOrders`, `vAssocSeqLineItems`, `vTargetMail`, `vTimeSeries` are data-mining views over FactInternetSales/DimCustomer/DimProduct — rebuild as Redshift views if QuickSight needs them.

## Implications for the DynamoDB design (feed into phase 3)
- Keep `OnlineOrderFlag`, `SalesPersonID`, `StoreID`, `CurrencyRateID`, `SpecialOfferID`, product cost at order time on order/line items → facts can be built without joins back to SQL.
- Keep price/cost **history** items in Catalog (needed for DimProduct SCD2).
- Keep `Person.Demographics` / `Store.Demographics` (XML) as maps → DimCustomer/DimReseller attributes.
- Keep inventory transactions (not just current qty) if FactProductInventory is to be rebuilt.

## Decision: static carry-over (John, 2026-10-11)
DW tables with no OLTP source are copied **once** from AdventureWorksDW2022 into Redshift as static tables (phase 6, e.g. export to S3 → `COPY`), alongside the zero-ETL-fed tables:
FactFinance, DimAccount, DimOrganization, DimDepartmentGroup, DimScenario, FactCallCenter, FactSurveyResponse,
FactAdditionalInternationalProductDescription, NewFactCurrencyRate, ProspectiveBuyer, plus the localised-name columns
of DimGeography/DimProductCategory/DimProductSubcategory/DimPromotion (kept as static lookup tables joined in).
DimDate is generated in Redshift. FactSurveyResponse references DimCustomer by key, so DimCustomer surrogate keys
must be preserved (derive from CustomerID) for it to keep joining.
