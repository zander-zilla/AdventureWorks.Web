#!/usr/bin/env python3
"""Generate the typed staging layer (one view per DynamoDB entity type) over the zero-ETL landing tables.

The zero-ETL landing shape (Redshift): one table per DynamoDB table, columns "PK", "SK" and `value` SUPER holding the
item in DynamoDB JSON ({"attr": {"S": ...}}). The local Postgres stand-in uses the same shape with `value jsonb`.
Everything above this layer (warehouse/sql/star/*.sql) is dialect-portable SQL over these views.

Generated files (CI checks they are in sync):
  warehouse/sql/redshift/10_staging_views.sql   warehouse/sql/postgres/10_staging_views.sql   (from design/mapping/mapping.json)
  warehouse/sql/star/20_build_procedure.sql     dw.sp_build_star(): 02_dims.sql + 03_facts.sql wrapped in one procedure,
                                                 valid PL/pgSQL on both Redshift and Postgres (CI runs it on Postgres)
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TYPES = {"int": "integer", "smallint": "integer", "tinyint": "integer", "bigint": "bigint", "bit": "boolean",
         "money": "decimal(19,4)", "smallmoney": "decimal(19,4)", "numeric": "decimal(38,6)", "decimal": "decimal(38,6)",
         "float": "double precision", "real": "double precision", "datetime": "timestamp", "datetime2": "timestamp",
         "smalldatetime": "timestamp", "date": "date", "uniqueidentifier": "varchar(36)",
         "Flag": "boolean", "NameStyle": "boolean", "time": "varchar(16)"}  # Flag/NameStyle are AW user types over bit
SKIP_SQL_TYPES = {"varbinary", "image", "xml", "hierarchyid", "geography", "binary"}  # never needed by the star schema
# derived (snapshot/helper) attributes that are not plain strings
DERIVED_TYPES = {"category_id": "integer", "stock_qty": "integer", "currency_average_rate": "decimal(19,4)", "discount_pct": "decimal(19,4)",
                 "min_qty": "integer", "max_qty": "integer", "offer_start": "timestamp", "offer_end": "timestamp",
                 "latitude": "double precision", "longitude": "double precision", "exp_month": "integer", "exp_year": "integer"}
EXTRA_TYPES = {"archived": "boolean"}
# xml_map attributes flattened to columns (keys as written by the loader's xml_map transform)
FLATTEN = {
    "Person": ("demographics", ["total_purchase_ytd", "date_first_purchase", "birth_date", "marital_status", "yearly_income", "gender",
                                "total_children", "number_children_at_home", "education", "occupation", "home_owner_flag",
                                "number_cars_owned", "commute_distance"]),
    "Store": ("demographics", ["annual_sales", "annual_revenue", "bank_name", "business_type", "year_opened", "specialty",
                               "square_feet", "brands", "internet", "number_employees"]),
}
# "varchar" is an artefact of expand_mapping parsing CAST(... AS varchar(10)) in Sales.Customer source_sql, not a real attribute
SKIP_ATTRS = {"varchar"}
META = [("type", "varchar(64)"), ("src", "varchar(8)"), ("updated_at", "varchar(32)")]

def snake(name):
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()

def entities(m):
    out = {}
    for src_name, s in m["sources"].items():
        cols = {c["attribute"]: c for c in s["columns"] if c["attribute"]}
        for it in s["items"]:
            key = (it["table"], it["entity"])
            e = out.setdefault(key, {"table": it["table"], "entity": it["entity"], "sources": [], "cols": {}})
            e["sources"].append(src_name)
            names = it.get("attribute_list") or (list(cols) + list(s.get("derived_attributes", [])))
            for a in names:
                if a in SKIP_ATTRS:
                    continue
                if a in cols:
                    c = cols[a]
                    if c["sql_type"] in SKIP_SQL_TYPES:
                        continue
                    t = TYPES.get(c["sql_type"], "varchar(65535)")
                else:
                    t = DERIVED_TYPES.get(a, "varchar(65535)")
                e["cols"].setdefault(a, t)
            for a in (it.get("extra") or {}):
                e["cols"].setdefault(a, EXTRA_TYPES.get(a, "varchar(256)"))
    return out

def dyn_key(t):
    if t == "boolean":
        return "BOOL"
    if t.startswith(("integer", "bigint", "decimal", "double")):
        return "N"
    return "S"

def expr(dialect, path, t):
    """path: list of attribute names (nested map path). Returns a typed scalar expression."""
    k = dyn_key(t)
    if dialect == "postgres":
        base = "value" + "".join("->'%s'->'M'" % p for p in path[:-1]) + "->'%s'" % path[-1]
        if k == "BOOL":
            return "(%s->>'BOOL')::boolean" % base
        raw = "COALESCE(%s->>'%s', %s->>'%s')" % (base, k, base, "S" if k == "N" else "N")
        return "NULLIF(%s, '')::%s" % (raw, t) if t != "varchar(65535)" and not t.startswith("varchar") else "%s::%s" % (raw, t)
    base = "value" + "".join('."%s"."M"' % p for p in path[:-1]) + '."%s"' % path[-1]
    if k == "BOOL":
        return '%s."BOOL"::boolean' % base
    raw = 'COALESCE(%s."%s"::varchar, %s."%s"::varchar)' % (base, k, base, "S" if k == "N" else "N")
    return ("CAST(NULLIF(%s, '') AS %s)" % (raw, t)) if not t.startswith("varchar") else "%s::%s" % (raw, t)

def landing(dialect, table):
    # Redshift: every DynamoDB zero-ETL integration has exactly one source table and lands in its own database created with
    # CREATE DATABASE aw_zetl_<domain> FROM INTEGRATION ... (warehouse/sql/redshift/00_setup.sql); read with 3-part names.
    if dialect == "postgres":
        return 'landing."%s"' % table
    return 'aw_zetl_%s.public."%s"' % (table.replace("aw-", ""), table)

def view_sql(dialect, e):
    cols = ['"PK"::varchar(2048) AS pk', '"SK"::varchar(2048) AS sk']
    cols += ["%s AS %s" % (expr(dialect, [a], t), a) for a, t in META]
    cols += ["%s AS %s" % (expr(dialect, [a], t), a) for a, t in e["cols"].items()]
    if e["entity"] in FLATTEN:
        m, keys = FLATTEN[e["entity"]]
        cols += ["%s AS %s_%s" % (expr(dialect, [m, k], "varchar(256)"), m[:4], k) for k in keys]
    name = "stg.%s" % snake(e["entity"])
    typ = expr(dialect, ["type"], "varchar(64)")
    deleted = expr(dialect, ["deleted"], "boolean")
    body = ("SELECT\n  " + ",\n  ".join(cols) + "\nFROM %s\nWHERE %s = '%s' AND COALESCE(%s, false) = false"
            % (landing(dialect, e["table"]), typ, e["entity"], deleted))
    # Materialized: Redshift refreshes MVs over zero-ETL tables incrementally (AUTO REFRESH); the star build then reads
    # narrow typed columns instead of re-navigating SUPER. Postgres stand-in: plain materialized views (refreshed per run).
    opts = " AUTO REFRESH YES" if dialect == "redshift" else ""
    hdr = "-- %s/%s  <- %s\n" % (e["table"], e["entity"], ", ".join(sorted(set(e["sources"]))))
    return hdr + "CREATE MATERIALIZED VIEW %s%s AS\n%s;\n" % (name, opts, body)

def main():
    m = json.load(open(os.path.join(ROOT, "design/mapping/mapping.json")))
    ents = entities(m)
    for d in ("postgres", "redshift"):
        parts = ["-- GENERATED by warehouse/gen_staging.py from design/mapping/mapping.json - do not edit.\n"
                 "-- Typed staging materialized views (one per DynamoDB entity type) over the zero-ETL landing tables; tombstones excluded.\n"
                 "DROP SCHEMA IF EXISTS stg CASCADE;\nCREATE SCHEMA stg;\n"]
        parts += [view_sql(d, e) for _, e in sorted(ents.items())]
        open(os.path.join(ROOT, "warehouse/sql/%s/10_staging_views.sql" % d), "w").write("\n".join(parts))
    write_procedure(ents)
    print("%d staging views" % len(ents))

def write_procedure(ents):
    sys.path.insert(0, os.path.join(ROOT, "warehouse/local"))
    from pg import split
    body = []
    for f in ("02_dims.sql", "03_facts.sql"):
        body += ["    -- " + f] + ["    " + st.replace("\n", "\n    ") for st in split(open(os.path.join(ROOT, "warehouse/sql/star", f)).read())]
    sql = ("-- GENERATED by warehouse/gen_staging.py from 02_dims.sql + 03_facts.sql - do not edit.\n"
           "-- One transaction: refresh nothing here (staging MVs auto-refresh on Redshift; run_star.py refreshes them locally),\n"
           "-- rebuild dims then facts. Scheduled on Redshift by EventBridge Scheduler -> Redshift Data API (aws/warehouse/terraform).\n"
           "CREATE OR REPLACE PROCEDURE dw.sp_build_star()\nAS $$\nBEGIN\n" + "\n".join(body) + "\nEND;\n$$ LANGUAGE plpgsql;\n")
    open(os.path.join(ROOT, "warehouse/sql/star/20_build_procedure.sql"), "w").write(sql)

if __name__ == "__main__":
    main()
