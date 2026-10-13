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


EVIDENCE = os.path.join(ROOT, "docs/business-processes/evidence.json")

def test_c2_3_purchasing_star_reconciles_with_oltp(conn):
    """FactPurchaseOrderLine / DimVendor rebuilt from aw-purchasing match Purchasing.* in AdventureWorks2022 (the counts and
    quantity sums measured on SQL Server for PR #15, docs/business-processes/evidence.json)."""
    m = json.load(open(EVIDENCE))["metrics"]
    ordered, received, rejected, stocked = (int(x) for x in m["pod.qty"]["ordered/received/rejected/stocked"].split("/"))
    cur = conn.cursor()
    cur.execute("""SELECT COUNT(*), SUM(order_quantity), SUM(received_quantity), SUM(rejected_quantity), SUM(stocked_quantity),
                          COUNT(DISTINCT purchase_order_id), SUM(CASE WHEN product_key IS NULL THEN 1 ELSE 0 END)
                   FROM dw.fact_purchase_order_line WHERE source = 'sql'""")
    n, o, r, j, s, pos, no_product = cur.fetchone()
    assert n == m["pod.receipt"]["full"] + m["pod.receipt"]["partial"] == 8845
    assert (o, r, j, s) == (ordered, received, rejected, stocked)
    assert pos == sum(m["poh.status"].values()) == 4012 and no_product == 0
    cur.execute("SELECT status, COUNT(DISTINCT purchase_order_id) FROM dw.fact_purchase_order_line WHERE source = 'sql' GROUP BY status")
    assert {str(k): v for k, v in cur.fetchall()} == m["poh.status"]
    cur.execute("SELECT COUNT(*), SUM(CASE WHEN preferred_vendor_flag THEN 1 ELSE 0 END), SUM(CASE WHEN active_flag THEN 0 ELSE 1 END) FROM dw.dim_vendor")
    assert cur.fetchone() == (104, 93, 4)
    # ShipDate = OrderDate + 9 on 4,000 POs (+25 on 12): lead times land in the fact
    cur.execute("SELECT lead_time_days, COUNT(DISTINCT purchase_order_id) FROM dw.fact_purchase_order_line WHERE source = 'sql' GROUP BY lead_time_days")
    assert {k: v for k, v in cur.fetchall()} == {int(k): v for k, v in m["poh.ship_minus_order_days"].items()}
    # the view aggregates the fact exactly (same definitions as the app's vendor page)
    cur.execute("SELECT SUM(lines), SUM(rejected_quantity), SUM(purchase_orders) FROM dw.v_vendor_performance")
    assert cur.fetchone() == (8845, rejected, 4012)
    cur.execute("SELECT COUNT(*) FROM dw.v_vendor_performance WHERE reject_rate < 0 OR reject_rate > 1 OR on_time_rate < 0 OR on_time_rate > 1")
    assert cur.fetchone()[0] == 0

def test_c2_3_po_tax_and_freight_ratio_matches_the_app():
    """The app writes TaxAmt = 8% and Freight = 2.5% of SubTotal (ProcurementRepository.TaxRate/FreightRate), the ratio of the
    SQL-era purchase order headers: tax holds for all 4,012; freight for all but 12 headers (sample-data outliers, measured in CI)."""
    import pg
    c = pg.connect(); cur = c.cursor()
    cur.execute("""SELECT COUNT(*), SUM(CASE WHEN ABS(tax_amt - ROUND(sub_total * 0.08, 4)) <= 0.01 THEN 1 ELSE 0 END),
                          SUM(CASE WHEN ABS(freight - ROUND(sub_total * 0.025, 4)) <= 0.01 THEN 1 ELSE 0 END)
                   FROM stg.purchase_order WHERE src = 'sql'""")
    n, tax_ok, freight_ok = cur.fetchone(); c.close()
    assert (n, tax_ok, freight_ok) == (4012, 4012, 4000), (n, tax_ok, freight_ok)

