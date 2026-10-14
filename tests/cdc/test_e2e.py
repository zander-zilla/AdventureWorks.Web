"""End-to-end: demo app (before stack) -> SQL Server -> CDC -> Debezium -> awcdc -> DynamoDB Local.
Requires scripts/cdc-up.sh to have run (and the before app on :5080). Run with:  AW_E2E=1 pytest tests/cdc/test_e2e.py"""
import http.cookiejar, json, os, re, subprocess, sys, time, urllib.parse, urllib.request
import pytest
from boto3.dynamodb.conditions import Key
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "loader"))

pytestmark = pytest.mark.skipif(os.environ.get("AW_E2E") != "1", reason="set AW_E2E=1 with the cdc stack running")
APP = os.environ.get("AW_APP", "http://localhost:5080")
CDC = os.environ.get("AW_CDC", "http://localhost:8090")
WAIT_S = int(os.environ.get("AW_E2E_WAIT", "60"))
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RESULTS = os.environ.get("AW_E2E_RESULTS", "/tmp/cdc-e2e.json")


def browser():
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    def get(path):
        return op.open(APP + path, timeout=30).read().decode()
    def post(path, data):
        return op.open(APP + path, urllib.parse.urlencode(data).encode(), timeout=30).read().decode()
    return get, post


def token(html):
    return re.search(r'name="__RequestVerificationToken" type="hidden" value="([^"]+)"', html).group(1)


