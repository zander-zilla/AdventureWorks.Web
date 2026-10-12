"""Unit tests for the CDC transform (no SQL Server / DynamoDB needed)."""
import datetime, decimal, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "cdc"))
from awcdc import transform as T

NOW = 1_800_000_000.0
M = T.load_json(T.default_mapping_path())


class Sleeps(list):
    def __call__(self, secs):
        self.append(round(secs, 3))


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


def seed_order_parents(sink, customer=True):
    """The related items an order header copies from (as the bulk load / earlier CDC events wrote them)."""
    if customer:
        sink.put("aw-customer", {"PK": "BE#001045", "SK": "CUSTOMER#029825", "GSI1PK": "CUSTOMER#029825", "GSI1SK": "CUSTOMER",
                                 "src_table": "Sales.Customer", "src_pk": "CustomerID=29825", "account_number": "AW00029825",
                                 "display_name": "Bike World", "store_name": "Bike World", "src_lsn": lsn(1)}, lsn(1))
    sink.put("aw-reference", {"PK": "SHIPMETHODS", "SK": "SHIPMETHOD#05", "name": "CARGO TRANSPORT 5", "src_lsn": lsn(1)}, lsn(1))
    sink.put("aw-customer", {"PK": "ADDRESS#000985", "SK": "ADDRESS", "address_line1": "6900 Sisk Road", "city": "Modesto",
                             "state_province_code": "CA", "postal_code": "95354", "country_region_code": "US", "src_lsn": lsn(1)}, lsn(1))
    sink.put("aw-customer", {"PK": "CARD#016281", "SK": "CARD", "card_type": "Vista", "card_last4": "0007", "src_lsn": lsn(1)}, lsn(1))


def setup(seed=True, attempts=4):
    sink = T.MemorySink(); sleeps = Sleeps()
    rows = T.Enricher(M, sink, attempts=attempts, backoff_ms=100, sleep=sleeps)
    if seed:
        seed_order_parents(sink)
    tr = T.Transformer(rows, sink, mapping=M, rules=T.load_refresh_rules(), clock=lambda: NOW)
    tr.sleeps = sleeps
    return rows, sink, tr


def test_insert_writes_all_items_for_row():
    rows, sink, tr = setup(); r = order(); 
    rep = tr.apply(T.Change("Sales.SalesOrderHeader", "c", lsn(10), after=r))
    keys = sorted((i["PK"], i["SK"]) for _, i in rep["puts"])
    assert keys == [("CCAPPROVAL#105041Vi84182", "ORDER#0000043659"), ("ORDER#0000043659", "ORDER"), ("PONUMBER#PO522145787", "ORDER#0000043659")]
    hdr = sink.raw("aw-sales", "ORDER#0000043659", "ORDER")
    assert hdr["src_lsn"] == lsn(10) and hdr["src_table"] == "Sales.SalesOrderHeader" and hdr["src_pk"] == "SalesOrderID=43659"
    assert hdr["GSI1PK"] == "CUSTOMER#029825" and "GSI2PK" not in hdr or hdr["GSI2PK"] == "ORDERSTATUS#5"


def test_update_ordering_older_and_replayed_events_ignored():
    rows, sink, tr = setup(); r = order(Comment="v2"); 
    tr.apply(T.Change("Sales.SalesOrderHeader", "u", lsn(20), before=order(), after=r))
    
    rep = tr.apply(T.Change("Sales.SalesOrderHeader", "u", lsn(15), before=order(), after=order(Comment="stale")))
    assert rep["skipped"] >= 1 and sink.raw("aw-sales", "ORDER#0000043659", "ORDER")["comment"] == "v2"
    
    rep = tr.apply(T.Change("Sales.SalesOrderHeader", "u", lsn(20), before=order(), after=order(Comment="v2")))
    assert rep["puts"] == []  # replay of the same position is a no-op


def test_key_move_on_update_tombstones_old_derived_item():
    rows, sink, tr = setup(); old = order(); new = order(PurchaseOrderNumber="PO-NEW")
    tr.apply(T.Change("Sales.SalesOrderHeader", "c", lsn(1), after=old))
    
    rep = tr.apply(T.Change("Sales.SalesOrderHeader", "u", lsn(2), before=old, after=new))
    assert [i["PK"] for _, i in rep["tombstones"]] == ["PONUMBER#PO522145787"]
    assert sink.raw("aw-sales", "PONUMBER#PO-NEW", "ORDER#0000043659")["src_lsn"] == lsn(2)


