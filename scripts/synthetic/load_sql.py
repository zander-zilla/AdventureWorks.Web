#!/usr/bin/env python3
"""C2-7: insert generated rows into the SQL Server source (the system of record), in date order, one transaction per batch.
From there the normal path carries them: SQL Server CDC -> DMS (AWS) / Debezium (local) -> CDC Lambda -> DynamoDB -> zero-ETL.

- Resumable and idempotent: dbo.SyntheticBatch records every loaded range (seed, profile hash, rows); a run continues
  from the day after the last batch and refuses to mix seeds or profiles.
- Batches: a month (--mode bulk) or a day (--mode trickle, the daily job; catches up every missed day up to --end).
- Inside each batch transaction the AdventureWorks triggers that would stamp GETDATE() into history or rewrite original
  rows (SalesPerson.SalesYTD) are disabled; DISABLE TRIGGER is transactional and holds a schema lock, so concurrent writers
  wait instead of skipping them. Identities are re-seeded below the synthetic floors afterwards, so demo orders and the
  Before app keep getting original-range keys.
Usage: python scripts/synthetic/load_sql.py [--end YYYY-MM-DD (default yesterday)] [--mode bulk|trickle] [--seed 2026] [--dry-run]"""
import argparse, datetime as dt, decimal, hashlib, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "loader"))
import generate as G

ORDER = ["Production.Product", "Production.ProductProductPhoto", "Production.BillOfMaterials", "Production.ProductListPriceHistory",
         "Production.ProductCostHistory", "Sales.SpecialOffer", "Sales.SpecialOfferProduct", "Sales.SalesPersonQuotaHistory",
         "Person.BusinessEntity", "Person.Person", "Person.EmailAddress", "Person.PersonPhone", "Person.Address", "Person.BusinessEntityAddress",
         "Sales.Customer", "Sales.SalesOrderHeader", "Sales.SalesOrderDetail", "Sales.SalesOrderHeaderSalesReason", "Production.WorkOrder",
         "Production.WorkOrderRouting", "Purchasing.PurchaseOrderHeader", "Purchasing.PurchaseOrderDetail", "Production.TransactionHistory",
         "Production.ProductReview"]
TRIGGERS = ["Sales.iduSalesOrderDetail ON Sales.SalesOrderDetail", "Sales.uSalesOrderHeader ON Sales.SalesOrderHeader",
            "Purchasing.iPurchaseOrderDetail ON Purchasing.PurchaseOrderDetail", "Production.iWorkOrder ON Production.WorkOrder"]
# identity column floors of generated keys (see awmap.SYNTHETIC / generate.SLOT)
IDENT_FLOOR = {"Sales.SalesOrderHeader": 1000000, "Sales.SalesOrderDetail": 10000000, "Sales.Customer": 500000, "Person.BusinessEntity": 500000,
               "Person.EmailAddress": 500000, "Person.Address": 500000, "Production.WorkOrder": 500000, "Purchasing.PurchaseOrderHeader": 500000,
               "Purchasing.PurchaseOrderDetail": 500000, "Production.TransactionHistory": 10000000, "Production.ProductReview": 50000,
               "Production.Product": 5000, "Production.BillOfMaterials": 50000, "Sales.SpecialOffer": 100}
BATCH_DDL = """IF OBJECT_ID('dbo.SyntheticBatch') IS NULL CREATE TABLE dbo.SyntheticBatch (
  BatchID int IDENTITY(1,1) PRIMARY KEY, BatchFrom date NOT NULL, BatchTo date NOT NULL, Seed int NOT NULL, ProfileSha char(64) NOT NULL,
  Mode varchar(10) NOT NULL, RowsInserted int NOT NULL, LoadedAt datetime2 NOT NULL DEFAULT SYSUTCDATETIME())"""


def lit(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, decimal.Decimal)):
        return str(v)
    if isinstance(v, float):
        return repr(round(v, 6))
    return "N'" + str(v).replace("'", "''") + "'"


def profile_sha():
    return hashlib.sha256(open(G.PROFILE, "rb").read()).hexdigest()


def connect():
    import sqlsrc
    return sqlsrc.connect()


def state(cur):
    cur.execute(BATCH_DDL)
    cur.execute("SELECT MAX(BatchTo) last, MIN(Seed) s1, MAX(Seed) s2, MIN(ProfileSha) p1, MAX(ProfileSha) p2 FROM dbo.SyntheticBatch")
    return cur.fetchone()


def identity_tables(cur):
    cur.execute("SELECT OBJECT_SCHEMA_NAME(object_id) + '.' + OBJECT_NAME(object_id) t, name FROM sys.identity_columns WHERE OBJECTPROPERTY(object_id, 'IsUserTable') = 1")
    return {r["t"]: r["name"] for r in cur.fetchall()}


