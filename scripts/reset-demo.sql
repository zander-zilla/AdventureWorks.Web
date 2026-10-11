-- BEFORE BASELINE: remove orders created through the demo login (Comment = 'demo-order').
-- Demo orders live in the FULL AdventureWorks2022 database. Safe to re-run; CDC captures the deletes too.
SET NOCOUNT ON;
SET QUOTED_IDENTIFIER ON;
USE AdventureWorks2022;
BEGIN TRAN;
-- The SalesOrderDetail trigger also logs a Production.TransactionHistory row (type 'S') per demo line.
-- Demo orders get ids above the restored max (75123); also removes rows orphaned by older resets.
DELETE th FROM Production.TransactionHistory th
 WHERE th.TransactionType = 'S' AND th.ReferenceOrderID > 75123
   AND (th.ReferenceOrderID IN (SELECT SalesOrderID FROM Sales.SalesOrderHeader WHERE Comment = N'demo-order')
        OR NOT EXISTS (SELECT 1 FROM Sales.SalesOrderHeader h WHERE h.SalesOrderID = th.ReferenceOrderID));
DELETE r FROM Sales.SalesOrderHeaderSalesReason r JOIN Sales.SalesOrderHeader h ON h.SalesOrderID = r.SalesOrderID WHERE h.Comment = N'demo-order';
DELETE d FROM Sales.SalesOrderDetail d JOIN Sales.SalesOrderHeader h ON h.SalesOrderID = d.SalesOrderID WHERE h.Comment = N'demo-order';
DELETE FROM Sales.SalesOrderHeader WHERE Comment = N'demo-order';
COMMIT;
SELECT COUNT(*) AS remaining_demo_orders FROM Sales.SalesOrderHeader WHERE Comment = N'demo-order';
-- Legacy: orders created by earlier builds of the demo in AdventureWorksLT2022.
USE AdventureWorksLT2022;
DELETE d FROM SalesLT.SalesOrderDetail d JOIN SalesLT.SalesOrderHeader h ON h.SalesOrderID = d.SalesOrderID WHERE h.Comment = N'demo-order';
DELETE FROM SalesLT.SalesOrderHeader WHERE Comment = N'demo-order';