def test_delete_becomes_tombstones_with_7_day_ttl():
    rows, sink, tr = setup(); r = order(); 
    tr.apply(T.Change("Sales.SalesOrderHeader", "c", lsn(1), after=r))
    rep = tr.apply(T.Change("Sales.SalesOrderHeader", "d", lsn(2), before=r))
    assert len(rep["tombstones"]) == 3
    t = sink.raw("aw-sales", "ORDER#0000043659", "ORDER")
    assert t["deleted"] is True and t["ttl"] == int(NOW) + 7 * 86400 and "GSI1PK" not in t and t["src_lsn"] == lsn(2)


def test_out_of_order_delete_before_insert():
    """Delete (newer) arrives before the insert (older): the late insert must not resurrect the row."""
    rows, sink, tr = setup(); r = order()
    tr.apply(T.Change("Sales.SalesOrderHeader", "d", lsn(9), before=r))
    
    tr.apply(T.Change("Sales.SalesOrderHeader", "c", lsn(5), after=r))
    assert sink.raw("aw-sales", "ORDER#0000043659", "ORDER")["deleted"] is True


def seed_catalog(tr, sink):
    """Category, subcategory, model and two inventory rows replicated through the transform itself."""
    tr.apply(T.Change("Production.ProductCategory", "c", lsn(1), after=dict(ProductCategoryID=2, Name="Components", rowguid="g",
                                                                             ModifiedDate=datetime.datetime(2008, 4, 30))))
    tr.apply(T.Change("Production.ProductSubcategory", "c", lsn(2), after=dict(ProductSubcategoryID=14, ProductCategoryID=2, Name="Road Frames",
                                                                                rowguid="g", ModifiedDate=datetime.datetime(2008, 4, 30))))
    tr.apply(T.Change("Production.ProductModel", "c", lsn(3), after=dict(ProductModelID=6, Name="HL Road Frame", CatalogDescription=None,
                                                                          Instructions=None, rowguid="g", ModifiedDate=datetime.datetime(2008, 4, 30))))
    sink.put("aw-inventory", {"PK": "LOCATION", "SK": "001", "name": "Tool Crib", "src_lsn": lsn(1)}, lsn(1))
    sink.put("aw-inventory", {"PK": "LOCATION", "SK": "006", "name": "Misc Storage", "src_lsn": lsn(1)}, lsn(1))
    for loc, qty in ((1, 60), (6, 40)):
        tr.apply(T.Change("Production.ProductInventory", "c", lsn(4), after=dict(ProductID=680, LocationID=loc, Shelf="A", Bin=1, Quantity=qty,
                                                                                  rowguid="g", ModifiedDate=datetime.datetime(2008, 4, 30))))


def product_image(**kw):
    """Base columns only, as Debezium/DMS deliver them (no joined names, no stock total)."""
    p = dict(ProductID=680, Name="HL Road Frame - Black, 58", ProductNumber="FR-R92B-58", MakeFlag=True, FinishedGoodsFlag=True,
             Color="Black", SafetyStockLevel=500, ReorderPoint=375, StandardCost=decimal.Decimal("1059.31"), ListPrice=decimal.Decimal("1431.50"),
             Size="58", SizeUnitMeasureCode=None, WeightUnitMeasureCode=None, Weight=None, DaysToManufacture=1, ProductLine="R", Class="H",
             Style="U", ProductSubcategoryID=14, ProductModelID=6, SellStartDate=datetime.datetime(2008, 4, 30), SellEndDate=None,
             DiscontinuedDate=None, rowguid="g", ModifiedDate=datetime.datetime(2014, 2, 8))
    p.update(kw); return p


def test_multi_item_row_product_enriched_from_dynamodb():
    rows, sink, tr = setup(); seed_catalog(tr, sink)
    rep = tr.apply(T.Change("Production.Product", "c", lsn(5), after=product_image()))
    types = sorted(i["type"] for _, i in rep["puts"])
    assert "Product" in types and "ProductNameIndex" in types and len(types) >= 3
    assert sink.raw("aw-catalog", "PRODUCTNAMES", "hl road frame - black, 58")["derived"] is True
    p = sink.raw("aw-catalog", "PRODUCT#000680", "PRODUCT")
    assert (p["subcategory_name"], p["category_id"], p["category_name"], p["model_name"], p["stock_qty"]) == ("Road Frames", 2, "Components", "HL Road Frame", 100)
    assert p["GSI1SK"] == "PRODUCT#A#hl road frame - black, 58#000680" and p["active"] == "A"
    assert sink.raw("aw-inventory", "PRODUCT#000680", "PRODUCT")["stock_qty"] == 100


