-- Emits a JSON document describing the current database's schema (run per database).
SET NOCOUNT ON;
SELECT
  DB_NAME() AS [database],
  (SELECT s.name AS [schema], t.name AS [table],
     (SELECT SUM(p.rows) FROM sys.partitions p WHERE p.object_id = t.object_id AND p.index_id IN (0,1)) AS row_count,
     (SELECT c.name, TYPE_NAME(c.user_type_id) AS type,
             CASE WHEN TYPE_NAME(c.user_type_id) IN ('nvarchar','nchar') AND c.max_length > 0 THEN c.max_length/2 ELSE c.max_length END AS max_length,
             c.precision, c.scale, c.is_nullable AS nullable, c.is_identity AS [identity], c.is_computed AS computed,
             cc.definition AS computed_definition, dc.definition AS [default]
        FROM sys.columns c
        LEFT JOIN sys.computed_columns cc ON cc.object_id = c.object_id AND cc.column_id = c.column_id
        LEFT JOIN sys.default_constraints dc ON dc.object_id = c.default_object_id
       WHERE c.object_id = t.object_id ORDER BY c.column_id FOR JSON PATH) AS columns,
     (SELECT c.name FROM sys.indexes i JOIN sys.index_columns ic ON ic.object_id=i.object_id AND ic.index_id=i.index_id
        JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id
       WHERE i.object_id = t.object_id AND i.is_primary_key = 1 ORDER BY ic.key_ordinal FOR JSON PATH) AS primary_key,
     (SELECT fk.name, SCHEMA_NAME(rt.schema_id) AS ref_schema, rt.name AS ref_table,
             (SELECT pc.name AS col, rc.name AS ref_col FROM sys.foreign_key_columns fkc
                JOIN sys.columns pc ON pc.object_id=fkc.parent_object_id AND pc.column_id=fkc.parent_column_id
                JOIN sys.columns rc ON rc.object_id=fkc.referenced_object_id AND rc.column_id=fkc.referenced_column_id
               WHERE fkc.constraint_object_id = fk.object_id ORDER BY fkc.constraint_column_id FOR JSON PATH) AS columns
        FROM sys.foreign_keys fk JOIN sys.tables rt ON rt.object_id = fk.referenced_object_id
       WHERE fk.parent_object_id = t.object_id FOR JSON PATH) AS foreign_keys,
     (SELECT i.name, i.type_desc AS type, i.is_unique AS [unique], i.is_primary_key AS [primary_key], i.filter_definition AS filter,
             (SELECT c.name + CASE WHEN ic.is_descending_key=1 THEN ' DESC' ELSE '' END AS col, ic.is_included_column AS included
                FROM sys.index_columns ic JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id
               WHERE ic.object_id=i.object_id AND ic.index_id=i.index_id ORDER BY ic.is_included_column, ic.key_ordinal FOR JSON PATH) AS columns
        FROM sys.indexes i WHERE i.object_id = t.object_id AND i.type > 0 FOR JSON PATH) AS indexes,
     (SELECT tr.name, tr.is_instead_of_trigger AS instead_of FROM sys.triggers tr WHERE tr.parent_id = t.object_id FOR JSON PATH) AS triggers
   FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id
   WHERE t.is_ms_shipped = 0 AND s.name NOT IN ('cdc') AND t.name NOT IN ('systranschemas','sysdiagrams')
   ORDER BY s.name, t.name FOR JSON PATH) AS tables,
  (SELECT SCHEMA_NAME(o.schema_id) AS [schema], o.name, o.type_desc AS type,
          (SELECT DISTINCT d.referenced_schema_name AS [schema], d.referenced_entity_name AS name
             FROM sys.sql_expression_dependencies d WHERE d.referencing_id = o.object_id AND d.referenced_entity_name IS NOT NULL FOR JSON PATH) AS references_
     FROM sys.objects o
    WHERE o.is_ms_shipped = 0 AND o.type IN ('V','P','FN','IF','TF') AND SCHEMA_NAME(o.schema_id) NOT IN ('cdc')
    ORDER BY o.type, SCHEMA_NAME(o.schema_id), o.name FOR JSON PATH) AS modules,
  (SELECT tr.name, OBJECT_SCHEMA_NAME(tr.parent_id) AS [schema], OBJECT_NAME(tr.parent_id) AS [table], tr.parent_class_desc AS scope
     FROM sys.triggers tr WHERE tr.is_ms_shipped = 0 AND tr.name NOT LIKE 'tr_MScdc%' FOR JSON PATH) AS triggers
FOR JSON PATH, WITHOUT_ARRAY_WRAPPER;
