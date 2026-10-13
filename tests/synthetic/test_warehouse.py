"""C2-7: the generated history reaches the star schema through the same zero-ETL path (Postgres stand-in), next to the
original rows that warehouse/local/reconcile.py --original-only keeps reconciling exactly. Run after scripts/synthetic-up.sh
+ WH_RECONCILE_ARGS=--original-only scripts/warehouse-up.sh with AW_WH_SYN=1."""
import os, sys
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "warehouse", "local")); sys.path.insert(0, os.path.join(ROOT, "scripts", "loader"))
pytestmark = pytest.mark.skipif(os.environ.get("AW_WH_SYN") != "1", reason="needs the star built over the generated slice")


@pytest.fixture(scope="module")
def pgc():
    import pg
    c = pg.connect(); yield c.cursor(); c.close()


@pytest.fixture(scope="module")
def sql():
    import sqlsrc
    c = sqlsrc.connect(); yield c.cursor(); c.close()


def v(cur, q):
    cur.execute(q); r = cur.fetchone(); return list(r.values())[0] if isinstance(r, dict) else r[0]


def test_generated_lines_in_facts(pgc, sql):
    for flag, fact in ((1, "fact_internet_sales"), (0, "fact_reseller_sales")):
        want = v(sql, "SELECT COUNT(*) AS n FROM Sales.SalesOrderDetail d JOIN Sales.SalesOrderHeader h ON h.SalesOrderID = d.SalesOrderID WHERE h.SalesOrderID >= 1000000 AND h.OnlineOrderFlag = %d" % flag)
        got = v(pgc, "SELECT COUNT(*) FROM dw.%s WHERE CAST(SUBSTRING(sales_order_number FROM 3) AS integer) >= 1000000" % fact)
        assert want > 0 and got == want, fact


def test_generated_dimensions(pgc, sql):
    assert v(pgc, "SELECT COUNT(*) FROM dw.dim_customer WHERE CAST(SUBSTRING(customer_alternate_key FROM 3) AS integer) >= 500000") == \
        v(sql, "SELECT COUNT(*) AS n FROM Sales.Customer WHERE CustomerID >= 500000")
    assert v(pgc, "SELECT COUNT(DISTINCT product_alternate_key) FROM dw.dim_product WHERE product_alternate_key LIKE 'SY-%'") == \
        v(sql, "SELECT COUNT(*) AS n FROM Production.Product WHERE ProductID >= 5000")
    assert v(pgc, "SELECT COUNT(*) FROM dw.dim_promotion WHERE promotion_alternate_key >= 100") == v(sql, "SELECT COUNT(*) AS n FROM Sales.SpecialOffer WHERE SpecialOfferID >= 100")
    assert v(pgc, "SELECT MAX(date_key) FROM dw.dim_date") >= 20141231


def test_history_is_continuous_by_month(pgc):
    pgc.execute("""SELECT DISTINCT CAST(order_date_key / 100 AS integer) FROM dw.fact_internet_sales ORDER BY 1""")
    months = [r[0] for r in pgc.fetchall()]
    ym = [(m // 100) * 12 + m % 100 for m in months]
    assert all(b - a == 1 for a, b in zip(ym, ym[1:])), "a month without web sales"
    assert months[-1] >= 201412