def test_snapshot_refresh_updates_copy_without_moving_src_lsn():
    rows, sink, tr = setup(); seed_catalog(tr, sink)
    tr.apply(T.Change("Production.Product", "c", lsn(5), after=product_image()))
    cat = dict(ProductCategoryID=2, Name="Parts", rowguid="g", ModifiedDate=datetime.datetime(2026, 1, 1))
    rep = tr.apply(T.Change("Production.ProductCategory", "u", lsn(7), before=dict(cat, Name="Components"), after=cat))
    s = sink.raw("aw-catalog", "CATALOG", "CAT#0002#SUB#0014")
    p = sink.raw("aw-catalog", "PRODUCT#000680", "PRODUCT")
    assert rep["refreshed"] >= 2 and s["category_name"] == "Parts" and s["src_lsn"] == lsn(2)
    assert p["category_name"] == "Parts" and p["src_lsn"] == lsn(5) and p["subcategory_name"] == "Road Frames"


def test_inventory_change_refreshes_product_stock_total():
    rows, sink, tr = setup(); seed_catalog(tr, sink)
    tr.apply(T.Change("Production.Product", "c", lsn(5), after=product_image()))
    inv = dict(ProductID=680, LocationID=6, Shelf="A", Bin=1, Quantity=5, rowguid="g", ModifiedDate=datetime.datetime(2026, 1, 1))
    tr.apply(T.Change("Production.ProductInventory", "u", lsn(8), before=dict(inv, Quantity=40), after=inv))
    assert sink.raw("aw-catalog", "PRODUCT#000680", "PRODUCT")["stock_qty"] == 65
    assert sink.raw("aw-inventory", "PRODUCT#000680", "PRODUCT")["stock_qty"] == 65


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
    rows, sink, tr = setup(); 
    rep = tr.apply(T.Change("Person.Person", "u", lsn(1), before=row, after=row))
    cdc = [(t, dict(i, updated_at="t")) for t, i in rep["puts"]]
    assert cdc == bulk
    person = [i for _, i in cdc if i["type"] == "Person"][0]
    assert person["demographics"] == {"total_purchase_ytd": "-3307.7544"}


def address(**kw):
    a = dict(AddressID=985, AddressLine1="6900 Sisk Road", AddressLine2="Suite 2", City="Modesto", StateProvinceID=9,
             PostalCode="95354", SpatialLocation=bytes.fromhex("e6100000010cae8bfc28bce44740" "67a8918989" "8a5ec0"),
             rowguid="g", ModifiedDate=datetime.datetime(2014, 9, 12))
    a.update(kw); return a


def test_refresh_removes_copy_when_source_becomes_null():
    rows, sink, tr = setup(seed=False)
    sink.put("aw-reference", {"PK": "COUNTRY#US", "SK": "STATE#CA", "GSI1PK": "STATE#009", "GSI1SK": "STATE", "name": "California",
                              "state_province_code": "CA", "country_region_code": "US", "src_lsn": lsn(1)}, lsn(1))
    sink.put("aw-customer", {"PK": "LOOKUP#ADDRESSTYPE", "SK": "02", "name": "Home", "src_lsn": lsn(1)}, lsn(1))
    tr.apply(T.Change("Person.Address", "c", lsn(2), after=address()))
    a = sink.raw("aw-customer", "ADDRESS#000985", "ADDRESS")
    assert a["state_province_code"] == "CA" and abs(a["latitude"] - decimal.Decimal("47.7869921906598")) < decimal.Decimal("1e-9")
    tr.apply(T.Change("Person.BusinessEntityAddress", "c", lsn(3), after=dict(BusinessEntityID=1045, AddressID=985, AddressTypeID=2,
                                                                               rowguid="g", ModifiedDate=datetime.datetime(2014, 9, 12))))
    link = sink.raw("aw-customer", "BE#001045", "ADDRESS#02#000985")
    assert link["address_line2"] == "Suite 2" and link["address_type"] == "Home"
    assert sink.raw("aw-purchasing", "VENDOR#001045", "ADDRESS#02#000985") is None  # not a vendor (EXISTS flag 0)
    rep = tr.apply(T.Change("Person.Address", "u", lsn(5), before=address(), after=address(AddressLine2=None, City="Salida")))
    link = sink.raw("aw-customer", "BE#001045", "ADDRESS#02#000985")
    assert rep["refreshed"] == 1 and "address_line2" not in link and link["city"] == "Salida" and link["src_lsn"] == lsn(3)


