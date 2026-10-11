-- Enable Change Data Capture on AdventureWorks2022 (OLTP) for sales/customer/product tables.
-- Requires SQL Server Agent (MSSQL_AGENT_ENABLED=true) for the capture/cleanup jobs.
-- Also enabled on AdventureWorksLT2022 because the 'before' app writes there (demo logins/orders).
SET NOCOUNT ON;
USE AdventureWorks2022;
IF (SELECT is_cdc_enabled FROM sys.databases WHERE name = DB_NAME()) = 0 EXEC sys.sp_cdc_enable_db;
DECLARE @t TABLE (s sysname, n sysname);
INSERT @t VALUES
 (N'Sales',N'SalesOrderHeader'),(N'Sales',N'SalesOrderDetail'),(N'Sales',N'Customer'),(N'Sales',N'Store'),
 (N'Sales',N'SpecialOfferProduct'),(N'Sales',N'ShoppingCartItem'),(N'Sales',N'CreditCard'),(N'Sales',N'PersonCreditCard'),
 (N'Person',N'Person'),(N'Person',N'Address'),(N'Person',N'BusinessEntityAddress'),(N'Person',N'EmailAddress'),(N'Person',N'PersonPhone'),
 (N'Production',N'Product'),(N'Production',N'ProductCategory'),(N'Production',N'ProductSubcategory'),(N'Production',N'ProductModel'),
 (N'Production',N'ProductInventory'),(N'Production',N'ProductListPriceHistory'),(N'Production',N'ProductReview');
DECLARE @s sysname, @n sysname;
DECLARE c CURSOR LOCAL FAST_FORWARD FOR SELECT s, n FROM @t;
OPEN c; FETCH NEXT FROM c INTO @s, @n;
WHILE @@FETCH_STATUS = 0
BEGIN
  IF NOT EXISTS (SELECT 1 FROM cdc.change_tables WHERE source_object_id = OBJECT_ID(QUOTENAME(@s)+N'.'+QUOTENAME(@n)))
    EXEC sys.sp_cdc_enable_table @source_schema=@s, @source_name=@n, @role_name=NULL, @supports_net_changes=1;
  FETCH NEXT FROM c INTO @s, @n;
END
CLOSE c; DEALLOCATE c;
GO
USE AdventureWorksLT2022;
IF (SELECT is_cdc_enabled FROM sys.databases WHERE name = DB_NAME()) = 0 EXEC sys.sp_cdc_enable_db;
DECLARE @n sysname;
DECLARE c CURSOR LOCAL FAST_FORWARD FOR SELECT v FROM (VALUES (N'Customer'),(N'SalesOrderHeader'),(N'SalesOrderDetail'),(N'Product')) x(v);
OPEN c; FETCH NEXT FROM c INTO @n;
WHILE @@FETCH_STATUS = 0
BEGIN
  IF NOT EXISTS (SELECT 1 FROM cdc.change_tables WHERE source_object_id = OBJECT_ID(N'SalesLT.'+QUOTENAME(@n)))
    EXEC sys.sp_cdc_enable_table @source_schema=N'SalesLT', @source_name=@n, @role_name=NULL, @supports_net_changes=1;
  FETCH NEXT FROM c INTO @n;
END
CLOSE c; DEALLOCATE c;
GO
SELECT N'AdventureWorks2022' db, s.name + '.' + t.name AS tracked FROM AdventureWorks2022.cdc.change_tables ct
  JOIN AdventureWorks2022.sys.tables t ON t.object_id = ct.source_object_id JOIN AdventureWorks2022.sys.schemas s ON s.schema_id=t.schema_id;
