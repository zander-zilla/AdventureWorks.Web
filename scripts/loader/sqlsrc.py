"""SQL Server access for the loader/tests (pymssql)."""
import os, pymssql

def connect(db="AdventureWorks2022"):
    return pymssql.connect(server=os.environ.get("SQL_HOST", "localhost"), port=int(os.environ.get("SQL_PORT", "1433")),
                           user=os.environ.get("SQL_USER", "sa"), password=os.environ.get("MSSQL_SA_PASSWORD", "AdvWorks!2026"),
                           database=db, as_dict=True)

def primary_key(conn, table):
    s, t = table.split(".")
    cur = conn.cursor()
    cur.execute("""SELECT c.name FROM sys.indexes i JOIN sys.index_columns ic ON ic.object_id=i.object_id AND ic.index_id=i.index_id
                   JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id
                   WHERE i.is_primary_key=1 AND i.object_id=OBJECT_ID(%s) ORDER BY ic.key_ordinal""", ("%s.%s" % (s, t),))
    return [r["name"] for r in cur.fetchall()]

def source_query(table, src):
    if src.get("source_sql"):
        return src["source_sql"]
    # hierarchyid/geography columns would arrive as raw bytes: callers omit them via 'omit' + source_sql
    return "SELECT * FROM %s" % table