def write_batch(conn, batch, a, b, seed, mode, ident):
    cur = conn.cursor(); n = 0
    cur.execute("EXEC sp_getapplock @Resource = 'aw-synthetic', @LockMode = 'Exclusive', @LockOwner = 'Transaction', @LockTimeout = 600000")
    for t in TRIGGERS:
        cur.execute("DISABLE TRIGGER " + t)
    for table in ORDER:
        rows = batch.rows.get(table) or []
        if not rows:
            continue
        cols = list(rows[0]); ident_on = table in ident and ident[table] in cols
        if ident_on:
            cur.execute("SET IDENTITY_INSERT %s ON" % table)
        step = max(1, min(1000, 2000 // len(cols) * 10))
        for i in range(0, len(rows), step):
            chunk = rows[i:i + step]
            cur.execute("INSERT INTO %s (%s) VALUES %s" % (table, ", ".join("[%s]" % c for c in cols),
                        ", ".join("(" + ", ".join(lit(r[c]) for c in cols) + ")" for r in chunk)))
            n += len(chunk)
        if ident_on:
            cur.execute("SET IDENTITY_INSERT %s OFF" % table)
    for table, sets, where in batch.updates:
        lo, hi = where["SalesOrderID_between"]
        cur.execute("UPDATE %s SET %s WHERE SalesOrderID BETWEEN %d AND %d AND Status < %d" % (
            table, ", ".join("[%s] = %s" % (k, lit(v)) for k, v in sets.items()), lo, hi, where["Status_lt"]))
    for t in TRIGGERS:
        cur.execute("ENABLE TRIGGER " + t)
    for table, col in sorted(ident.items()):   # keep the next identity value in the original range
        if table in IDENT_FLOOR and batch.rows.get(table):
            cur.execute("SELECT ISNULL(MAX([%s]), 0) m FROM %s WHERE [%s] < %d" % (col, table, col, IDENT_FLOOR[table]))
            cur.execute("DBCC CHECKIDENT ('%s', RESEED, %d) WITH NO_INFOMSGS" % (table, cur.fetchone()["m"]))
    cur.execute("INSERT INTO dbo.SyntheticBatch (BatchFrom, BatchTo, Seed, ProfileSha, Mode, RowsInserted) VALUES (%s, %s, %s, %s, %s, %s)",
                (a.isoformat(), b.isoformat(), seed, profile_sha(), mode, n))
    conn.commit()
    return n


def batches(start, end, mode):
    d = start
    while d <= end:
        if mode == "trickle":
            yield d, d
            d += dt.timedelta(days=1)
        else:
            nxt = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
            yield d, min(end, nxt - dt.timedelta(days=1))
            d = nxt


def run(end, mode="bulk", seed=2026, dry_run=False, conn=None, growth=0.05, dip2020=False, log=print):
    conn = conn or connect(); cur = conn.cursor(); s = state(cur); conn.commit()
    if s["last"] and (s["s1"] != seed or s["s2"] != seed or s["p1"] != profile_sha() or s["p2"] != profile_sha()):
        raise SystemExit("dbo.SyntheticBatch was loaded with another seed/profile: restore the original backup first (docs/chapter-2/PLAN.md, C2-7)")
    start = (s["last"] + dt.timedelta(days=1)) if s["last"] else G.ORIGIN
    if isinstance(start, dt.datetime):
        start = start.date()
    gen = G.Generator(seed=seed, growth=growth, dip2020=dip2020); ident = identity_tables(cur); total = 0; t0 = time.time(); done = []
    for a, b in batches(start, end, mode):
        batch = gen.range(a, b)
        n = sum(batch.counts().values())
        if not dry_run:
            n = write_batch(conn, batch, a, b, seed, mode, ident)
        total += n; done.append([a.isoformat(), b.isoformat(), n])
        log("%s %s..%s %8d rows  (%.0f s)" % ("dry-run" if dry_run else "loaded", a, b, n, time.time() - t0))
    return {"from": start.isoformat(), "to": end.isoformat(), "batches": len(done), "rows": total, "seconds": round(time.time() - t0, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--end", default=(dt.date.today() - dt.timedelta(days=1)).isoformat())
    ap.add_argument("--mode", choices=["bulk", "trickle"], default="bulk"); ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--dip2020", action="store_true")
    a = ap.parse_args()
    print(json.dumps(run(dt.date.fromisoformat(a.end), a.mode, a.seed, a.dry_run, dip2020=a.dip2020), indent=1))


if __name__ == "__main__":
    main()