def wait_for(fn, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = fn()
        if v:
            return v, time.time() - t0
        time.sleep(0.25)
    raise AssertionError("timed out after %ss" % timeout)


def test_demo_order_replicates_and_reset_tombstones():
    import ddb
    os.environ.setdefault("DDB_MULTI", "1")
    sales = ddb.resource().Table("aw-sales")
    get, post = browser()
    post("/Account/Login", {"email": "catherine0@adventure-works.com", "password": "Demo!2026", "__RequestVerificationToken": token(get("/Account/Login"))})
    shop = get("/Shop")
    pid = re.search(r'name="productId" value="(\d+)"', shop).group(1)
    t_order = time.time()
    page = post("/Shop/Order", {"productId": pid, "quantity": "2", "__RequestVerificationToken": token(shop)})
    oid = int(re.findall(r"SO(\d+)", page)[0])
    pk = "ORDER#%010d" % oid

    def order_items():
        items = sales.query(KeyConditionExpression=Key("PK").eq(pk), ConsistentRead=True)["Items"]
        hdr = [i for i in items if i["SK"] == "ORDER"]
        lines = [i for i in items if i["SK"].startswith("LINE#")]
        return (hdr[0], lines) if hdr and lines and hdr[0].get("total_due", 0) > 0 else None
    (hdr, lines), lag_insert = wait_for(order_items, WAIT_S)
    lag_insert = time.time() - t_order
    assert hdr["type"] == "Order" and hdr["customer_id"] == 29485 and hdr["comment"] == "demo-order" and hdr["src"] == "sql"
    assert hdr["GSI1PK"] == "CUSTOMER#029485" and hdr["GSI1SK"].startswith("ORDER#") and hdr["GSI1SK"].endswith("%010d" % oid)
    assert hdr["GSI2PK"] == "ORDERSTATUS#1"
    assert len(lines) == 1 and lines[0]["type"] == "OrderLine" and lines[0]["order_qty"] == 2 and lines[0]["product_id"] == int(pid)
    assert lines[0]["product_name"]  # snapshot copied at order time

    # reset-demo deletes -> tombstones (D10, TTL 7 days P3-4)
    t_reset = time.time()
    subprocess.run(["docker", "exec", "aw-before-sqlserver-1", "/opt/mssql-tools18/bin/sqlcmd", "-C", "-S", "localhost", "-U", "sa",
                    "-P", os.environ.get("MSSQL_SA_PASSWORD", "AdvWorks!2026"), "-b", "-Q", open(os.path.join(ROOT, "scripts", "reset-demo.sql")).read()],
                   text=True, check=True, capture_output=True)

    def tombstoned():
        items = sales.query(KeyConditionExpression=Key("PK").eq(pk), ConsistentRead=True)["Items"]
        return items if items and all(i.get("deleted") for i in items) else None
    items, _ = wait_for(tombstoned, WAIT_S)
    lag_delete = time.time() - t_reset
    for i in items:
        assert "GSI1PK" not in i and int(i["ttl"]) - time.time() > 6.9 * 86400
    status = json.load(urllib.request.urlopen(CDC + "/api/status"))
    json.dump({"order_id": oid, "end_to_end_insert_s": round(lag_insert, 2), "end_to_end_delete_s": round(lag_delete, 2),
               "consumer_lag_ms": status["lag_ms"], "dlq": status["dlq"]}, open(RESULTS, "w"), indent=1)
    assert status["dlq"] == 0


def test_synthetic_trickle_replicates_through_cdc():
    """C2-7: the daily trickle inserts generated days into SQL Server; CDC carries them to DynamoDB like any other write,
    marked syn = 1 (the reconcile step after this test then checks SQL vs DynamoDB exactly, generated rows included)."""
    import ddb
    sys.path.insert(0, os.path.join(ROOT, "scripts", "synthetic"))
    import generate as G, load_sql
    os.environ.setdefault("DDB_MULTI", "1")
    t0 = time.time()
    r = load_sql.run(G.ORIGIN + __import__("datetime").timedelta(days=1), mode="trickle", log=lambda *_: None)
    assert r["batches"] == 2 and r["rows"] > 500
    first = G.Generator().day(G.ORIGIN)
    oid = first.rows["Sales.SalesOrderHeader"][0]["SalesOrderID"]; cid = first.rows["Sales.Customer"][0]["CustomerID"]
    sales, cust = ddb.resource().Table("aw-sales"), ddb.resource().Table("aw-customer")

    def replicated():
        h = sales.get_item(Key={"PK": "ORDER#%010d" % oid, "SK": "ORDER"}, ConsistentRead=True).get("Item")
        c = cust.get_item(Key={"PK": "BE#%06d" % cid, "SK": "PERSON"}, ConsistentRead=True).get("Item")
        return (h, c) if h and c else None
    (h, c), _ = wait_for(replicated, WAIT_S * 3)
    assert h["syn"] == 1 and c["syn"] == 1 and h["src"] == "sql" and h["src_lsn"] != "0x" + "0" * 20
    # the reconcile step after this test compares every row: wait until the whole of both days has been applied
    # (the consumer applies a generated day in ~1-3 min on a CI runner; the first order arrives within seconds)
    last = G.Generator().range(G.ORIGIN, G.ORIGIN + __import__("datetime").timedelta(days=1))
    lo = max(r["SalesOrderID"] for r in last.rows["Sales.SalesOrderHeader"])
    lc = max(r["CustomerID"] for r in last.rows["Sales.Customer"])

    th = max(last.rows["Production.TransactionHistory"], key=lambda r: r["TransactionID"])  # last table of each day
    inv = ddb.resource().Table("aw-inventory")
    seen = {}

    def drained():
        st = json.load(urllib.request.urlopen(CDC + "/api/status"))
        h = sales.get_item(Key={"PK": "ORDER#%010d" % lo, "SK": "ORDER"}, ConsistentRead=True).get("Item")
        c = cust.get_item(Key={"PK": "BE#%06d" % lc, "SK": "PERSON"}, ConsistentRead=True).get("Item")
        t = inv.get_item(Key={"PK": "PRODUCT#%06d" % th["ProductID"], "SK": "TXN#%s#%08d" % (th["TransactionDate"], th["TransactionID"])},
                         ConsistentRead=True).get("Item")
        stable = seen.get("n") == st["applied_events"] and time.time() - seen.get("t", time.time()) >= 10
        if seen.get("n") != st["applied_events"]:
            seen.update(n=st["applied_events"], t=time.time())
        return st if h and c and t and st["queued"] == 0 and stable else None
    wait_for(drained, WAIT_S * 10)
    json.dump({"synthetic_days": r["batches"], "rows": r["rows"], "replicated_s": round(time.time() - t0, 1)}, open("/tmp/cdc-e2e-synthetic.json", "w"))
