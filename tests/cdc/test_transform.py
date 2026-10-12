"""Unit tests for the CDC transform (no SQL Server / DynamoDB needed)."""
import datetime, decimal, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "cdc"))
from awcdc import transform as T

NOW = 1_800_000_000.0
M = T.load_json(T.default_mapping_path())


class FakeRows:
    """Stands in for SqlRows: current() returns the row registry, from_image() returns the image as is."""
    def __init__(self):
        self.db = {}
        self.children = {}
    def current(self, table, image):
        pk = tuple(image[c] for c in M["sources"][table]["primary_key"])
        return self.db.get((table, pk))
    def from_image(self, table, image):
        return dict(image)
    def by_columns(self, table, values):
        return [r for (t, _), r in self.db.items() if t == table and all(r.get(k) == v for k, v in values.items())]
    def set(self, table, row):
        pk = tuple(row[c] for c in M["sources"][table]["primary_key"]); self.db[(table, pk)] = row
    def drop(self, table, row):
        self.db.pop((table, tuple(row[c] for c in M["sources"][table]["primary_key"])), None)


def lsn(n):
    return "0x%020x" % n


def order(**kw):
    r = dict(SalesOrderID=43659, RevisionNumber=8, OrderDate=datetime.datetime(2022, 5, 30), DueDate=datetime.datetime(2022, 6, 11),
             ShipDate=None, Status=5, OnlineOrderFlag=False, SalesOrderNumber="SO43659", PurchaseOrderNumber="PO522145787",
             AccountNumber="10-4020-000676", CustomerID=29825, SalesPersonID=279, TerritoryID=5, BillToAddressID=985,
             ShipToAddressID=985, ShipMethodID=5, CreditCardID=16281, CreditCardApprovalCode="105041Vi84182", CurrencyRateID=None,
             SubTotal=decimal.Decimal("20565.6206"), TaxAmt=decimal.Decimal("1971.5149"), Freight=decimal.Decimal("616.0984"),
             TotalDue=decimal.Decimal("23153.2339"), Comment=None, ModifiedDate=datetime.datetime(2022, 6, 6))
    r.update(kw); return r


def setup():
    rows, sink = FakeRows(), T.MemorySink()
    return rows, sink, T.Transformer(rows, sink, mapping=M, rules=T.load_refresh_rules(), clock=lambda: NOW)


def test_insert_writes_all_items_for_row():
    rows, sink, tr = setup(); r = order(); rows.set("Sales.SalesOrderHeader", r)
    rep = tr.apply(T.Change("Sales.SalesOrderHeader", "c", lsn(10), after=r))
    keys = sorted((i["PK"], i["SK"]) for _, i in rep["puts"])
    assert keys == [("CCAPPROVAL#105041Vi84182", "ORDER#0000043659"), ("ORDER#0000043659", "ORDER"), ("PONUMBER#PO522145787", "ORDER#0000043659")]
    hdr = sink.get("aw-sales", "ORDER#0000043659", "ORDER")
    assert hdr["src_lsn"] == lsn(10) and hdr["src_table"] == "Sales.SalesOrderHeader" and hdr["src_pk"] == "SalesOrderID=43659"
    assert hdr["GSI1PK"] == "CUSTOMER#029825" and "GSI2PK" not in hdr or hdr["GSI2PK"] == "ORDERSTATUS#5"


def test_update_ordering_older_and_replayed_events_ignored():
    rows, sink, tr = setup(); r = order(Comment="v2"); rows.set("Sales.SalesOrderHeader", r)
    tr.apply(T.Change("Sales.SalesOrderHeader", "u", lsn(20), before=order(), after=r))
    rows.set("Sales.SalesOrderHeader", order(Comment="stale"))
    rep = tr.apply(T.Change("Sales.SalesOrderHeader", "u", lsn(15), before=order(), after=order(Comment="stale")))
    assert rep["skipped"] >= 1 and sink.get("aw-sales", "ORDER#0000043659", "ORDER")["comment"] == "v2"
    rows.set("Sales.SalesOrderHeader", order(Comment="v2"))
    rep = tr.apply(T.Change("Sales.SalesOrderHeader", "u", lsn(20), before=order(), after=order(Comment="v2")))
    assert rep["puts"] == []  # replay of the same position is a no-op


def test_key_move_on_update_tombstones_old_derived_item():
    rows, sink, tr = setup(); old = order(); new = order(PurchaseOrderNumber="PO-NEW")
    rows.set("Sales.SalesOrderHeader", old); tr.apply(T.Change("Sales.SalesOrderHeader", "c", lsn(1), after=old))
    rows.set("Sales.SalesOrderHeader", new)
    rep = tr.apply(T.Change("Sales.SalesOrderHeader", "u", lsn(2), before=old, after=new))
    assert [i["PK"] for _, i in rep["tombstones"]] == ["PONUMBER#PO522145787"]
    assert sink.get("aw-sales", "PONUMBER#PO-NEW", "ORDER#0000043659")["src_lsn"] == lsn(2)


