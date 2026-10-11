-- Restore the three official AdventureWorks 2022 backups (idempotent).
SET NOCOUNT ON;
DECLARE @dbs TABLE (db sysname, bak nvarchar(260));
INSERT @dbs VALUES (N'AdventureWorksLT2022', N'/var/opt/mssql/backup/AdventureWorksLT2022.bak'),
                   (N'AdventureWorks2022',   N'/var/opt/mssql/backup/AdventureWorks2022.bak'),
                   (N'AdventureWorksDW2022', N'/var/opt/mssql/backup/AdventureWorksDW2022.bak');
DECLARE @db sysname, @bak nvarchar(260), @sql nvarchar(max);
DECLARE c CURSOR LOCAL FAST_FORWARD FOR SELECT db, bak FROM @dbs;
OPEN c; FETCH NEXT FROM c INTO @db, @bak;
WHILE @@FETCH_STATUS = 0
BEGIN
  IF DB_ID(@db) IS NULL
  BEGIN
    DECLARE @files TABLE (LogicalName sysname, PhysicalName nvarchar(260), [Type] char(1), FileGroupName sysname NULL,
      Size numeric(20,0), MaxSize numeric(20,0), FileId bigint, CreateLSN numeric(25,0), DropLSN numeric(25,0) NULL,
      UniqueId uniqueidentifier, ReadOnlyLSN numeric(25,0) NULL, ReadWriteLSN numeric(25,0) NULL, BackupSizeInBytes bigint,
      SourceBlockSize int, FileGroupId int, LogGroupGUID uniqueidentifier NULL, DifferentialBaseLSN numeric(25,0) NULL,
      DifferentialBaseGUID uniqueidentifier NULL, IsReadOnly bit, IsPresent bit, TDEThumbprint varbinary(32) NULL, SnapshotUrl nvarchar(360) NULL);
    DELETE FROM @files;
    INSERT @files EXEC (N'RESTORE FILELISTONLY FROM DISK = N''' + @bak + N'''');
    SELECT @sql = N'RESTORE DATABASE [' + @db + N'] FROM DISK = N''' + @bak + N''' WITH REPLACE'
      + STRING_AGG(CONVERT(nvarchar(max), N', MOVE N''' + LogicalName + N''' TO N''/var/opt/mssql/data/' + @db + N'_' + LogicalName
      + CASE [Type] WHEN 'L' THEN N'.ldf' ELSE N'.mdf' END + N''''), N'')
    FROM @files;
    PRINT @sql; EXEC (@sql);
  END
  FETCH NEXT FROM c INTO @db, @bak;
END
CLOSE c; DEALLOCATE c;
SELECT name, state_desc FROM sys.databases WHERE name LIKE N'AdventureWorks%';
