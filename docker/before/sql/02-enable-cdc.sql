-- Enable Change Data Capture on AdventureWorks2022 (OLTP): all business tables.
-- Requires SQL Server Agent (MSSQL_AGENT_ENABLED=true) for the capture/cleanup jobs.
-- Also enabled on AdventureWorksLT2022 for the original CRUD screens (which still use LT); demo orders go to AdventureWorks2022.
SET NOCOUNT ON;
USE AdventureWorks2022;
IF (SELECT is_cdc_enabled FROM sys.databases WHERE name = DB_NAME()) = 0 EXEC sys.sp_cdc_enable_db;
-- ALL user tables in HumanResources, Person, Production, Purchasing, Sales (68 tables).
-- Excluded: dbo housekeeping (AWBuildVersion, DatabaseLog, ErrorLog) - not business data; DatabaseLog is
-- written by the DDL trigger (including by CDC's own DDL), so capturing it would be noise.
-- Every included table has a primary key, so all use @supports_net_changes = 1 (checked below; a table
-- without a PK falls back to @supports_net_changes = 0 and is reported).
DECLARE @s sysname, @n sysname, @haspk bit;
DECLARE c CURSOR LOCAL FAST_FORWARD FOR
  SELECT s.name, t.name,
         CASE WHEN EXISTS (SELECT 1 FROM sys.indexes i WHERE i.object_id = t.object_id AND i.is_primary_key = 1) THEN 1 ELSE 0 END
    FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id
   WHERE t.is_ms_shipped = 0 AND s.name IN (N'HumanResources', N'Person', N'Production', N'Purchasing', N'Sales')
   ORDER BY s.name, t.name;
OPEN c; FETCH NEXT FROM c INTO @s, @n, @haspk;
WHILE @@FETCH_STATUS = 0
BEGIN
  IF NOT EXISTS (SELECT 1 FROM cdc.change_tables WHERE source_object_id = OBJECT_ID(QUOTENAME(@s)+N'.'+QUOTENAME(@n)))
  BEGIN
    IF @haspk = 0 PRINT N'WARNING: no primary key, net changes disabled: ' + @s + N'.' + @n;
    EXEC sys.sp_cdc_enable_table @source_schema=@s, @source_name=@n, @role_name=NULL, @supports_net_changes=@haspk;
  END
  FETCH NEXT FROM c INTO @s, @n, @haspk;
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
SELECT COUNT(*) AS cdc_tracked_tables_oltp FROM AdventureWorks2022.cdc.change_tables;
SELECT COUNT(*) AS cdc_tracked_tables_lt FROM AdventureWorksLT2022.cdc.change_tables;
GO
-- CDC retention 7 days (decision P4-4, same as on RDS): cleanup job keeps 10080 minutes of change data.
USE AdventureWorks2022;
EXEC sys.sp_cdc_change_job @job_type = N'cleanup', @retention = 10080;
SELECT job_type, retention FROM msdb.dbo.cdc_jobs WHERE database_id = DB_ID();
