#!/usr/bin/env python3
"""C2-6 derived AI inputs, written after the Phase 3 load (src='derived', never replicated back to SQL):
  aw-inventory  DEMAND#<pid> / M#yyyy-MM   ProductDemandMonth  monthly units + orders per product (smart reorder forecast, INV-07)
  aw-catalog    ALSO#<pid>   / RANK#nn     AlsoBought          top co-purchased products (customers also bought, CAT-12)
Dedicated partitions, so the product partitions (and their parsers) are untouched. Idempotent: re-running overwrites.
Usage: python scripts/loader/derive_ai.py [--top 6]   (DDB_ENDPOINT=aws on AWS, see docs/aws-setup.md)"""
import argparse, json, os, sys
from decimal import Decimal
sys.path.insert(0, os.path.dirname(__file__))
import ddb, sqlsrc

DEMAND_SQL = """SELECT d.ProductID AS pid, CONVERT(char(7), h.OrderDate, 126) AS month, SUM(d.OrderQty) AS qty, COUNT(DISTINCT h.SalesOrderID) AS orders
FROM Sales.SalesOrderDetail d JOIN Sales.SalesOrderHeader h ON h.SalesOrderID = d.SalesOrderID
GROUP BY d.ProductID, CONVERT(char(7), h.OrderDate, 126)"""
ALSO_SQL = """WITH pairs AS (
  SELECT a.ProductID AS pid, b.ProductID AS other, COUNT(DISTINCT a.SalesOrderID) AS orders
  FROM Sales.SalesOrderDetail a JOIN Sales.SalesOrderDetail b ON b.SalesOrderID = a.SalesOrderID AND b.ProductID <> a.ProductID
  GROUP BY a.ProductID, b.ProductID),
ranked AS (SELECT p.*, ROW_NUMBER() OVER (PARTITION BY p.pid ORDER BY p.orders DESC, p.other) AS rnk FROM pairs p)
SELECT r.pid, r.other, r.orders, r.rnk, pr.Name AS other_name, pr.ProductNumber AS other_number, pr.ListPrice AS other_price
FROM ranked r JOIN Production.Product pr ON pr.ProductID = r.other WHERE r.rnk <= %d"""

def demand_items(rows):
    for r in rows:
        yield {"PK": "DEMAND#%d" % r["pid"], "SK": "M#%s" % r["month"], "type": "ProductDemandMonth", "src": "derived", "derived": True,
               "product_id": r["pid"], "month": r["month"], "qty": int(r["qty"]), "orders": int(r["orders"])}

def also_items(rows):
    for r in rows:
        yield {"PK": "ALSO#%d" % r["pid"], "SK": "RANK#%02d" % r["rnk"], "type": "AlsoBought", "src": "derived", "derived": True,
               "product_id": r["pid"], "other_id": r["other"], "other_name": r["other_name"], "other_number": r["other_number"],
               "other_price": Decimal(str(r["other_price"])), "orders": int(r["orders"]), "rank": int(r["rnk"])}

def write(table, items):
    n = 0
    with ddb.resource().Table(table).batch_writer(overwrite_by_pkeys=["PK", "SK"]) as w:
        for it in items:
            w.put_item(Item=it); n += 1
    return n

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--top", type=int, default=6); a = ap.parse_args()
    conn = sqlsrc.connect(); cur = conn.cursor()
    cur.execute(DEMAND_SQL); demand = cur.fetchall()
    cur.execute(ALSO_SQL % a.top); also = cur.fetchall(); conn.close()
    out = {"aw-inventory ProductDemandMonth": write("aw-inventory", demand_items(demand)), "aw-catalog AlsoBought": write("aw-catalog", also_items(also))}
    print(json.dumps(out))

if __name__ == "__main__":
    main()