def test_delete_becomes_tombstones_with_7_day_ttl():
    rows, sink, tr = setup(); r = order(); rows.set("Sales.SalesOrderHeader", r)
    tr.apply(T.Change("Sales.SalesOrderHeader", "c", lsn(1), after=r)); rows.drop("Sales.SalesOrderHeader", r)
    rep = tr.apply(T.Change("Sales.SalesOrderHeader", "d", lsn(2), before=r))
    assert len(rep["tombstones"]) == 3
    t = sink.get("aw-sales", "ORDER#0000043659", "ORDER")
    assert t["deleted"] is True and t["ttl"] == int(NOW) + 7 * 86400 and "GSI1PK" not in t and t["src_lsn"] == lsn(2)


def test_out_of_order_delete_before_insert():
    """Delete (newer) arrives before the insert (older): the late insert must not resurrect the row."""
    rows, sink, tr = setup(); r = order()
    tr.apply(T.Change("Sales.SalesOrderHeader", "d", lsn(9), before=r))
    rows.set("Sales.SalesOrderHeader", r)
    tr.apply(T.Change("Sales.SalesOrderHeader", "c", lsn(5), after=r))
    assert sink.get("aw-sales", "ORDER#0000043659", "ORDER")["deleted"] is True


def test_multi_item_row_product():
    rows, sink, tr = setup()
    p = dict(ProductID=680, Name="HL Road Frame - Black, 58", ProductNumber="FR-R92B-58", MakeFlag=True, FinishedGoodsFlag=True,
             Color="Black", SafetyStockLevel=500, ReorderPoint=375, StandardCost=decimal.Decimal("1059.31"), ListPrice=decimal.Decimal("1431.50"),
             Size="58", ProductSubcategoryID=14, ProductModelID=6, SellStartDate=datetime.datetime(2008, 4, 30), SellEndDate=None,
             DiscontinuedDate=None, ModifiedDate=datetime.datetime(2014, 2, 8), subcategory_name="Road Frames", category_id=2,
             category_name="Components", model_name="HL Road Frame", stock_qty=100, x_active="A", x_name_lower="hl road frame - black, 58")
    rows.set("Production.Product", p)
    rep = tr.apply(T.Change("Production.Product", "c", lsn(3), after=p))
    types = sorted(i["type"] for _, i in rep["puts"])
    assert "Product" in types and "ProductNameIndex" in types and len(types) >= 3
    assert sink.get("aw-catalog", "PRODUCTNAMES", "hl road frame - black, 58")["derived"] is True


def test_snapshot_refresh_updates_copy_without_moving_src_lsn():
    rows, sink, tr = setup()
    sub = dict(ProductSubcategoryID=14, ProductCategoryID=2, Name="Road Frames", category_name="Components", ModifiedDate=datetime.datetime(2008, 4, 30))
    rows.set("Production.ProductSubcategory", sub); tr.apply(T.Change("Production.ProductSubcategory", "c", lsn(1), after=sub))
    cat = dict(ProductCategoryID=2, Name="Parts", ModifiedDate=datetime.datetime(2026, 1, 1))
    rows.set("Production.ProductCategory", cat); rows.set("Production.ProductSubcategory", dict(sub, category_name="Parts"))
    rep = tr.apply(T.Change("Production.ProductCategory", "u", lsn(7), before=dict(cat, Name="Components"), after=cat))
    s = sink.get("aw-catalog", "CATALOG", "CAT#0002#SUB#0014")
    assert rep["refreshed"] >= 1 and s["category_name"] == "Parts" and s["src_lsn"] == lsn(1)


def test_refresh_never_resurrects_tombstone():
    sink = T.MemorySink(); sink.put("t", {"PK": "A", "SK": "B", "deleted": True, "src_lsn": lsn(2)}, lsn(2))
    assert sink.refresh("t", {"PK": "A", "SK": "B", "name": "x", "updated_at": "z"}) == 0


def test_debezium_event_normalisation():
    types = lambda t: [{"name": "SalesOrderID", "st": "int"}, {"name": "OrderDate", "st": "datetime"}, {"name": "TotalDue", "st": "money"},
                       {"name": "rowguid", "st": "uniqueidentifier"}, {"name": "OrganizationNode", "st": "hierarchyid"}]
    ev = {"payload": {"op": "u", "before": {"SalesOrderID": 1, "OrderDate": 0, "TotalDue": "1.5000", "OrganizationNode": "Wg=="},
                      "after": {"SalesOrderID": 1, "OrderDate": 86400000, "TotalDue": "2.0000", "OrganizationNode": "Wg=="},
                      "source": {"schema": "Sales", "table": "SalesOrderHeader", "change_lsn": "0000002b:00000348:0002", "ts_ms": 5}}}
    ch = T.from_debezium(ev, types)
    assert ch.table == "Sales.SalesOrderHeader" and ch.position == "0x0000002b000003480002" and ch.op == "u"
    assert ch.after["OrderDate"] == datetime.datetime(1970, 1, 2) and ch.after["TotalDue"] == decimal.Decimal("2.0000")
    assert ch.after["OrganizationNode"] == b"Z"
    assert T.lsn_from_debezium("ffffffff:ffffffff:ffff") > T.LOAD_LSN if hasattr(T, "LOAD_LSN") else True