def test_c2_3_app_purchase_order_reaches_the_star(conn):
    """A PO written by the app (ProcurementRepository.CreatePlan + ReceivePlan item shapes) lands via zero-ETL: a fact row with
    PO-DDB number, on-time flag and app source, DimDate extended to 2026, the vendor's performance row counts it, and the receipt's
    TransactionHistory P adds units in to FactProductInventory."""
    cur = conn.cursor()
    app = {"src": "ddb", "src_lsn": "~app"}
    cur.execute("""SELECT (value->'business_entity_id'->>'N')::int, (value->'product_id'->>'N')::int, value->'product_name'->>'S'
                   FROM landing."aw-purchasing" WHERE "SK" LIKE 'PRODUCT#%%' AND value->>'type' LIKE '%%VendorProduct%%' ORDER BY "PK", "SK" LIMIT 1""")
    vendor, pid, pname = cur.fetchone()
    po, line = 100001, 100001
    cur.execute("""INSERT INTO landing."aw-purchasing" ("PK", "SK", value) VALUES ('PO#100001', 'PO', %s::jsonb)""",
                (_j(dict(app, type="PurchaseOrder", purchase_order_id=po, revision_number=3, status=4, employee_id=251, vendor_id=vendor, ship_method_id=3,
                         order_date="2026-10-01T09:00:00", ship_date="2026-10-12T18:00:00", sub_total=100.0, tax_amt=8.0, freight=2.5, total_due=110.5,
                         modified_date="2026-10-12T18:00:00", vendor_name="v", employee_name="Mikael Sandberg", ship_method_name="OVERSEAS - DELUXE")),))
    cur.execute("""INSERT INTO landing."aw-purchasing" ("PK", "SK", value) VALUES ('PO#100001', 'LINE#100001', %s::jsonb)""",
                (_j(dict(app, type="PurchaseOrderLine", purchase_order_id=po, purchase_order_detail_id=line, due_date="2026-10-18T00:00:00", order_qty=10,
                         product_id=pid, unit_price=10.0, line_total=100.0, received_qty=10, rejected_qty=1, stocked_qty=9, modified_date="2026-10-12T18:00:00",
                         product_name=pname)),))
    cur.execute("""INSERT INTO landing."aw-inventory" ("PK", "SK", value) VALUES (%s, 'TXN#2026-10-12T18:00:00#10000050', %s::jsonb)""",
                ("PRODUCT#%06d" % pid, _j(dict(app, type="InventoryTransaction", transaction_id=10000050, product_id=pid, reference_order_id=po,
                 reference_order_line_id=line, transaction_date="2026-10-12T18:00:00", transaction_type="P", quantity=9, actual_cost=10.0,
                 modified_date="2026-10-12T18:00:00", archived=False))))
    for v in ("purchase_order", "purchase_order_line", "inventory_transaction"):
        cur.execute("REFRESH MATERIALIZED VIEW stg.%s" % v)
    cur.execute("CALL dw.sp_build_star()")
    cur.execute("""SELECT purchase_order_number, status, on_time_flag, lead_time_days, source, stocked_quantity, order_date_key, product_key IS NOT NULL, employee_key IS NOT NULL
                   FROM dw.fact_purchase_order_line WHERE purchase_order_id = 100001""")
    assert cur.fetchone() == ("PO-DDB-100001", 4, 1, 11, "ddb", Decimal("9.0000"), 20261001, True, True)
    cur.execute("SELECT MAX(full_date) FROM dw.dim_date"); assert str(cur.fetchone()[0]) >= "2026-12-31"
    cur.execute("SELECT app_lines, purchase_orders FROM dw.v_vendor_performance WHERE vendor_key = %s", (vendor,))
    app_lines, n = cur.fetchone(); assert app_lines == 1 and n >= 1
    cur.execute("SELECT units_in FROM dw.fact_product_inventory f JOIN dw.dim_product p ON p.product_key = f.product_key WHERE p.product_id = %s AND f.date_key = 20261012", (pid,))
    assert cur.fetchone()[0] == 9
    cur.execute("SELECT COUNT(*) FROM dw.fact_purchase_order_line WHERE source = 'sql'"); assert cur.fetchone()[0] == 8845   # SQL-era lines untouched