# ---------------------------------------------------------------- related items in DynamoDB, out-of-order arrival

def customer_image():
    return dict(CustomerID=29825, PersonID=None, StoreID=1045, TerritoryID=5, rowguid="g", ModifiedDate=datetime.datetime(2014, 9, 12))


def seed_store(tr, sink):
    sink.put("aw-sales", {"PK": "TERRITORY#05", "SK": "TERRITORY", "name": "Southeast", "src_lsn": lsn(1)}, lsn(1))
    tr.apply(T.Change("Sales.Store", "c", lsn(2), after=dict(BusinessEntityID=1045, Name="Bike World", SalesPersonID=None, Demographics=None,
                                                              rowguid="g", ModifiedDate=datetime.datetime(2014, 9, 12))))


def test_order_header_enriched_from_replicated_items():
    rows, sink, tr = setup()
    tr.apply(T.Change("Sales.SalesOrderHeader", "c", lsn(10), after=order()))
    h = sink.raw("aw-sales", "ORDER#0000043659", "ORDER")
    assert (h["customer_name"], h["customer_account_number"], h["ship_method_name"], h["ship_to_city"], h["bill_to_state"], h["card_last4"]) == \
        ("Bike World", "AW00029825", "CARGO TRANSPORT 5", "Modesto", "CA", "0007")
    assert "currency_from" not in h  # CurrencyRateID NULL: LEFT JOIN, no lookup, no wait
    assert h["sales_order_number"] == "SO43659" and h["total_due"] == decimal.Decimal("23153.2339")
    assert tr.sleeps == []


def test_out_of_order_order_before_customer_retries_then_fails_for_dlq():
    """Order header arrives before its customer: bounded retry with backoff, then MissingParent (-> batch retry / DLQ);
    nothing is written. When the customer has replicated, the redelivered order succeeds."""
    rows, sink, tr = setup(seed=False, attempts=4); seed_order_parents(sink, customer=False); seed_store(tr, sink)
    try:
        tr.apply(T.Change("Sales.SalesOrderHeader", "c", lsn(10), after=order()))
        raise AssertionError("expected MissingParent")
    except T.MissingParent as e:
        assert "CUSTOMER#029825" in str(e)
    assert tr.sleeps == [0.1, 0.2, 0.4] and rows.stats["missing"] == 1
    assert not [k for k in sink.tables.get("aw-sales", {}) if "0000043659" in k[0] + k[1]]  # nothing written
    # the customer change (older LSN, other shard/partition) is applied, then the order is redelivered
    tr.apply(T.Change("Sales.Customer", "c", lsn(9), after=customer_image()))
    c = sink.raw("aw-customer", "BE#001045", "CUSTOMER#029825")
    assert c["account_number"] == "AW00029825" and c["display_name"] == "Bike World" and c["territory_name"] == "Southeast"
    assert c["GSI2SK"] == "BIKE WORLD#029825"
    tr.apply(T.Change("Sales.SalesOrderHeader", "c", lsn(10), after=order()))
    h = sink.raw("aw-sales", "ORDER#0000043659", "ORDER")
    assert h["customer_name"] == "Bike World" and h["store_name"] == "Bike World" and h["src_lsn"] == lsn(10)


def test_out_of_order_parent_arrives_during_backoff():
    rows, sink, tr = setup(seed=False); seed_order_parents(sink, customer=False); seed_store(tr, sink)
    def sleep(secs):  # the customer lands while the order waits
        tr.sleeps.append(secs); tr.apply(T.Change("Sales.Customer", "c", lsn(9), after=customer_image()))
    rows.sleep = sleep
    tr.apply(T.Change("Sales.SalesOrderHeader", "c", lsn(10), after=order()))
    assert len(tr.sleeps) == 1 and sink.raw("aw-sales", "ORDER#0000043659", "ORDER")["customer_name"] == "Bike World"


def test_delete_with_missing_parent_does_not_wait():
    rows, sink, tr = setup(seed=False)
    rep = tr.apply(T.Change("Sales.SalesOrderHeader", "d", lsn(10), before=order()))
    assert tr.sleeps == [] and {i["PK"] for _, i in rep["tombstones"]} == {"ORDER#0000043659", "PONUMBER#PO522145787", "CCAPPROVAL#105041Vi84182"}


