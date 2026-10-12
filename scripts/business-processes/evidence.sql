-- Lifecycle evidence for docs/business-processes (run after scripts/reset-demo.sql).
-- Output: metric|key|value, one row per line. Rendered by evidence.py into docs/business-processes/evidence.json.
SET NOCOUNT ON;
USE AdventureWorks2022;
CREATE TABLE #e (m nvarchar(80), k nvarchar(120), v nvarchar(60));
DECLARE @d varchar(10) = 'yyyy-MM-dd';
-- order-to-cash
INSERT #e SELECT 'soh.status_by_channel', CONCAT(CASE OnlineOrderFlag WHEN 1 THEN 'internet' ELSE 'reseller' END,':',Status), COUNT(*) FROM Sales.SalesOrderHeader GROUP BY OnlineOrderFlag, Status;
INSERT #e SELECT 'soh.orderdate_range', CASE OnlineOrderFlag WHEN 1 THEN 'internet' ELSE 'reseller' END, CONCAT(FORMAT(MIN(OrderDate),@d),'..',FORMAT(MAX(OrderDate),@d)) FROM Sales.SalesOrderHeader GROUP BY OnlineOrderFlag;
INSERT #e SELECT 'soh.ship_minus_order_days', CONCAT(CASE OnlineOrderFlag WHEN 1 THEN 'internet' ELSE 'reseller' END,':',DATEDIFF(day,OrderDate,ShipDate)), COUNT(*) FROM Sales.SalesOrderHeader GROUP BY OnlineOrderFlag, DATEDIFF(day,OrderDate,ShipDate);
INSERT #e SELECT 'soh.due_minus_order_days', CONCAT(CASE OnlineOrderFlag WHEN 1 THEN 'internet' ELSE 'reseller' END,':',DATEDIFF(day,OrderDate,DueDate)), COUNT(*) FROM Sales.SalesOrderHeader GROUP BY OnlineOrderFlag, DATEDIFF(day,OrderDate,DueDate);
INSERT #e SELECT 'soh.shipdate_null', 'all', COUNT(*) FROM Sales.SalesOrderHeader WHERE ShipDate IS NULL;
INSERT #e SELECT 'soh.with_salesperson', CASE OnlineOrderFlag WHEN 1 THEN 'internet' ELSE 'reseller' END, SUM(CASE WHEN SalesPersonID IS NULL THEN 0 ELSE 1 END) FROM Sales.SalesOrderHeader GROUP BY OnlineOrderFlag;
INSERT #e SELECT 'soh.with_creditcard', CASE OnlineOrderFlag WHEN 1 THEN 'internet' ELSE 'reseller' END, SUM(CASE WHEN CreditCardID IS NULL THEN 0 ELSE 1 END) FROM Sales.SalesOrderHeader GROUP BY OnlineOrderFlag;
INSERT #e SELECT 'soh.with_purchaseorder', CASE OnlineOrderFlag WHEN 1 THEN 'internet' ELSE 'reseller' END, SUM(CASE WHEN PurchaseOrderNumber IS NULL THEN 0 ELSE 1 END) FROM Sales.SalesOrderHeader GROUP BY OnlineOrderFlag;
INSERT #e SELECT 'soh.with_currencyrate', CASE OnlineOrderFlag WHEN 1 THEN 'internet' ELSE 'reseller' END, SUM(CASE WHEN CurrencyRateID IS NULL THEN 0 ELSE 1 END) FROM Sales.SalesOrderHeader GROUP BY OnlineOrderFlag;
INSERT #e SELECT 'soh.revision', CAST(RevisionNumber AS varchar), COUNT(*) FROM Sales.SalesOrderHeader GROUP BY RevisionNumber;
INSERT #e SELECT 'soh.shipmethod', CONCAT(CASE OnlineOrderFlag WHEN 1 THEN 'internet' ELSE 'reseller' END,':',sm.Name), COUNT(*) FROM Sales.SalesOrderHeader h JOIN Purchasing.ShipMethod sm ON sm.ShipMethodID=h.ShipMethodID GROUP BY OnlineOrderFlag, sm.Name;
INSERT #e SELECT 'soh.comment_notnull', 'all', COUNT(*) FROM Sales.SalesOrderHeader WHERE Comment IS NOT NULL;
INSERT #e SELECT 'sod.lines_by_channel', CASE h.OnlineOrderFlag WHEN 1 THEN 'internet' ELSE 'reseller' END, COUNT(*) FROM Sales.SalesOrderDetail d JOIN Sales.SalesOrderHeader h ON h.SalesOrderID=d.SalesOrderID GROUP BY h.OnlineOrderFlag;
INSERT #e SELECT 'sod.discounted_lines', CASE h.OnlineOrderFlag WHEN 1 THEN 'internet' ELSE 'reseller' END, SUM(CASE WHEN d.UnitPriceDiscount>0 THEN 1 ELSE 0 END) FROM Sales.SalesOrderDetail d JOIN Sales.SalesOrderHeader h ON h.SalesOrderID=d.SalesOrderID GROUP BY h.OnlineOrderFlag;
INSERT #e SELECT 'sod.lines_by_offer', CONCAT(d.SpecialOfferID,':',so.Description), COUNT(*) FROM Sales.SalesOrderDetail d JOIN Sales.SpecialOffer so ON so.SpecialOfferID=d.SpecialOfferID GROUP BY d.SpecialOfferID, so.Description;
INSERT #e SELECT 'sod.with_tracking', CASE h.OnlineOrderFlag WHEN 1 THEN 'internet' ELSE 'reseller' END, SUM(CASE WHEN d.CarrierTrackingNumber IS NULL THEN 0 ELSE 1 END) FROM Sales.SalesOrderDetail d JOIN Sales.SalesOrderHeader h ON h.SalesOrderID=d.SalesOrderID GROUP BY h.OnlineOrderFlag;
INSERT #e SELECT 'sales_reason.orders', r.Name, COUNT(*) FROM Sales.SalesOrderHeaderSalesReason x JOIN Sales.SalesReason r ON r.SalesReasonID=x.SalesReasonID GROUP BY r.Name;
INSERT #e SELECT 'cart.items', 'all', COUNT(*) FROM Sales.ShoppingCartItem;
INSERT #e SELECT 'creditcard.type', CardType, COUNT(*) FROM Sales.CreditCard GROUP BY CardType;
INSERT #e SELECT 'currencyrate.to', ToCurrencyCode, COUNT(*) FROM Sales.CurrencyRate GROUP BY ToCurrencyCode;
-- sales management
INSERT #e SELECT 'specialoffer.type_category', CONCAT(Type,':',Category), COUNT(*) FROM Sales.SpecialOffer GROUP BY Type, Category;
INSERT #e SELECT 'specialoffer.products', CONCAT(so.SpecialOfferID,':',so.Description), COUNT(*) FROM Sales.SpecialOfferProduct p JOIN Sales.SpecialOffer so ON so.SpecialOfferID=p.SpecialOfferID GROUP BY so.SpecialOfferID, so.Description;
INSERT #e SELECT 'quota.range', 'all', CONCAT(FORMAT(MIN(QuotaDate),@d),'..',FORMAT(MAX(QuotaDate),@d),' people=',COUNT(DISTINCT BusinessEntityID)) FROM Sales.SalesPersonQuotaHistory;
INSERT #e SELECT 'territoryhistory.ended', 'all', COUNT(*) FROM Sales.SalesTerritoryHistory WHERE EndDate IS NOT NULL;
INSERT #e SELECT 'salesperson.no_territory', 'all', COUNT(*) FROM Sales.SalesPerson WHERE TerritoryID IS NULL;
INSERT #e SELECT 'store.no_salesperson', 'all', COUNT(*) FROM Sales.Store WHERE SalesPersonID IS NULL;
INSERT #e SELECT 'store.with_orders', 'all', COUNT(DISTINCT c.StoreID) FROM Sales.Customer c JOIN Sales.SalesOrderHeader h ON h.CustomerID=c.CustomerID WHERE c.StoreID IS NOT NULL;
-- customer / person
INSERT #e SELECT 'customer.kind', CASE WHEN PersonID IS NOT NULL AND StoreID IS NOT NULL THEN 'store_contact' WHEN StoreID IS NOT NULL THEN 'store' ELSE 'person' END, COUNT(*) FROM Sales.Customer GROUP BY CASE WHEN PersonID IS NOT NULL AND StoreID IS NOT NULL THEN 'store_contact' WHEN StoreID IS NOT NULL THEN 'store' ELSE 'person' END;
INSERT #e SELECT 'customer.with_orders', 'all', COUNT(DISTINCT CustomerID) FROM Sales.SalesOrderHeader;
INSERT #e SELECT 'person.type', PersonType, COUNT(*) FROM Person.Person GROUP BY PersonType;
INSERT #e SELECT 'person.email_promotion', CAST(EmailPromotion AS varchar), COUNT(*) FROM Person.Person GROUP BY EmailPromotion;
INSERT #e SELECT 'person.with_demographics', 'all', COUNT(*) FROM Person.Person WHERE Demographics IS NOT NULL;
INSERT #e SELECT 'address.type', t.Name, COUNT(*) FROM Person.BusinessEntityAddress a JOIN Person.AddressType t ON t.AddressTypeID=a.AddressTypeID GROUP BY t.Name;
INSERT #e SELECT 'contact.type', t.Name, COUNT(*) FROM Person.BusinessEntityContact c JOIN Person.ContactType t ON t.ContactTypeID=c.ContactTypeID GROUP BY t.Name;
-- procure-to-pay
INSERT #e SELECT 'poh.status', CAST(Status AS varchar), COUNT(*) FROM Purchasing.PurchaseOrderHeader GROUP BY Status;
INSERT #e SELECT 'poh.revision', CAST(RevisionNumber AS varchar), COUNT(*) FROM Purchasing.PurchaseOrderHeader GROUP BY RevisionNumber;
INSERT #e SELECT 'poh.orderdate_range', 'all', CONCAT(FORMAT(MIN(OrderDate),@d),'..',FORMAT(MAX(OrderDate),@d)) FROM Purchasing.PurchaseOrderHeader;
INSERT #e SELECT 'poh.ship_minus_order_days', CAST(DATEDIFF(day,OrderDate,ShipDate) AS varchar), COUNT(*) FROM Purchasing.PurchaseOrderHeader GROUP BY DATEDIFF(day,OrderDate,ShipDate);
INSERT #e SELECT 'poh.buyers', 'distinct_employees', COUNT(DISTINCT EmployeeID) FROM Purchasing.PurchaseOrderHeader;
INSERT #e SELECT 'poh.buyer_titles', e.JobTitle, COUNT(*) FROM Purchasing.PurchaseOrderHeader h JOIN HumanResources.Employee e ON e.BusinessEntityID=h.EmployeeID GROUP BY e.JobTitle;
INSERT #e SELECT 'pod.receipt', CASE WHEN ReceivedQty=0 THEN 'none' WHEN ReceivedQty<OrderQty THEN 'partial' ELSE 'full' END, COUNT(*) FROM Purchasing.PurchaseOrderDetail GROUP BY CASE WHEN ReceivedQty=0 THEN 'none' WHEN ReceivedQty<OrderQty THEN 'partial' ELSE 'full' END;
INSERT #e SELECT 'pod.rejected_lines', 'all', COUNT(*) FROM Purchasing.PurchaseOrderDetail WHERE RejectedQty>0;
INSERT #e SELECT 'pod.qty', 'ordered/received/rejected/stocked', CONCAT(SUM(CAST(OrderQty AS bigint)),'/',CAST(SUM(ReceivedQty) AS bigint),'/',CAST(SUM(RejectedQty) AS bigint),'/',CAST(SUM(StockedQty) AS bigint)) FROM Purchasing.PurchaseOrderDetail;
INSERT #e SELECT 'pod.receipt_by_status', CONCAT(h.Status,':',CASE WHEN d.ReceivedQty=0 THEN 'none' WHEN d.ReceivedQty<d.OrderQty THEN 'partial' ELSE 'full' END), COUNT(*) FROM Purchasing.PurchaseOrderDetail d JOIN Purchasing.PurchaseOrderHeader h ON h.PurchaseOrderID=d.PurchaseOrderID GROUP BY h.Status, CASE WHEN d.ReceivedQty=0 THEN 'none' WHEN d.ReceivedQty<d.OrderQty THEN 'partial' ELSE 'full' END;
INSERT #e SELECT 'vendor.flags', CONCAT('active=',ActiveFlag,' preferred=',PreferredVendorStatus), COUNT(*) FROM Purchasing.Vendor GROUP BY ActiveFlag, PreferredVendorStatus;
INSERT #e SELECT 'vendor.credit_rating', CAST(CreditRating AS varchar), COUNT(*) FROM Purchasing.Vendor GROUP BY CreditRating;
INSERT #e SELECT 'vendor.with_pos', 'all', COUNT(DISTINCT VendorID) FROM Purchasing.PurchaseOrderHeader;
INSERT #e SELECT 'productvendor.products', 'distinct', COUNT(DISTINCT ProductID) FROM Purchasing.ProductVendor;
INSERT #e SELECT 'productvendor.on_order', 'with_OnOrderQty', COUNT(*) FROM Purchasing.ProductVendor WHERE OnOrderQty IS NOT NULL;
-- plan-to-produce
INSERT #e SELECT 'wo.state', CASE WHEN EndDate IS NULL THEN 'open' WHEN EndDate>DueDate THEN 'closed_late' ELSE 'closed_on_time' END, COUNT(*) FROM Production.WorkOrder GROUP BY CASE WHEN EndDate IS NULL THEN 'open' WHEN EndDate>DueDate THEN 'closed_late' ELSE 'closed_on_time' END;
INSERT #e SELECT 'wo.daterange', 'start', CONCAT(FORMAT(MIN(StartDate),@d),'..',FORMAT(MAX(StartDate),@d)) FROM Production.WorkOrder;
INSERT #e SELECT 'wo.with_scrap', 'all', COUNT(*) FROM Production.WorkOrder WHERE ScrappedQty>0;
INSERT #e SELECT 'wo.qty', 'ordered/stocked/scrapped', CONCAT(SUM(CAST(OrderQty AS bigint)),'/',SUM(CAST(StockedQty AS bigint)),'/',SUM(CAST(ScrappedQty AS bigint))) FROM Production.WorkOrder;
INSERT #e SELECT 'wo.scrap_reason', r.Name, COUNT(*) FROM Production.WorkOrder w JOIN Production.ScrapReason r ON r.ScrapReasonID=w.ScrapReasonID GROUP BY r.Name;
INSERT #e SELECT 'wo.with_routing', 'all', COUNT(DISTINCT WorkOrderID) FROM Production.WorkOrderRouting;
INSERT #e SELECT 'wo.products', 'distinct', COUNT(DISTINCT ProductID) FROM Production.WorkOrder;
INSERT #e SELECT 'wor.location', CONCAT(r.OperationSequence,':',l.Name), COUNT(*) FROM Production.WorkOrderRouting r JOIN Production.Location l ON l.LocationID=r.LocationID GROUP BY r.OperationSequence, l.Name;
INSERT #e SELECT 'wor.late_ops', 'ActualEndDate>ScheduledEndDate', COUNT(*) FROM Production.WorkOrderRouting WHERE ActualEndDate>ScheduledEndDate;
INSERT #e SELECT 'wor.cost', 'planned/actual', CONCAT(CAST(SUM(PlannedCost) AS bigint),'/',CAST(SUM(ActualCost) AS bigint)) FROM Production.WorkOrderRouting;
INSERT #e SELECT 'bom.level', CAST(BOMLevel AS varchar), COUNT(*) FROM Production.BillOfMaterials GROUP BY BOMLevel;
INSERT #e SELECT 'bom.ended', 'EndDate not null', COUNT(*) FROM Production.BillOfMaterials WHERE EndDate IS NOT NULL;
INSERT #e SELECT 'bom.assemblies', 'distinct', COUNT(DISTINCT ProductAssemblyID) FROM Production.BillOfMaterials;
INSERT #e SELECT 'location.costrate', CONCAT(LocationID,':',Name), CONCAT(CostRate,' / ',Availability) FROM Production.Location;
-- inventory
INSERT #e SELECT 'th.type', CONCAT('current:',TransactionType), COUNT(*) FROM Production.TransactionHistory GROUP BY TransactionType;
INSERT #e SELECT 'th.type', CONCAT('archive:',TransactionType), COUNT(*) FROM Production.TransactionHistoryArchive GROUP BY TransactionType;
INSERT #e SELECT 'th.daterange', 'current', CONCAT(FORMAT(MIN(TransactionDate),@d),'..',FORMAT(MAX(TransactionDate),@d)) FROM Production.TransactionHistory;
INSERT #e SELECT 'th.daterange', 'archive', CONCAT(FORMAT(MIN(TransactionDate),@d),'..',FORMAT(MAX(TransactionDate),@d)) FROM Production.TransactionHistoryArchive;
INSERT #e SELECT 'inv.by_location', l.Name, CONCAT(COUNT(*),' rows / ',SUM(i.Quantity),' units') FROM Production.ProductInventory i JOIN Production.Location l ON l.LocationID=i.LocationID GROUP BY l.Name;
INSERT #e SELECT 'inv.below_reorder', 'products', COUNT(*) FROM Production.Product p WHERE p.ReorderPoint > ISNULL((SELECT SUM(Quantity) FROM Production.ProductInventory i WHERE i.ProductID=p.ProductID),0) AND p.SellEndDate IS NULL;
INSERT #e SELECT 'inv.below_safety', 'products', COUNT(*) FROM Production.Product p WHERE p.SafetyStockLevel > ISNULL((SELECT SUM(Quantity) FROM Production.ProductInventory i WHERE i.ProductID=p.ProductID),0) AND p.SellEndDate IS NULL;
INSERT #e SELECT 'inv.products_with_stock', 'distinct', COUNT(DISTINCT ProductID) FROM Production.ProductInventory;
-- catalog
INSERT #e SELECT 'product.flags', CONCAT('make=',MakeFlag,' finished=',FinishedGoodsFlag), COUNT(*) FROM Production.Product GROUP BY MakeFlag, FinishedGoodsFlag;
INSERT #e SELECT 'product.lifecycle', CASE WHEN DiscontinuedDate IS NOT NULL THEN 'discontinued' WHEN SellEndDate IS NOT NULL THEN 'sell_ended' ELSE 'selling' END, COUNT(*) FROM Production.Product GROUP BY CASE WHEN DiscontinuedDate IS NOT NULL THEN 'discontinued' WHEN SellEndDate IS NOT NULL THEN 'sell_ended' ELSE 'selling' END;
INSERT #e SELECT 'product.sellstart_year', CAST(YEAR(SellStartDate) AS varchar), COUNT(*) FROM Production.Product GROUP BY YEAR(SellStartDate);
INSERT #e SELECT 'product.no_subcategory', 'all', COUNT(*) FROM Production.Product WHERE ProductSubcategoryID IS NULL;
INSERT #e SELECT 'pricehistory.versions', CAST(n AS varchar), COUNT(*) FROM (SELECT ProductID, COUNT(*) n FROM Production.ProductListPriceHistory GROUP BY ProductID) x GROUP BY n;
INSERT #e SELECT 'costhistory.versions', CAST(n AS varchar), COUNT(*) FROM (SELECT ProductID, COUNT(*) n FROM Production.ProductCostHistory GROUP BY ProductID) x GROUP BY n;
INSERT #e SELECT 'document.status', CAST(Status AS varchar), COUNT(*) FROM Production.Document GROUP BY Status;
INSERT #e SELECT 'photo.nonplaceholder_products', 'all', COUNT(*) FROM Production.ProductProductPhoto WHERE ProductPhotoID<>1;
-- reviews / returns
INSERT #e SELECT 'review.rating', CAST(Rating AS varchar), COUNT(*) FROM Production.ProductReview GROUP BY Rating;
INSERT #e SELECT 'returns.tables', 'Sales/Production return or RMA tables', COUNT(*) FROM sys.tables WHERE name LIKE '%Return%' OR name LIKE '%RMA%' OR name LIKE '%Refund%' OR name LIKE '%Credit%Memo%';
INSERT #e SELECT 'returns.dw_finance_accounts', 'DimAccount like return', COUNT(*) FROM AdventureWorksDW2022.dbo.DimAccount WHERE AccountDescription LIKE '%Return%';
-- HR
INSERT #e SELECT 'emp.flags', CONCAT('current=',CurrentFlag,' salaried=',SalariedFlag), COUNT(*) FROM HumanResources.Employee GROUP BY CurrentFlag, SalariedFlag;
INSERT #e SELECT 'emp.org_level', ISNULL(CAST(OrganizationLevel AS varchar),'null'), COUNT(*) FROM HumanResources.Employee GROUP BY OrganizationLevel;
INSERT #e SELECT 'emp.hire_range', 'all', CONCAT(FORMAT(MIN(HireDate),@d),'..',FORMAT(MAX(HireDate),@d)) FROM HumanResources.Employee;
INSERT #e SELECT 'emp.hires_by_year', CAST(YEAR(HireDate) AS varchar), COUNT(*) FROM HumanResources.Employee GROUP BY YEAR(HireDate);
INSERT #e SELECT 'edh.assignments_per_emp', CAST(n AS varchar), COUNT(*) FROM (SELECT BusinessEntityID, COUNT(*) n FROM HumanResources.EmployeeDepartmentHistory GROUP BY BusinessEntityID) x GROUP BY n;
INSERT #e SELECT 'edh.ended', 'EndDate not null', COUNT(*) FROM HumanResources.EmployeeDepartmentHistory WHERE EndDate IS NOT NULL;
INSERT #e SELECT 'edh.current_by_shift', s.Name, COUNT(*) FROM HumanResources.EmployeeDepartmentHistory h JOIN HumanResources.Shift s ON s.ShiftID=h.ShiftID WHERE h.EndDate IS NULL GROUP BY s.Name;
INSERT #e SELECT 'edh.current_by_group', d.GroupName, COUNT(*) FROM HumanResources.EmployeeDepartmentHistory h JOIN HumanResources.Department d ON d.DepartmentID=h.DepartmentID WHERE h.EndDate IS NULL GROUP BY d.GroupName;
INSERT #e SELECT 'eph.rates_per_emp', CAST(n AS varchar), COUNT(*) FROM (SELECT BusinessEntityID, COUNT(*) n FROM HumanResources.EmployeePayHistory GROUP BY BusinessEntityID) x GROUP BY n;
INSERT #e SELECT 'eph.frequency', CAST(PayFrequency AS varchar), COUNT(*) FROM HumanResources.EmployeePayHistory GROUP BY PayFrequency;
INSERT #e SELECT 'jobcandidate.hired', CASE WHEN BusinessEntityID IS NULL THEN 'applicant' ELSE 'linked_to_employee' END, COUNT(*) FROM HumanResources.JobCandidate GROUP BY CASE WHEN BusinessEntityID IS NULL THEN 'applicant' ELSE 'linked_to_employee' END;
SELECT m, k, v FROM #e ORDER BY m, k;