def test_c2_4_production_star_reconciles_with_oltp(conn):
    """FactWorkOrder / FactWorkOrderRouting / DimScrapReason rebuilt from aw-inventory match Production.WorkOrder(Routing) in
    AdventureWorks2022 (counts, quantity sums, states, scrap reasons, routing steps by sequence and location, late steps, cost)."""
    m = json.load(open(EVIDENCE))["metrics"]
    ordered, stocked, scrapped = (int(x) for x in m["wo.qty"]["ordered/stocked/scrapped"].split("/"))
    cur = conn.cursor()
    cur.execute("""SELECT COUNT(*), SUM(order_quantity), SUM(stocked_quantity), SUM(scrapped_quantity), SUM(on_time_flag), SUM(1 - on_time_flag),
                          SUM(CASE WHEN scrapped_quantity > 0 THEN 1 ELSE 0 END), SUM(CASE WHEN product_key IS NULL THEN 1 ELSE 0 END), SUM(1 - closed_flag)
                   FROM dw.fact_work_order WHERE source = 'sql'""")
    n, o, st, sc, on_time, late, with_scrap, no_product, still_open = cur.fetchone()
    assert n == m["wo.state"]["closed_on_time"] + m["wo.state"]["closed_late"] == 72591
    assert (o, st, sc) == (ordered, stocked, scrapped)
    assert (on_time, late) == (m["wo.state"]["closed_on_time"], m["wo.state"]["closed_late"])
    assert with_scrap == m["wo.with_scrap"]["all"] and no_product == 0 and still_open == 0
    cur.execute("""SELECT r.scrap_reason_name, COUNT(*) FROM dw.fact_work_order f JOIN dw.dim_scrap_reason r ON r.scrap_reason_key = f.scrap_reason_key
                   WHERE f.source = 'sql' GROUP BY r.scrap_reason_name""")
    assert dict(cur.fetchall()) == m["wo.scrap_reason"]
    cur.execute("SELECT COUNT(*) FROM dw.dim_scrap_reason"); assert cur.fetchone()[0] == 16
    cur.execute("""SELECT COUNT(DISTINCT p.product_id) FROM dw.fact_work_order f JOIN dw.dim_product p ON p.product_key = f.product_key WHERE f.source = 'sql'""")
    assert cur.fetchone()[0] == m["wo.products"]["distinct"]
    # routing: steps by "sequence:location", late steps, planned / actual cost
    cur.execute("""SELECT CAST(r.operation_sequence AS varchar(4)) || ':' || l.location_name, COUNT(*) FROM dw.fact_work_order_routing r
                   JOIN dw.dim_location l ON l.location_key = r.location_key WHERE r.source = 'sql' GROUP BY 1""")
    assert dict(cur.fetchall()) == m["wor.location"]
    cur.execute("""SELECT COUNT(DISTINCT work_order_id), SUM(late_flag), SUM(planned_cost), SUM(actual_cost), SUM(CASE WHEN product_key IS NULL THEN 1 ELSE 0 END)
                   FROM dw.fact_work_order_routing WHERE source = 'sql'""")
    wos, late_ops, planned, actual, orphan = cur.fetchone()
    assert wos == m["wo.with_routing"]["all"] and late_ops == m["wor.late_ops"]["ActualEndDate>ScheduledEndDate"] and orphan == 0
    p_ev, a_ev = (int(x) for x in m["wor.cost"]["planned/actual"].split("/"))
    assert abs(planned - p_ev) < 1 and abs(actual - a_ev) < 1          # SQL Server CAST(SUM AS bigint) truncates
    # the view aggregates the fact exactly (same definitions as the app's production floor)
    cur.execute("SELECT SUM(work_orders), SUM(scrapped_quantity), SUM(on_time), SUM(closed) FROM dw.v_production_scrap_on_time")
    assert cur.fetchone() == (72591, scrapped, m["wo.state"]["closed_on_time"], 72591)
    cur.execute("SELECT COUNT(*) FROM dw.v_production_scrap_on_time WHERE scrap_rate < 0 OR scrap_rate > 1 OR on_time_rate < 0 OR on_time_rate > 1")
    assert cur.fetchone()[0] == 0

