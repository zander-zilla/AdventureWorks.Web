#!/usr/bin/env python3
"""Static carry-over from AdventureWorksDW2022 (decision 3) + reconciliation reference copy.

  --out DIR     write <schema>.<table>.csv.gz for every static table (the files you upload to S3 for Redshift COPY)
  --ddl         regenerate warehouse/sql/star/05_static_ddl.sql and warehouse/sql/redshift/40_static_copy.sql (committed)
  --pg          also load them into the Postgres stand-in (schemas dw_static and, for reconciliation only, ref)

dw_static: the 10 no-OLTP-source DW tables (copied verbatim, snake_case columns) + localised-name lookups (loc_*).
ref:       reference copies of the DW tables we rebuild, used only by warehouse/local/reconcile.py (never shipped to Redshift).
CSV convention: NULL = \\N (unquoted), booleans true/false, timestamps ISO."""
import argparse, csv, datetime, decimal, gzip, io, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts/loader"))
sys.path.insert(0, os.path.dirname(__file__))
import sqlsrc

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
STATIC = ["FactFinance", "DimAccount", "DimOrganization", "DimDepartmentGroup", "DimScenario", "FactCallCenter", "FactSurveyResponse",
          "FactAdditionalInternationalProductDescription", "NewFactCurrencyRate", "ProspectiveBuyer"]
LOC = {  # localised names that have no OLTP source (decision 3), as small lookup tables
    "loc_product_category": "SELECT ProductCategoryAlternateKey AS alternate_key, SpanishProductCategoryName AS spanish_name, FrenchProductCategoryName AS french_name FROM DimProductCategory",
    "loc_product_subcategory": "SELECT ProductSubcategoryAlternateKey AS alternate_key, SpanishProductSubcategoryName AS spanish_name, FrenchProductSubcategoryName AS french_name FROM DimProductSubcategory",
    "loc_promotion": "SELECT PromotionAlternateKey AS alternate_key, SpanishPromotionName AS spanish_name, FrenchPromotionName AS french_name, SpanishPromotionType AS spanish_type, FrenchPromotionType AS french_type, SpanishPromotionCategory AS spanish_category, FrenchPromotionCategory AS french_category FROM DimPromotion",
    "loc_country": "SELECT DISTINCT CountryRegionCode AS country_region_code, SpanishCountryRegionName AS spanish_name, FrenchCountryRegionName AS french_name FROM DimGeography",
    "loc_product_name": "SELECT ProductAlternateKey AS product_alternate_key, MAX(SpanishProductName) AS spanish_name, MAX(FrenchProductName) AS french_name FROM DimProduct GROUP BY ProductAlternateKey",
}
REF = ["DimDate", "DimCustomer", "DimGeography", "DimReseller", "DimProduct", "DimProductCategory", "DimProductSubcategory", "DimPromotion",
       "DimSalesTerritory", "DimEmployee", "DimCurrency", "DimSalesReason", "FactInternetSales", "FactResellerSales",
       "FactInternetSalesReason", "FactSalesQuota", "FactCurrencyRate"]
SKIP_TYPES = {"varbinary", "image", "binary", "hierarchyid", "geography"}

def snake(n):
    n = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", n); return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", n).lower()

