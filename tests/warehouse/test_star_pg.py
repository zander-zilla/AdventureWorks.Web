"""Integration tests on the Postgres stand-in after scripts/warehouse-up.sh (set AW_WH_IT=1)."""
import json, os, sys
from decimal import Decimal
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

def _j(v):
    """Python -> DynamoDB JSON attribute map (the zero-ETL landing shape)."""
    out = {}
    for k, x in v.items():
        out[k] = {"BOOL": x} if isinstance(x, bool) else {"N": str(x)} if isinstance(x, (int, float)) else {"S": x}
    return json.dumps(out)

def test_c2_2_app_writes_reach_the_star(conn):
    """C2-2 reconciliation: the items the app writes (shipped order with offer + tracking, TransactionHistory type S,
    ListPriceHistory close + new, ProductReview; all src=ddb, src_lsn=~app) flow through staging into the star:
    tax/freight allocated by line share, promotion key, tracking, a 2026 DimDate, one inventory row per moved day
    (no 12-year grid), a new DimProduct SCD2 version."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM dw.fact_product_inventory"); inv_rows0 = cur.fetchone()[0]
    app = {"src": "ddb", "src_lsn": "~app"}
    # shipped native order: copy of SO43697 re-keyed, as SalesRepository.Plan + FulfilmentRepository.ShipPlan write it
    cur.execute("""INSERT INTO landing."aw-sales" ("PK", "SK", value)
                   SELECT 'ORDER#1000000002', "SK", value || %s::jsonb || jsonb_build_object('tax_amt', jsonb_build_object('N', ROUND((value->'sub_total'->>'N')::numeric * 0.088, 4)::text))
                   FROM landing."aw-sales" WHERE "PK" = 'ORDER#0000043697' AND "SK" = 'ORDER'""",
                (_j(dict(app, sales_order_id=1000000002, sales_order_number="SO-DDB-1000000002", status=5, order_date="2026-10-12T15:00:00",
                         due_date="2026-10-24T15:00:00", ship_date="2026-10-12T18:00:00", ship_method_id=5, carrier_tracking_number="1ZC22WH")),))
    cur.execute("""INSERT INTO landing."aw-sales" ("PK", "SK", value)
                   SELECT 'ORDER#1000000002', "SK", value || %s::jsonb FROM landing."aw-sales" WHERE "PK" = 'ORDER#0000043697' AND "SK" LIKE 'LINE#%%'""",
                (_j(dict(app, sales_order_id=1000000002, special_offer_id=2, unit_price_discount=0.02, carrier_tracking_number="1ZC22WH")),))
    cur.execute("""SELECT (value->'product_id'->>'N')::int, (value->'order_qty'->>'N')::int FROM landing."aw-sales" WHERE "PK" = 'ORDER#1000000002' AND "SK" LIKE 'LINE#%%' LIMIT 1""")
    pid, qty = cur.fetchone()
    cur.execute("""INSERT INTO landing."aw-inventory" ("PK", "SK", value) VALUES (%s, %s, %s::jsonb)""",
                ("PRODUCT#%06d" % pid, "TXN#2026-10-12T18:00:00#10000001", _j(dict(app, type="InventoryTransaction", transaction_id=10000001, product_id=pid,
                 reference_order_id=1000000002, reference_order_line_id=1, transaction_date="2026-10-12T18:00:00", transaction_type="S", quantity=qty,
                 actual_cost=1.0, modified_date="2026-10-12T18:00:00", archived=False))))
    # price edit (CatalogRepository.PriceHistoryActions): close the open version, add today's
    cur.execute("""SELECT "PK", "SK", (value->'product_id'->>'N')::int FROM landing."aw-catalog"
                   WHERE value->'type'->>'S' = 'ListPriceHistory' AND NOT value ? 'end_date' ORDER BY "PK" LIMIT 1""")
    ppk, psk, ppid = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM dw.dim_product WHERE product_id = %s", (ppid,)); versions0 = cur.fetchone()[0]
    cur.execute("""UPDATE landing."aw-catalog" SET value = value || %s::jsonb WHERE "PK" = %s AND "SK" = %s""", (_j(dict(app, end_date="2026-10-11T00:00:00")), ppk, psk))
    cur.execute("""INSERT INTO landing."aw-catalog" ("PK", "SK", value) VALUES (%s, 'PRICE#2026-10-12T00:00:00', %s::jsonb)""",
                (ppk, _j(dict(app, type="ListPriceHistory", product_id=ppid, start_date="2026-10-12T00:00:00", list_price=99.99, modified_date="2026-10-12T00:00:00"))))
    cur.execute("""INSERT INTO landing."aw-catalog" ("PK", "SK", value) VALUES ('PRODUCT#000709', 'REVIEW#2026-10-12T18:00:00#10001', %s::jsonb)""",
                (_j(dict(app, type="ProductReview", product_review_id=10001, product_id=709, reviewer_name="Walter Brian", review_date="2026-10-12T18:00:00",
                         email_address="walter0@adventure-works.com", rating=4, comments="Comfortable socks.", modified_date="2026-10-12T18:00:00")),))
    for v in ("order", "order_line", "inventory_transaction", "list_price_history", "product_review"):
        cur.execute("REFRESH MATERIALIZED VIEW stg.%s" % v)
    cur.execute("CALL dw.sp_build_star()")

    cur.execute("""SELECT COUNT(*), SUM(tax_amt), MIN(carrier_tracking_number), MIN(promotion_key), MIN(order_date_key) FROM dw.fact_internet_sales
                   WHERE sales_order_number = 'SO-DDB-1000000002'""")
    n, tax, track, promo, odk = cur.fetchone()
    cur.execute("""SELECT ROUND((value->'tax_amt'->>'N')::numeric, 4) FROM landing."aw-sales" WHERE "PK" = 'ORDER#1000000002' AND "SK" = 'ORDER'""")
    header_tax = cur.fetchone()[0]
    assert n >= 1 and abs(tax - header_tax) <= Decimal("0.0001") * n   # same allocation as Pricing.Allocate in the app
    assert track == "1ZC22WH" and promo == 2 and odk == 20261012
    cur.execute("SELECT MAX(full_date) FROM dw.dim_date"); assert str(cur.fetchone()[0]) == "2026-12-31"
    cur.execute("SELECT units_out FROM dw.fact_product_inventory f JOIN dw.dim_product p ON p.product_key = f.product_key WHERE p.product_id = %s AND f.date_key = 20261012", (pid,))
    assert cur.fetchone()[0] == qty
    cur.execute("SELECT COUNT(*) FROM dw.fact_product_inventory"); assert cur.fetchone()[0] - inv_rows0 <= 5
    cur.execute("SELECT COUNT(*), MAX(list_price) FILTER (WHERE end_date IS NULL) FROM dw.dim_product WHERE product_id = %s", (ppid,))
    versions, current = cur.fetchone()
    assert versions == versions0 + 1 and current == Decimal("99.99")
    cur.execute("SELECT COUNT(*) FROM stg.product_review WHERE product_review_id = 10001 AND src = 'ddb'"); assert cur.fetchone()[0] == 1

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