def test_c2_4_app_work_order_reaches_the_star(conn):
    """A work order written by the app (ProductionRepository.CreatePlan + CompletePlan item shapes) lands via zero-ETL: a fact row
    with WO-DDB number, late flag and days late, its routing steps, the view counts it as an app work order, and the completion's
    TransactionHistory W moves (+product, -component) reach FactProductInventory."""
    cur = conn.cursor()
    app = {"src": "ddb", "src_lsn": "~app"}
    cur.execute("""SELECT (value->'product_assembly_id'->>'N')::int, (value->'component_id'->>'N')::int FROM landing."aw-inventory"
                   WHERE "PK" LIKE 'ASSEMBLY#0%%' AND value->>'type' LIKE '%%BomEdge%%' ORDER BY "PK", "SK" LIMIT 1""")
    pid, comp = cur.fetchone()
    wo = 100000
    cur.execute("""INSERT INTO landing."aw-inventory" ("PK", "SK", value) VALUES ('WO#100000', 'WO', %s::jsonb)""",
                (_j(dict(app, type="WorkOrder", work_order_id=wo, product_id=pid, product_name="p", order_qty=2, stocked_qty=1, scrapped_qty=1, scrap_reason_id=1,
                         start_date="2026-10-13T00:00:00", end_date="2026-10-20T18:00:00", due_date="2026-10-18T00:00:00", modified_date="2026-10-20T18:00:00")),))
    for seq, loc, end in ((1, 50, "2026-10-14T10:00:00"), (2, 60, "2026-10-20T18:00:00")):
        cur.execute("""INSERT INTO landing."aw-inventory" ("PK", "SK", value) VALUES ('WO#100000', %s, %s::jsonb)""",
                    ("ROUTING#%03d#%03d" % (seq, loc), _j(dict(app, type="WorkOrderRouting", work_order_id=wo, product_id=pid, operation_sequence=seq, location_id=loc,
                     scheduled_start_date="2026-10-1%dT00:00:00" % (3 + seq), scheduled_end_date="2026-10-1%dT00:00:00" % (4 + seq), actual_start_date="2026-10-13T00:00:00",
                     actual_end_date=end, actual_resource_hrs=4, planned_cost=49.0, actual_cost=49.0, modified_date=end))))
    for tid, p, q in ((10000060, pid, 1), (10000061, comp, -2)):
        cur.execute("""INSERT INTO landing."aw-inventory" ("PK", "SK", value) VALUES (%s, %s, %s::jsonb)""",
                    ("PRODUCT#%06d" % p, "TXN#2026-10-20T18:00:00#%d" % tid, _j(dict(app, type="InventoryTransaction", transaction_id=tid, product_id=p, reference_order_id=wo,
                     reference_order_line_id=0, transaction_date="2026-10-20T18:00:00", transaction_type="W", quantity=q, actual_cost=0, modified_date="2026-10-20T18:00:00", archived=False))))
    for v in ("work_order", "work_order_routing", "inventory_transaction"):
        cur.execute("REFRESH MATERIALIZED VIEW stg.%s" % v)
    cur.execute("CALL dw.sp_build_star()")
    cur.execute("""SELECT work_order_number, closed_flag, on_time_flag, days_late, source, scrapped_quantity, due_date_key, product_key IS NOT NULL, scrap_reason_key
                   FROM dw.fact_work_order WHERE work_order_id = 100000""")
    assert cur.fetchone() == ("WO-DDB-100000", 1, 0, 2, "ddb", 1, 20261018, True, 1)
    cur.execute("SELECT operation_sequence, late_flag FROM dw.fact_work_order_routing WHERE work_order_id = 100000 ORDER BY 1")
    assert cur.fetchall() == [(1, 0), (2, 1)]
    cur.execute("SELECT MAX(full_date) FROM dw.dim_date"); assert str(cur.fetchone()[0]) >= "2026-12-31"
    cur.execute("SELECT work_orders, app_work_orders, on_time FROM dw.v_production_scrap_on_time WHERE due_year_month = 202610")
    assert cur.fetchone() == (1, 1, 0)
    cur.execute("""SELECT p.product_id, f.units_in FROM dw.fact_product_inventory f JOIN dw.dim_product p ON p.product_key = f.product_key
                   WHERE p.product_id IN (%s, %s) AND f.date_key = 20261020 ORDER BY 1""", (pid, comp))
    assert dict(cur.fetchall()) == {pid: 1, comp: -2}
    cur.execute("SELECT COUNT(*) FROM dw.fact_work_order WHERE source = 'sql'"); assert cur.fetchone()[0] == 72591

EVAL = os.path.join(ROOT, "src/AdventureWorks.Web/Ai/eval.json")

def _norm(rows):
    out = []
    for r in rows:
        out.append(tuple(round(float(x), 4) if isinstance(x, (Decimal, float)) else x for x in r))
    return out

def _close(a, b):
    if len(a) != len(b): return False
    for ra, rb in zip(a, b):
        if len(ra) != len(rb): return False
        for x, y in zip(ra, rb):
            if isinstance(x, float) and isinstance(y, (float, int)):
                if abs(x - y) > max(0.01, abs(y) * 1e-6): return False
            elif x != y: return False
    return True

def test_c2_5_eval_set_mocked_model_matches_reference_queries(conn):
    """C2-5: the 30 ask-the-data questions. The mocked model's SQL (dw.v_* views only, wrapped exactly like SqlGuard does with
    LIMIT 200) runs as a read-only role that can see nothing but the three views, in a read-only transaction with a statement
    timeout; its results must equal the reference query over the facts and dimensions."""
    qs = json.load(open(EVAL))["questions"]
    assert len(qs) == 30
    cur = conn.cursor()
    cur.execute("CREATE ROLE aw_ai_reader_test NOLOGIN; GRANT USAGE ON SCHEMA dw TO aw_ai_reader_test; "
                "GRANT SELECT ON dw.v_sales, dw.v_vendor_performance, dw.v_production_scrap_on_time TO aw_ai_reader_test")
    failures = []
    for q in qs:
        cur.execute(q["expected"]); expected = _norm(cur.fetchall())
        cur.execute("SAVEPOINT ai; SET LOCAL ROLE aw_ai_reader_test; SET LOCAL statement_timeout = 15000")
        cur.execute("SELECT * FROM (%s) AS q LIMIT 200" % q["sql"]); got = _norm(cur.fetchall())
        cur.execute("RESET ROLE; RELEASE SAVEPOINT ai")
        assert expected, "reference query %d returned no rows" % q["id"]
        if not _close(got, expected): failures.append((q["id"], q["question"], got[:3], expected[:3]))
    assert not failures, failures

