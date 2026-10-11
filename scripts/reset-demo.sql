-- BEFORE BASELINE: remove orders created through the demo login (Comment = 'demo-order').
-- Safe to re-run. Run against AdventureWorksLT2022. CDC will capture these deletes too.
USE AdventureWorksLT2022;
SET NOCOUNT ON;
SET QUOTED_IDENTIFIER ON;
BEGIN TRAN;
DELETE d FROM SalesLT.SalesOrderDetail d JOIN SalesLT.SalesOrderHeader h ON h.SalesOrderID = d.SalesOrderID WHERE h.Comment = N'demo-order';
DELETE FROM SalesLT.SalesOrderHeader WHERE Comment = N'demo-order';
COMMIT;
SELECT COUNT(*) AS remaining_demo_orders FROM SalesLT.SalesOrderHeader WHERE Comment = N'demo-order';
