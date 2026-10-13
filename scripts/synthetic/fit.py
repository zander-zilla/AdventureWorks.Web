#!/usr/bin/env python3
"""C2-7: fit the synthetic-data profile from the ORIGINAL AdventureWorks2022 rows (never from generated rows).
Writes scripts/synthetic/profile.json: demand shape (monthly seasonality, day of week, base level), basket and mix
distributions, reference data the generator needs (current products, stores, name pools, address pools, vendors,
routings, sales people), so generate.py runs without a database and is fully deterministic.
Usage: python scripts/synthetic/fit.py [--out scripts/synthetic/profile.json]   (CI checks the committed file is in sync)"""
import argparse, collections, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "loader"))
sys.path.insert(0, HERE)
import sqlsrc
from marking import original_where

FIT_FROM, FIT_TO = "2013-07-01", "2014-06-01"   # last 11 complete months with the full (2013+) online range


def rows(cur, sql, *a):
    cur.execute(sql, a); return cur.fetchall()


def num(v):
    return None if v is None else (int(v) if float(v).is_integer() else round(float(v), 4))


def fit(conn):
    cur = conn.cursor(); P = {"version": 1, "fit_window": [FIT_FROM, FIT_TO]}
    so = original_where("Sales.SalesOrderHeader", "h")
    # --- demand shape --------------------------------------------------------------------------------------------
    m = rows(cur, f"""SELECT MONTH(OrderDate) mo, COUNT(*) n FROM Sales.SalesOrderHeader h WHERE OnlineOrderFlag=1 AND {so}
                      AND OrderDate >= %s AND OrderDate < %s GROUP BY MONTH(OrderDate)""", FIT_FROM, FIT_TO)
    days = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}
    per_day = {r["mo"]: r["n"] / days[r["mo"]] for r in m}
    base = sum(per_day.values()) / len(per_day)
    P["online_orders_per_day"] = round(base, 3)
    P["month_index"] = [round(per_day.get(i, base) / base, 4) for i in range(1, 13)]   # June: not in window -> 1.0
    d = rows(cur, f"""SELECT (DATEPART(weekday, OrderDate) + @@DATEFIRST - 2) % 7 dow, COUNT(*) n FROM Sales.SalesOrderHeader h
                      WHERE OnlineOrderFlag=1 AND {so} AND OrderDate >= %s AND OrderDate < %s GROUP BY (DATEPART(weekday, OrderDate) + @@DATEFIRST - 2) % 7""", FIT_FROM, FIT_TO)
    tot = sum(r["n"] for r in d)
    P["dow_index"] = [round(7 * next(r["n"] for r in d if r["dow"] == i) / tot, 4) for i in range(7)]   # Monday = 0
    r = rows(cur, f"""SELECT COUNT(*) n, COUNT(DISTINCT FORMAT(OrderDate,'yyyy-MM')) months FROM Sales.SalesOrderHeader h
                      WHERE OnlineOrderFlag=0 AND {so} AND OrderDate >= '2013-06-01' AND OrderDate < '2014-06-01'""")[0]
    P["reseller_orders_per_month"] = round(r["n"] / 12, 2)
    # --- territories, new customers ---------------------------------------------------------------------------------
    t = rows(cur, f"""SELECT h.TerritoryID tid, COUNT(*) n FROM Sales.SalesOrderHeader h WHERE OnlineOrderFlag=1 AND {so}
                      AND OrderDate >= %s AND OrderDate < %s GROUP BY h.TerritoryID ORDER BY 1""", FIT_FROM, FIT_TO)
    P["online_territory_share"] = {str(x["tid"]): round(x["n"] / sum(y["n"] for y in t), 4) for x in t}
    r = rows(cur, f"""WITH f AS (SELECT CustomerID, MIN(OrderDate) first FROM Sales.SalesOrderHeader h WHERE OnlineOrderFlag=1 AND {so} GROUP BY CustomerID)
                      SELECT SUM(CASE WHEN h.OrderDate = f.first THEN 1 ELSE 0 END) * 1.0 / COUNT(*) s FROM Sales.SalesOrderHeader h JOIN f ON f.CustomerID = h.CustomerID
                      WHERE h.OrderDate >= %s AND h.OrderDate < %s""", FIT_FROM, FIT_TO)[0]
    P["online_new_customer_share"] = round(float(r["s"]), 4)
    terr = rows(cur, "SELECT TerritoryID, CountryRegionCode cc FROM Sales.SalesTerritory ORDER BY 1")
    P["territory_country"] = {str(x["TerritoryID"]): x["cc"] for x in terr}
    # --- baskets ---------------------------------------------------------------------------------------------------
    def dist(sql, *a):
        rs = rows(cur, sql, *a); tot = sum(x["n"] for x in rs)
        return [[num(x["k"]), round(x["n"] / tot, 5)] for x in rs]
    P["online_lines"] = dist(f"""SELECT c k, COUNT(*) n FROM (SELECT COUNT(*) c FROM Sales.SalesOrderDetail d JOIN Sales.SalesOrderHeader h
                              ON h.SalesOrderID = d.SalesOrderID WHERE OnlineOrderFlag=1 AND {so} AND OrderDate >= %s AND OrderDate < %s GROUP BY h.SalesOrderID) x GROUP BY c ORDER BY c""", FIT_FROM, FIT_TO)
    P["reseller_lines"] = dist(f"""SELECT c k, COUNT(*) n FROM (SELECT COUNT(*) c FROM Sales.SalesOrderDetail d JOIN Sales.SalesOrderHeader h
                              ON h.SalesOrderID = d.SalesOrderID WHERE OnlineOrderFlag=0 AND {so} AND OrderDate >= '2013-06-01' GROUP BY h.SalesOrderID) x GROUP BY c ORDER BY c""")
    P["reseller_qty"] = dist(f"""SELECT OrderQty k, COUNT(*) n FROM Sales.SalesOrderDetail d JOIN Sales.SalesOrderHeader h ON h.SalesOrderID = d.SalesOrderID
                              WHERE OnlineOrderFlag=0 AND {so} AND OrderDate >= '2013-06-01' GROUP BY OrderQty ORDER BY OrderQty""")
    sr = rows(cur, f"""SELECT r.SalesReasonID k, COUNT(*) n FROM Sales.SalesOrderHeaderSalesReason r JOIN Sales.SalesOrderHeader h ON h.SalesOrderID = r.SalesOrderID
                       WHERE {so} AND OrderDate >= %s GROUP BY r.SalesReasonID ORDER BY 1""", FIT_FROM)
    n_on = rows(cur, f"SELECT COUNT(*) n FROM Sales.SalesOrderHeader h WHERE OnlineOrderFlag=1 AND {so} AND OrderDate >= %s", FIT_FROM)[0]["n"]
    P["sales_reason_rate"] = {str(x["k"]): round(x["n"] / n_on, 4) for x in sr}
    # --- products --------------------------------------------------------------------------------------------------
    pr = rows(cur, f"""SELECT p.ProductID, p.Name, p.ProductNumber, p.MakeFlag, p.FinishedGoodsFlag, p.Color, p.SafetyStockLevel, p.ReorderPoint,
                         p.StandardCost, p.ListPrice, p.Size, p.SizeUnitMeasureCode, p.WeightUnitMeasureCode, p.Weight, p.DaysToManufacture,
                         p.ProductLine, p.Class, p.Style, p.ProductSubcategoryID, p.ProductModelID, sc.ProductCategoryID cat, pm.Name model
                       FROM Production.Product p LEFT JOIN Production.ProductSubcategory sc ON sc.ProductSubcategoryID = p.ProductSubcategoryID
                       LEFT JOIN Production.ProductModel pm ON pm.ProductModelID = p.ProductModelID
                       WHERE p.SellEndDate IS NULL AND {original_where('Production.Product', 'p')} ORDER BY p.ProductID""")
    def weights(online):
        rs = rows(cur, f"""SELECT d.ProductID, COUNT(*) n FROM Sales.SalesOrderDetail d JOIN Sales.SalesOrderHeader h ON h.SalesOrderID = d.SalesOrderID
                           WHERE OnlineOrderFlag=%s AND {so} AND OrderDate >= %s AND OrderDate < %s GROUP BY d.ProductID""", online, FIT_FROM, FIT_TO)
        tot = sum(x["n"] for x in rs); return {x["ProductID"]: x["n"] / tot for x in rs}
    won, woff = weights(1), weights(0)
    ratio = {x["cat"]: float(x["r"]) for x in rows(cur, f"""SELECT sc.ProductCategoryID cat, AVG(d.UnitPrice / p.ListPrice) r FROM Sales.SalesOrderDetail d
                     JOIN Sales.SalesOrderHeader h ON h.SalesOrderID = d.SalesOrderID JOIN Production.Product p ON p.ProductID = d.ProductID
                     JOIN Production.ProductSubcategory sc ON sc.ProductSubcategoryID = p.ProductSubcategoryID
                     WHERE OnlineOrderFlag=0 AND d.UnitPriceDiscount = 0 AND {so} AND OrderDate >= '2013-06-01' GROUP BY sc.ProductCategoryID""")}
    P["reseller_price_ratio"] = {str(k): round(v, 4) for k, v in sorted(ratio.items())}
    photos = {x["ProductID"]: x["ProductPhotoID"] for x in rows(cur, "SELECT ProductID, ProductPhotoID FROM Production.ProductProductPhoto WHERE [Primary] = 1")}
    P["products"] = [{**{k: num(v) if k in ("StandardCost", "ListPrice", "Weight") else v for k, v in x.items()},
                      "w_online": round(won.get(x["ProductID"], 0), 6), "w_reseller": round(woff.get(x["ProductID"], 0), 6),
                      "photo": photos.get(x["ProductID"])} for x in pr]
    bom = rows(cur, """SELECT ProductAssemblyID a, ComponentID c, UnitMeasureCode u, BOMLevel l, PerAssemblyQty q FROM Production.BillOfMaterials
                       WHERE EndDate IS NULL AND ProductAssemblyID IS NOT NULL ORDER BY 1, 2""")
    fg = {x["ProductID"] for x in pr if x["FinishedGoodsFlag"] and x["MakeFlag"] and x["cat"] == 1}
    P["bom"] = {str(a): [[x["c"], x["u"].strip(), x["l"], num(x["q"])] for x in bom if x["a"] == a] for a in sorted(fg)}
    # --- work orders, routings, scrap ------------------------------------------------------------------------------
    wo = rows(cur, f"""SELECT w.ProductID, COUNT(*) n, AVG(OrderQty * 1.0) q FROM Production.WorkOrder w WHERE {original_where('Production.WorkOrder', 'w')}
                       AND StartDate >= '2013-07-01' AND StartDate < '2014-07-01' GROUP BY w.ProductID ORDER BY 1""")
    ops = rows(cur, """WITH last AS (SELECT ProductID, MAX(WorkOrderID) wo FROM Production.WorkOrderRouting GROUP BY ProductID)
                       SELECT r.ProductID, r.OperationSequence s, r.LocationID loc, r.ActualResourceHrs h, r.PlannedCost c,
                              DATEDIFF(day, r.ScheduledStartDate, r.ScheduledEndDate) d
                       FROM Production.WorkOrderRouting r JOIN last ON last.wo = r.WorkOrderID AND last.ProductID = r.ProductID ORDER BY 1, 2""")
    P["work_orders"] = {str(x["ProductID"]): {"per_day": round(x["n"] / 365, 4), "qty": round(float(x["q"]), 1),
                        "ops": [[o["s"], o["loc"], num(o["h"]), num(o["c"]), o["d"]] for o in ops if o["ProductID"] == x["ProductID"]]} for x in wo}
    s = rows(cur, f"""SELECT SUM(CASE WHEN ScrappedQty > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) f, AVG(CASE WHEN ScrappedQty > 0 THEN ScrappedQty * 1.0 / OrderQty END) q
                      FROM Production.WorkOrder w WHERE {original_where('Production.WorkOrder', 'w')}""")[0]
    P["scrap"] = {"wo_share": round(float(s["f"]), 4), "qty_share": round(float(s["q"]), 4),
                  "reasons": [[x["ScrapReasonID"], round(x["n"] / sum(y["n"] for y in rr), 4)] for rr in [rows(cur, """SELECT ScrapReasonID, COUNT(*) n FROM Production.WorkOrder
                              WHERE ScrapReasonID IS NOT NULL GROUP BY ScrapReasonID ORDER BY 1""")] for x in rr]}
    # --- purchasing ------------------------------------------------------------------------------------------------
    pv = rows(cur, f"""SELECT pv.ProductID, pv.BusinessEntityID v, pv.AverageLeadTime lt, pv.StandardPrice sp, pv.MinOrderQty mn, pv.MaxOrderQty mx,
                         (SELECT COUNT(*) FROM Purchasing.PurchaseOrderDetail d JOIN Purchasing.PurchaseOrderHeader h ON h.PurchaseOrderID = d.PurchaseOrderID
                          WHERE d.ProductID = pv.ProductID AND h.VendorID = pv.BusinessEntityID AND h.OrderDate >= '2013-07-01') n
                       FROM Purchasing.ProductVendor pv JOIN Purchasing.Vendor v ON v.BusinessEntityID = pv.BusinessEntityID WHERE v.ActiveFlag = 1 ORDER BY 1, 2""")
    P["vendor_products"] = [[x["ProductID"], x["v"], x["lt"], num(x["sp"]), x["mn"], x["mx"], round(x["n"] / 62.0, 4)] for x in pv if x["n"]]  # lines per week
    P["po"] = {"reject_rate": round(float(rows(cur, "SELECT SUM(RejectedQty) / SUM(ReceivedQty) r FROM Purchasing.PurchaseOrderDetail")[0]["r"]), 4),
               "employees": [x["EmployeeID"] for x in rows(cur, "SELECT DISTINCT EmployeeID FROM Purchasing.PurchaseOrderHeader ORDER BY 1")],
               "ship_methods": [x["ShipMethodID"] for x in rows(cur, "SELECT DISTINCT ShipMethodID FROM Purchasing.PurchaseOrderHeader ORDER BY 1")]}
    # --- stores, sales people, quotas ------------------------------------------------------------------------------
    st = rows(cur, f"""SELECT h.CustomerID, MAX(h.SalesPersonID) sp, MAX(h.TerritoryID) tid, MAX(h.BillToAddressID) bill, MAX(h.ShipToAddressID) ship, COUNT(*) n
                       FROM Sales.SalesOrderHeader h WHERE OnlineOrderFlag=0 AND {so} AND OrderDate >= '2013-06-01' GROUP BY h.CustomerID ORDER BY 1""")
    P["stores"] = [[x["CustomerID"], x["sp"], x["tid"], x["bill"], x["ship"], x["n"]] for x in st]
    q = rows(cur, """SELECT q.BusinessEntityID id, q.SalesQuota sq FROM Sales.SalesPersonQuotaHistory q
                     WHERE QuotaDate = (SELECT MAX(QuotaDate) FROM Sales.SalesPersonQuotaHistory q2 WHERE q2.BusinessEntityID = q.BusinessEntityID) ORDER BY 1""")
    P["quotas"] = [[x["id"], num(x["sq"])] for x in q]
    # --- people pools (recombined, never copied as whole identities) -----------------------------------------------
    P["first_names"] = [x["FirstName"] for x in rows(cur, "SELECT DISTINCT FirstName FROM Person.Person WHERE PersonType = 'IN' ORDER BY 1")]
    P["last_names"] = [x["LastName"] for x in rows(cur, "SELECT DISTINCT LastName FROM Person.Person WHERE PersonType = 'IN' ORDER BY 1")]
    ad = rows(cur, """SELECT DISTINCT sp.TerritoryID tid, a.City, a.StateProvinceID spid, a.PostalCode pc FROM Person.Address a
                      JOIN Person.StateProvince sp ON sp.StateProvinceID = a.StateProvinceID ORDER BY 1, 2, 3, 4""")
    P["address_pool"] = {str(t_): [[x["City"], x["spid"], x["pc"]] for x in ad if x["tid"] == t_] for t_ in sorted({x["tid"] for x in ad})}
    P["streets"] = sorted({" ".join(x["l"].split(" ")[1:]) for x in rows(cur, "SELECT TOP 4000 AddressLine1 l FROM Person.Address ORDER BY AddressID") if " " in x["l"]})[:600]
    rv = rows(cur, "SELECT Rating k, COUNT(*) n FROM Production.ProductReview GROUP BY Rating ORDER BY 1")
    P["review_ratings"] = [[x["k"], round(x["n"] / sum(y["n"] for y in rv), 4) ] for x in rv]
    return P


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=os.path.join(HERE, "profile.json")); a = ap.parse_args()
    P = fit(sqlsrc.connect())
    with open(a.out, "w") as f:
        json.dump(P, f, indent=None, sort_keys=True, separators=(",", ":"), default=str); f.write("\n")
    print("profile: %d products, %d stores, %d work-order products, %d vendor lines -> %s" % (
        len(P["products"]), len(P["stores"]), len(P["work_orders"]), len(P["vendor_products"]), a.out))


if __name__ == "__main__":
    main()