def test_c2_5_ai_reader_cannot_touch_anything_else(conn):
    cur = conn.cursor()
    cur.execute("CREATE ROLE aw_ai_reader_test2 NOLOGIN; GRANT USAGE ON SCHEMA dw TO aw_ai_reader_test2; GRANT SELECT ON dw.v_sales TO aw_ai_reader_test2")
    for sql in ("SELECT COUNT(*) FROM dw.fact_internet_sales", "SELECT COUNT(*) FROM dw.dim_customer", "DELETE FROM dw.fact_internet_sales",
                "SELECT COUNT(*) FROM landing.\"aw-sales\"", "CREATE TABLE dw.x (a int)"):
        cur.execute("SAVEPOINT p; SET LOCAL ROLE aw_ai_reader_test2")
        with pytest.raises(Exception):
            cur.execute(sql)
        cur.execute("ROLLBACK TO SAVEPOINT p")
    cur.execute("SAVEPOINT p; SET LOCAL ROLE aw_ai_reader_test2; SET LOCAL transaction_read_only = on")
    cur.execute("SELECT COUNT(*) FROM dw.v_sales"); assert cur.fetchone()[0] > 0
    cur.execute("ROLLBACK TO SAVEPOINT p")


def _forecast(h):
    """The app's Forecast.Step (src/AdventureWorks.Web/Ai/Reorder.cs), one step ahead."""
    n = len(h); k = min(3, n); mean3 = sum(h[n - k:]) / k
    if n < 12:
        return mean3
    last3 = sum(h[n - 3:]); prev3 = sum(h[n - 15:n - 12]) if n >= 15 else 0
    g = 1.0 if prev3 <= 0 else min(2.0, max(0.5, last3 / prev3))
    return 0.5 * h[n - 12] * g + 0.5 * mean3


def test_c2_6_demand_view_and_forecast_backtest(conn):
    """v_product_demand_monthly sums the sales facts exactly; one-step backtest of the INV-07 forecast over the last 12 months
    of history, for products with 24+ months: WAPE vs the 12-month mean baseline (the numbers go in the C2-6 docs)."""
    cur = conn.cursor()
    cur.execute("SELECT SUM(units) FROM dw.v_product_demand_monthly")
    total = cur.fetchone()[0]
    cur.execute("SELECT (SELECT SUM(order_quantity) FROM dw.fact_internet_sales) + (SELECT SUM(order_quantity) FROM dw.fact_reseller_sales)")
    assert total == cur.fetchone()[0]
    cur.execute("SELECT product_id, calendar_year * 12 + month_number_of_year - 1, units FROM dw.v_product_demand_monthly ORDER BY 1, 2")
    series = {}
    for pid, m, u in cur.fetchall():
        series.setdefault(pid, {})[m] = float(u)
    err_f = err_b = actual = 0.0; products = 0
    for pid, by in series.items():
        lo, hi = min(by), max(by)
        h = [by.get(m, 0.0) for m in range(lo, hi + 1)]
        if len(h) < 24:
            continue
        products += 1
        for t in range(len(h) - 12, len(h)):
            past = h[:t]; y = h[t]
            err_f += abs(_forecast(past) - y); err_b += abs(sum(past[-12:]) / 12 - y); actual += y
    wape_f, wape_b = err_f / actual, err_b / actual
    line = "C2-6 backtest: products=%d WAPE forecast=%.3f baseline=%.3f" % (products, wape_f, wape_b)
    print(line)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a").write(line + "\n")
    assert products >= 50
    assert wape_f < 1.0 and wape_b < 1.5


def test_c2_6_affinity_view_is_symmetric(conn):
    cur = conn.cursor()
    cur.execute("""SELECT COUNT(*) FROM dw.v_product_affinity a LEFT JOIN dw.v_product_affinity b
                   ON b.product_id = a.other_product_id AND b.other_product_id = a.product_id WHERE b.orders IS NULL OR b.orders <> a.orders""")
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT COUNT(DISTINCT product_id) FROM dw.v_product_affinity")
    assert cur.fetchone()[0] >= 100