def test_person_rename_refreshes_customer_name_and_sort_key():
    rows, sink, tr = setup(seed=False)
    sink.put("aw-sales", {"PK": "TERRITORY#05", "SK": "TERRITORY", "name": "Southeast", "src_lsn": lsn(1)}, lsn(1))
    person = dict(BusinessEntityID=293, PersonType="IN", NameStyle=False, Title=None, FirstName="Catherine", MiddleName="R.",
                  LastName="Abel", Suffix=None, EmailPromotion=1, AdditionalContactInfo=None, Demographics=None, rowguid="g",
                  ModifiedDate=datetime.datetime(2022, 1, 1))
    tr.apply(T.Change("Person.Person", "c", lsn(1), after=person))
    tr.apply(T.Change("Sales.Customer", "c", lsn(2), after=dict(customer_image(), PersonID=293, StoreID=None)))
    assert sink.raw("aw-customer", "BE#000293", "CUSTOMER#029825")["GSI2SK"] == "ABEL, CATHERINE#029825"
    tr.apply(T.Change("Person.Person", "u", lsn(3), before=person, after=dict(person, LastName="Zed")))
    c = sink.raw("aw-customer", "BE#000293", "CUSTOMER#029825")
    assert c["display_name"] == "Catherine Zed" and c["GSI2SK"] == "ZED, CATHERINE#029825" and c["src_lsn"] == lsn(2)
    # territory rename: unindexed parent -> filtered scan
    tr.apply(T.Change("Sales.SalesTerritory", "u", lsn(4), before=None, after=dict(TerritoryID=5, Name="South East", CountryRegionCode="US",
              Group="North America", SalesYTD=decimal.Decimal("0"), SalesLastYear=decimal.Decimal("0"), CostYTD=decimal.Decimal("0"),
              CostLastYear=decimal.Decimal("0"), rowguid="g", ModifiedDate=datetime.datetime(2022, 1, 1))))
    assert sink.raw("aw-customer", "BE#000293", "CUSTOMER#029825")["territory_name"] == "South East"


def test_hierarchyid_and_geography_like_sql_server():
    for hexv, s, lvl in (("", "/", 0), ("48", "/0/", 1), ("58", "/1/", 1), ("5ade", "/1/1/3/", 3), ("62c0", "/1.1/", 1),
                         ("e02540", "/98/", 1), ("3f80", "/-1/", 1), ("17ffffb94220", "/-5000/", 1), ("80fd38", "/3.-2.7/", 1),
                         ("f800071b7220", "/123456/", 1), ("fc0111b2c9439910", "/300000000000/", 1)):
        assert T.hid_to_string(bytes.fromhex(hexv)) == s and T.hid_level(bytes.fromhex(hexv)) == lvl
    assert T.hid_to_string(None) is None
    clr = bytes.fromhex("e6100000010cae8bfc28bce4474067a89189898a5ec0")
    assert T.geo_point(clr) == (47.7869921906598, -122.164644615406)
    assert T.geo_point("POINT (-122.164644615406 47.7869921906598)") == (47.7869921906598, -122.164644615406)
    assert T.geo_point(None) == (None, None)


def test_no_table_needs_sql():
    cfg = T.load_enrichment()
    assert "sql" not in cfg and not hasattr(T, "SqlRows")
    for t, spec in cfg["lookup"].items():
        assert set((spec.get("computed") or {}).values()) <= set(T.COMPUTED), t


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


def test_debezium_and_dms_images_normalise_guid_and_time_like_pymssql():
    types = lambda t: [{"name": "rowguid", "st": "uniqueidentifier"}, {"name": "StartTime", "st": "time"}, {"name": "Flag", "st": "bit"}]
    ev = {"payload": {"op": "u", "source": {"schema": "HumanResources", "table": "Shift", "change_lsn": "0000002e:00000a10:0003", "ts_ms": 1},
                      "before": None, "after": {"rowguid": "D54E0552-C226-4C22-AF3B-762CA854CDD3", "StartTime": 25200000, "Flag": True}}}
    a = T.from_debezium(ev, types).after
    assert a["rowguid"] == "d54e0552-c226-4c22-af3b-762ca854cdd3" and a["StartTime"] == datetime.time(7, 0)
    rec = {"metadata": {"schema-name": "HumanResources", "table-name": "Shift", "operation": "update", "timestamp": "2026-10-11T00:00:00Z"},
           "data": {"rowguid": "D54E0552-C226-4C22-AF3B-762CA854CDD3", "StartTime": "07:00:00.0000000", "Flag": "1", "AR_H_CHANGE_SEQ": "1"}}
    d = T.from_dms(rec, types).after
    assert d["rowguid"] == a["rowguid"] and d["StartTime"] == datetime.time(7, 0) and d["Flag"] is True
