"""C2-7 database tests after scripts/synthetic/load_sql.py (run by scripts/synthetic-up.sh with AW_SYN_IT=1):
original rows unchanged, every generated row marked and counted, constraints in SQL, identities kept in the original range,
resumable, and the daily trickle (last test: it moves the end date on by 3 days) ends where a bulk run ends."""
import datetime as dt, json, os, sys
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts", "synthetic")); sys.path.insert(0, os.path.join(ROOT, "scripts", "loader"))
pytestmark = pytest.mark.skipif(os.environ.get("AW_SYN_IT") != "1", reason="needs SQL Server with the generated slice (scripts/synthetic-up.sh)")

END = dt.date.fromisoformat(os.environ.get("SYNTHETIC_END", "2014-12-31"))


@pytest.fixture(scope="module")
def conn():
    import sqlsrc
    c = sqlsrc.connect(); yield c; c.close()


def one(conn, sql):
    cur = conn.cursor(); cur.execute(sql); return cur.fetchone()


def test_original_rows_unchanged(conn):
    import original_checksum
    before = json.load(open("/tmp/original-before.json"))
    assert original_checksum.checksums(conn) == before


def test_generated_rows_match_the_generator(conn):
    import generate as G
    from marking import synthetic_where
    counts = G.Generator().range(G.ORIGIN, END).counts()
    for table, n in counts.items():
        assert one(conn, "SELECT COUNT(*) n FROM %s WHERE %s" % (table, synthetic_where(table)))["n"] == n, table


def test_batches_recorded_and_resumable(conn):
    import load_sql
    r = one(conn, "SELECT MIN(BatchFrom) a, MAX(BatchTo) b, COUNT(DISTINCT Seed) s FROM dbo.SyntheticBatch")
    assert (r["a"], r["b"], r["s"]) == (dt.date(2014, 7, 1), END, 1)
    again = load_sql.run(END, conn=conn, log=lambda *_: None)
    assert again["batches"] == 0 and again["rows"] == 0


def test_identities_stay_in_original_range(conn):
    import load_sql
    for t, floor in load_sql.IDENT_FLOOR.items():
        assert one(conn, "SELECT IDENT_CURRENT('%s') i" % t)["i"] < floor, t


def test_constraints_in_sql(conn):
    checks = {
        "order before customer": """SELECT COUNT(*) n FROM Sales.SalesOrderHeader h JOIN Sales.Customer c ON c.CustomerID = h.CustomerID
                                    WHERE h.SalesOrderID >= 1000000 AND c.CustomerID >= 500000 AND c.ModifiedDate > h.OrderDate""",
        "line outside sell window": """SELECT COUNT(*) n FROM Sales.SalesOrderDetail d JOIN Sales.SalesOrderHeader h ON h.SalesOrderID = d.SalesOrderID
                                       JOIN Production.Product p ON p.ProductID = d.ProductID WHERE h.SalesOrderID >= 1000000
                                       AND (h.OrderDate < p.SellStartDate OR (p.ProductID >= 5000 AND h.OrderDate > p.SellEndDate))""",
        "discount outside offer dates": """SELECT COUNT(*) n FROM Sales.SalesOrderDetail d JOIN Sales.SalesOrderHeader h ON h.SalesOrderID = d.SalesOrderID
                                           JOIN Sales.SpecialOffer o ON o.SpecialOfferID = d.SpecialOfferID WHERE h.SalesOrderID >= 1000000
                                           AND d.UnitPriceDiscount > 0 AND (h.OrderDate < o.StartDate OR h.OrderDate > o.EndDate)""",
        "header totals": """SELECT COUNT(*) n FROM Sales.SalesOrderHeader h WHERE h.SalesOrderID >= 1000000 AND ABS(h.SubTotal -
                            (SELECT SUM(LineTotal) FROM Sales.SalesOrderDetail d WHERE d.SalesOrderID = h.SalesOrderID)) > 0.05""",
        "receipts over ordered": "SELECT COUNT(*) n FROM Purchasing.PurchaseOrderDetail WHERE PurchaseOrderID >= 500000 AND (ReceivedQty > OrderQty OR RejectedQty > ReceivedQty)",
        "scrap over produced": "SELECT COUNT(*) n FROM Production.WorkOrder WHERE WorkOrderID >= 500000 AND ScrappedQty > OrderQty",
        "history dated today": "SELECT COUNT(*) n FROM Production.TransactionHistory WHERE TransactionID >= 10000000 AND TransactionDate > '%s'" % END.isoformat(),
        # e-mail is a unique lookup item in DynamoDB (EMAIL#...): a generated address must never reuse an original one
        "e-mail reused": "SELECT COUNT(*) n FROM (SELECT EmailAddress FROM Person.EmailAddress GROUP BY EmailAddress HAVING COUNT(*) > 1 AND MAX(BusinessEntityID) >= 500000) x",
        "unshipped old orders": "SELECT COUNT(*) n FROM Sales.SalesOrderHeader WHERE SalesOrderID >= 1000000 AND Status < 5 AND OrderDate <= '%s'" % (END - dt.timedelta(days=7)).isoformat(),
    }
    bad = {k: one(conn, sql)["n"] for k, sql in checks.items()}
    assert not any(bad.values()), bad


def test_trickle_catches_up_and_matches_bulk(conn):
    """Last: the daily job loads END+1..END+3 one day per transaction; the result equals a single generator run."""
    import generate as G, load_sql
    end = END + dt.timedelta(days=3)
    r = load_sql.run(end, mode="trickle", conn=conn, log=lambda *_: None)
    assert r["batches"] == 3
    assert one(conn, "SELECT COUNT(*) n FROM dbo.SyntheticBatch WHERE Mode = 'trickle'")["n"] == 3
    lo = END - dt.timedelta(days=10)
    want = G.apply_updates(G.Generator().range(lo, end))
    cur = conn.cursor()
    cur.execute("SELECT SalesOrderID, Status, CONVERT(char(10), ShipDate, 23) s FROM Sales.SalesOrderHeader WHERE SalesOrderID >= %d ORDER BY 1"
                % (1000000 + G.Generator.idx(lo) * G.SLOT["order"]))
    got = [(x["SalesOrderID"], x["Status"], x["s"]) for x in cur.fetchall()]
    exp = sorted((h["SalesOrderID"], h["Status"], h["ShipDate"][:10] if h["ShipDate"] else None) for h in want.rows["Sales.SalesOrderHeader"])
    assert got == exp