def test_dms_record_normalisation_and_position_order():
    types = lambda t: [{"name": "SalesOrderID", "st": "int"}, {"name": "OrderDate", "st": "datetime"}]
    rec = lambda seq, op: {"metadata": {"schema-name": "Sales", "table-name": "SalesOrderHeader", "operation": op, "timestamp": "2026-10-11T22:00:00.000000Z"},
                           "data": {"SalesOrderID": 1, "OrderDate": "2026-10-11T21:59:59", "AR_H_CHANGE_SEQ": seq}}
    a = T.from_dms(rec("20261011220000000000000000000000001", "update"), types)
    b = T.from_dms(rec("20261011220000000000000000000000002", "delete"), types)
    assert a.position < b.position and a.position > "0x" + "0" * 20 and b.op == "d" and b.before["SalesOrderID"] == 1


XML = ('<IndividualSurvey xmlns="http://schemas.microsoft.com/sqlserver/2004/07/adventure-works/IndividualSurvey">'
       '<TotalPurchaseYTD>-3307.7544</TotalPurchaseYTD></IndividualSurvey>')


def test_xml_demographics_identical_via_bulk_load_and_cdc():
    """Person.Demographics (xml) must become the same map whether loaded in bulk (mapping.yaml) or via CDC (mapping.json)."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "loader"))
    import awmap
    y = awmap.load_mapping()["sources"]["Person.Person"]
    row = dict(BusinessEntityID=293, PersonType="IN", NameStyle=False, Title=None, FirstName="Catherine", MiddleName="R.",
               LastName="Abel", Suffix=None, EmailPromotion=1, AdditionalContactInfo=None, Demographics=XML,
               rowguid="x", ModifiedDate=datetime.datetime(2022, 1, 1))
    bulk = awmap.items_for_row("Person.Person", y, row, ["BusinessEntityID"], lsn(1), "t")
    rows, sink, tr = setup(); rows.set("Person.Person", row)
    rep = tr.apply(T.Change("Person.Person", "u", lsn(1), before=row, after=row))
    cdc = [(t, dict(i, updated_at="t")) for t, i in rep["puts"]]
    assert cdc == bulk
    person = [i for _, i in cdc if i["type"] == "Person"][0]
    assert person["demographics"] == {"total_purchase_ytd": "-3307.7544"}


def _product(**kw):
    p = dict(ProductID=680, Name="HL Road Frame - Black, 58", ProductNumber="FR-R92B-58", MakeFlag=True, FinishedGoodsFlag=True,
             Color="Black", SafetyStockLevel=500, ReorderPoint=375, StandardCost=decimal.Decimal("1059.31"), ListPrice=decimal.Decimal("1431.50"),
             Size="58", ProductSubcategoryID=14, ProductModelID=6, SellStartDate=datetime.datetime(2008, 4, 30), SellEndDate=None,
             DiscontinuedDate=None, ModifiedDate=datetime.datetime(2014, 2, 8), subcategory_name="Road Frames", category_id=2,
             category_name="Components", model_name="HL Road Frame", stock_qty=100, x_active="A", x_name_lower="hl road frame - black, 58")
    p.update(kw); return p


def test_refresh_removes_copy_when_source_becomes_null():
    rows, sink, tr = setup(); p = _product(); rows.set("Production.Product", p)
    tr.apply(T.Change("Production.Product", "c", lsn(1), after=p))
    assert sink.get("aw-catalog", "PRODUCT#000680", "PRODUCT")["model_name"] == "HL Road Frame"
    rows.set("Production.Product", _product(model_name=None))  # e.g. the model row lost its name/link
    model = dict(ProductModelID=6, Name="HL Road Frame", ModifiedDate=datetime.datetime(2026, 1, 1))
    rep = tr.apply(T.Change("Production.ProductModel", "u", lsn(5), before=model, after=model))
    item = sink.get("aw-catalog", "PRODUCT#000680", "PRODUCT")
    assert rep["refreshed"] >= 1 and "model_name" not in item and item["src_lsn"] == lsn(1)


def test_dynamodb_sink_refresh_emits_remove():
    calls = {}
    class Tbl:
        meta = type("M", (), {"client": type("C", (), {"exceptions": type("E", (), {"ConditionalCheckFailedException": KeyError})})})
        def update_item(self, **kw):
            calls.update(kw)
    sink = T.DynamoDBSink(type("R", (), {"Table": lambda self, n: Tbl()})())
    assert sink.refresh("aw-catalog", {"PK": "P", "SK": "S", "name": "x", "updated_at": "t"}, remove=["model_name"]) == 1
    assert calls["UpdateExpression"].endswith("REMOVE #r0") and calls["ExpressionAttributeNames"]["#r0"] == "model_name"
    assert "attribute_not_exists(deleted)" in calls["ConditionExpression"]
