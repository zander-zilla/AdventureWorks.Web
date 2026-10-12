"""Integration tests on the Postgres stand-in after scripts/warehouse-up.sh (set AW_WH_IT=1)."""
import json, os, sys
import pytest
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(ROOT, "warehouse/local"))
pytestmark = pytest.mark.skipif(os.environ.get("AW_WH_IT") != "1", reason="needs scripts/warehouse-up.sh (AW_WH_IT=1)")

def counts(cur):
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'dw' AND table_type = 'BASE TABLE' ORDER BY 1")
    out = {}
    for (t,) in cur.fetchall():
        cur.execute("SELECT COUNT(*) FROM dw.%s" % t); out[t] = cur.fetchone()[0]
    return out

@pytest.fixture
def conn():
    import pg
    c = pg.connect(); yield c; c.rollback(); c.close()

def test_rebuild_is_idempotent(conn):
    cur = conn.cursor(); before = counts(cur)
    cur.execute("SELECT SUM(sales_amount) FROM dw.fact_internet_sales"); s0 = cur.fetchone()[0]
    cur.execute("CALL dw.sp_build_star()")
    assert counts(cur) == before
    cur.execute("SELECT SUM(sales_amount) FROM dw.fact_internet_sales"); assert cur.fetchone()[0] == s0

def test_replicated_changes_flow_into_facts(conn):
    """A DynamoDB-native order (src=ddb, D5 id range) appears in FactInternetSales; a tombstoned line (D10) disappears."""
    cur = conn.cursor()
    cur.execute("""INSERT INTO landing."aw-sales" ("PK", "SK", value)
                   SELECT 'ORDER#1000000001', "SK", jsonb_set(jsonb_set(jsonb_set(value, '{sales_order_id}', '{"N": "1000000001"}'),
                          '{src}', '{"S": "ddb"}'), '{sales_order_number}', '{"S": "SO-DDB-1000000001"}')
                   FROM landing."aw-sales" WHERE "PK" = 'ORDER#0000043697' AND "SK" = 'ORDER'""")
    cur.execute("""INSERT INTO landing."aw-sales" ("PK", "SK", value)
                   SELECT 'ORDER#1000000001', "SK", jsonb_set(value, '{sales_order_id}', '{"N": "1000000001"}')
                   FROM landing."aw-sales" WHERE "PK" = 'ORDER#0000043697' AND "SK" LIKE 'LINE#%'""")
    cur.execute("""UPDATE landing."aw-sales" SET value = value || '{"deleted": {"BOOL": true}}'
                   WHERE "PK" = 'ORDER#0000043698' AND "SK" LIKE 'LINE#%'""")
    cur.execute("REFRESH MATERIALIZED VIEW stg.order; REFRESH MATERIALIZED VIEW stg.order_line")
    cur.execute("CALL dw.sp_build_star()")
    cur.execute("SELECT COUNT(*), SUM(sales_amount) FROM dw.fact_internet_sales WHERE sales_order_number = 'SO-DDB-1000000001'")
    n, amt = cur.fetchone()
    cur.execute("SELECT SUM(sales_amount) FROM dw.fact_internet_sales WHERE sales_order_number = 'SO43697'")
    assert n >= 1 and amt == cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM dw.fact_internet_sales WHERE sales_order_number = 'SO43698'")
    assert cur.fetchone()[0] == 0

def test_reconciliation_gate_passed():
    r = json.load(open("/tmp/warehouse-reconcile.json"))
    assert r["gate_failures"] == []
    fis = r["facts"]["fact_internet_sales"]
    assert fis["rows"] == fis["ref_rows"] == fis["matched_lines"] == 60398

def test_static_carry_over_loaded(conn):
    cur = conn.cursor()
    expect = {"fact_finance": 39409, "dim_account": 99, "dim_organization": 14, "dim_department_group": 7, "dim_scenario": 3,
              "fact_call_center": 120, "fact_survey_response": 2727, "fact_additional_international_product_description": 15168,
              "new_fact_currency_rate": 50, "prospective_buyer": 2059}
    for t, n in expect.items():
        cur.execute("SELECT COUNT(*) FROM dw_static.%s" % t); assert cur.fetchone()[0] == n, t
    # FactSurveyResponse keeps joining DimCustomer because customer_key = CustomerID
    cur.execute("SELECT COUNT(*) FROM dw_static.fact_survey_response s LEFT JOIN dw.dim_customer c ON c.customer_key = s.customer_key WHERE c.customer_key IS NULL")
    assert cur.fetchone()[0] == 0