def coltype(t, length, prec, scale):
    if t in ("int",): return "integer"
    if t in ("smallint", "tinyint"): return "smallint"
    if t == "bigint": return "bigint"
    if t == "bit": return "boolean"
    if t in ("money", "smallmoney"): return "decimal(19,4)"
    if t in ("decimal", "numeric"): return "decimal(%d,%d)" % (prec, scale)
    if t == "float": return "double precision"
    if t == "real": return "real"
    if t == "date": return "date"
    if t in ("datetime", "datetime2", "smalldatetime"): return "timestamp"
    if t in ("nvarchar", "nchar"): return "varchar(%d)" % (65535 if length == -1 else min(65535, length // 2 * 3 or 3))
    if t in ("varchar", "char"): return "varchar(%d)" % (65535 if length == -1 else max(1, length))
    if t == "uniqueidentifier": return "varchar(36)"
    return "varchar(65535)"

def columns(conn, table):
    cur = conn.cursor()
    cur.execute("""SELECT c.name, ty.name AS t, c.max_length, c.precision, c.scale FROM sys.columns c JOIN sys.types ty ON ty.user_type_id = c.user_type_id
                   WHERE c.object_id = OBJECT_ID(%s) ORDER BY c.column_id""", ("dbo." + table,))
    return [(r["name"], snake(r["name"]), coltype(r["t"], r["max_length"], r["precision"], r["scale"])) for r in cur.fetchall() if r["t"] not in SKIP_TYPES]

def cell(v):
    if v is None: return "\\N"
    if isinstance(v, bool): return "true" if v else "false"
    if isinstance(v, (datetime.datetime, datetime.date)): return v.isoformat(sep=" ") if isinstance(v, datetime.datetime) else v.isoformat()
    if isinstance(v, decimal.Decimal): return format(v, "f")
    return str(v)

def dump(conn, query, out_path):
    cur = conn.cursor(); cur.execute(query); n = 0; cols = None
    with gzip.open(out_path, "wt", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        for r in cur:
            cols = cols or list(r.keys()); w.writerow([cell(r[c]) for c in cols]); n += 1
    return n

def specs(conn):
    """[(schema, name, select, [(snake, type)], shipped)]"""
    out = []
    for t in STATIC:
        cols = columns(conn, t)
        out.append(("dw_static", snake(t), "SELECT %s FROM dbo.[%s]" % (", ".join("[%s]" % c[0] for c in cols), t), [(c[1], c[2]) for c in cols], True))
    for name, q in LOC.items():
        cur = conn.cursor(); cur.execute("SELECT TOP 0 * FROM (%s) x" % q); cols = [d[0] for d in cur.description]
        out.append(("dw_static", name, q, [(c, "integer" if c == "alternate_key" else "varchar(150)") for c in cols], True))
    for t in REF:
        cols = columns(conn, t)
        out.append(("ref", snake(t), "SELECT %s FROM dbo.[%s]" % (", ".join("[%s]" % c[0] for c in cols), t), [(c[1], c[2]) for c in cols], False))
    return out

def ddl(schema, name, cols):
    return "DROP TABLE IF EXISTS %s.%s;\nCREATE TABLE %s.%s (\n  %s);\n" % (schema, name, schema, name, ",\n  ".join('"%s" %s' % c for c in cols))

def write_ddl(sp):
    hdr = "-- GENERATED by warehouse/local/static_export.py --ddl from AdventureWorksDW2022 - do not edit.\n"
    body = [hdr + "-- Static carry-over (decision 3): DW tables with no OLTP source + localised-name lookups. PORTABLE SQL.\nCREATE SCHEMA IF NOT EXISTS dw_static;\n"]
    body += [ddl(s, n, c) for s, n, q, c, ship in sp if ship]
    open(os.path.join(ROOT, "warehouse/sql/star/05_static_ddl.sql"), "w").write("\n".join(body))
    cp = [hdr + "-- One-time static load into Redshift: upload the CSVs written by `static_export.py --out` to\n"
          "-- s3://${static_bucket}/static/ (terraform output static_bucket) and run this after 05_static_ddl.sql.\n"]
    cp += ["COPY dw_static.%s FROM 's3://${static_bucket}/static/dw_static.%s.csv.gz'\n  IAM_ROLE '${copy_role_arn}' FORMAT AS CSV GZIP NULL AS '\\\\N' TIMEFORMAT 'auto' DATEFORMAT 'auto';\n" % (n, n)
           for s, n, q, c, ship in sp if ship]
    open(os.path.join(ROOT, "warehouse/sql/redshift/40_static_copy.sql"), "w").write("\n".join(cp))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="/tmp/aw-static"); ap.add_argument("--ddl", action="store_true")
    ap.add_argument("--pg", action="store_true"); a = ap.parse_args()
    conn = sqlsrc.connect("AdventureWorksDW2022"); sp = specs(conn)
    if a.ddl:
        write_ddl(sp)
    os.makedirs(a.out, exist_ok=True)
    pgc = None
    if a.pg:
        import pg
        pgc = pg.connect(); cur = pgc.cursor(); cur.execute("CREATE SCHEMA IF NOT EXISTS dw_static; CREATE SCHEMA IF NOT EXISTS ref")
    for s, n, q, cols, ship in sp:
        path = os.path.join(a.out, "%s.%s.csv.gz" % (s, n)); rows = dump(conn, q, path)
        if pgc:
            cur.execute(ddl(s, n, cols))
            with gzip.open(path, "rt") as f:
                cur.copy_expert("COPY %s.%s FROM STDIN WITH (FORMAT csv, NULL '\\N')" % (s, n), f)
            pgc.commit()
        print("%-10s %-48s %8d rows" % (s, n, rows), flush=True)

if __name__ == "__main__":
    main()
