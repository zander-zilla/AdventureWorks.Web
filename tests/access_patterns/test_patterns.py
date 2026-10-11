"""Executes every DynamoDB-served access pattern (design/mapping/access-pattern-keys.yaml) against DynamoDB Local
loaded by scripts/loader/load.py, and checks results against the equivalent SQL on AdventureWorks2022."""
import datetime, decimal, json, os, uuid
import pytest, yaml
from boto3.dynamodb.conditions import Key, Attr
from conftest import pattern, q, query_all, awmap

ROOT = awmap.ROOT
def T(db, name): return db.Table(name)
def iso(d): return d.replace(microsecond=0).isoformat()

# ---------------- Catalog ----------------
@pattern("CAT-01")
def test_cat01_categories_with_subcategories(db, sql):
    items = query_all(T(db, "aw-catalog"), KeyConditionExpression=Key("PK").eq("CATALOG"))
    cats = [i for i in items if i["type"] == "Category"]; subs = [i for i in items if i["type"] == "Subcategory"]
    assert len(cats) == q(sql, "SELECT COUNT(*) n FROM Production.ProductCategory")[0]["n"]
    assert len(subs) == q(sql, "SELECT COUNT(*) n FROM Production.ProductSubcategory")[0]["n"]
    assert {(s["product_category_id"], s["name"]) for s in subs} == {(r["ProductCategoryID"], r["Name"]) for r in q(sql, "SELECT ProductCategoryID, Name FROM Production.ProductSubcategory")}

@pattern("CAT-02")
def test_cat02_category_and_subcategory_by_id(db, sql):
    t = T(db, "aw-catalog")
    items = query_all(t, KeyConditionExpression=Key("PK").eq("CATALOG") & Key("SK").begins_with("CAT#0001"))
    assert items[0]["type"] == "Category" and items[0]["name"] == "Bikes"
    assert len(items) - 1 == q(sql, "SELECT COUNT(*) n FROM Production.ProductSubcategory WHERE ProductCategoryID = 1")[0]["n"]
    sub = query_all(t, IndexName="GSI1", KeyConditionExpression=Key("GSI1PK").eq("SUBCAT#0014") & Key("GSI1SK").eq("#META"))
    assert sub[0]["name"] == q(sql, "SELECT Name FROM Production.ProductSubcategory WHERE ProductSubcategoryID = 14")[0]["Name"]
    t.update_item(Key={"PK": "CATALOG", "SK": "CAT#0001"}, UpdateExpression="SET ver = ver + :one", ExpressionAttributeValues={":one": 1},
                  ConditionExpression="attribute_exists(PK)")

@pattern("CAT-03")
def test_cat03_sellable_products_in_subcategory(db, sql):
    for sub in (1, 2, 14, 31):
        items = query_all(T(db, "aw-catalog"), IndexName="GSI1", KeyConditionExpression=Key("GSI1PK").eq("SUBCAT#%04d" % sub) & Key("GSI1SK").begins_with("PRODUCT#A#"))
        exp = [r["Name"] for r in q(sql, "SELECT Name FROM Production.Product WHERE ProductSubcategoryID = %s AND SellEndDate IS NULL AND DiscontinuedDate IS NULL ORDER BY LOWER(Name), ProductID", sub)]
        assert [i["name"] for i in items] == exp

@pattern("CAT-04")
def test_cat04_product_detail(db, sql):
    t = T(db, "aw-catalog")
    items = query_all(t, KeyConditionExpression=Key("PK").eq("PRODUCT#000771"))
    types = {i["type"] for i in items}
    assert {"Product", "ProductPhotoLink", "ListPriceHistory", "CostHistory", "ProductOffer"} <= types
    p = next(i for i in items if i["type"] == "Product")
    r = q(sql, "SELECT p.ListPrice, p.ProductModelID, (SELECT SUM(Quantity) FROM Production.ProductInventory WHERE ProductID = 771) qty FROM Production.Product p WHERE ProductID = 771")[0]
    assert p["list_price"] == r["ListPrice"] and p["stock_qty"] == r["qty"]
    assert len([i for i in items if i["type"] == "ProductOffer"]) == q(sql, "SELECT COUNT(*) n FROM Sales.SpecialOfferProduct WHERE ProductID = 771")[0]["n"]
    d = t.get_item(Key={"PK": "MODEL#%04d" % r["ProductModelID"], "SK": "DESC#en"})["Item"]
    exp = q(sql, "SELECT pd.Description FROM Production.ProductModelProductDescriptionCulture x JOIN Production.ProductDescription pd ON pd.ProductDescriptionID = x.ProductDescriptionID WHERE x.ProductModelID = %s AND x.CultureID = 'en'", r["ProductModelID"])[0]["Description"]
    assert d["description"] == exp
    reviewed = query_all(t, KeyConditionExpression=Key("PK").eq("PRODUCT#000937") & Key("SK").begins_with("REVIEW#"))
    assert len(reviewed) == q(sql, "SELECT COUNT(*) n FROM Production.ProductReview WHERE ProductID = 937")[0]["n"]

@pattern("CAT-05")
def test_cat05_product_by_number(db, sql):
    t = T(db, "aw-catalog")
    m = t.get_item(Key={"PK": "PRODUCTNUMBER#BK-M68B-42", "SK": "PRODUCTNUMBER"})["Item"]
    p = t.get_item(Key={"PK": "PRODUCT#%06d" % m["product_id"], "SK": "PRODUCT"})["Item"]
    assert p["name"] == q(sql, "SELECT Name FROM Production.Product WHERE ProductNumber = 'BK-M68B-42'")[0]["Name"]

@pattern("CAT-06")
def test_cat06_admin_product_list(db, sql):
    items = query_all(T(db, "aw-catalog"), KeyConditionExpression=Key("PK").eq("PRODUCTNAMES"))
    assert [i["name"] for i in items] == [r["Name"] for r in q(sql, "SELECT Name FROM Production.Product ORDER BY LOWER(Name)")]
    page = T(db, "aw-catalog").query(KeyConditionExpression=Key("PK").eq("PRODUCTNAMES"), Limit=25)
    assert len(page["Items"]) == 25 and "LastEvaluatedKey" in page

@pattern("CAT-07")
def test_cat07_create_product_enforces_unique_name_and_number(db):
    t = T(db, "aw-catalog"); c = t.meta.client
    pid = 990000 + int(uuid.uuid4().int % 9999); name = "Test Bike %d" % pid; num = "TB-%d" % pid
    def tx(n, nm):
        c.transact_write_items(TransactItems=[
            {"Put": {"TableName": "aw-catalog", "Item": {"PK": "PRODUCT#%06d" % pid, "SK": "PRODUCT", "type": "Product", "name": nm, "src": "ddb", "ver": int("1")}, "ConditionExpression": "attribute_not_exists(PK)"}},
            {"Put": {"TableName": "aw-catalog", "Item": {"PK": "PRODUCTNAMES", "SK": nm.lower(), "type": "ProductNameIndex", "product_id": int(str(pid))}, "ConditionExpression": "attribute_not_exists(PK)"}},
            {"Put": {"TableName": "aw-catalog", "Item": {"PK": "PRODUCTNUMBER#" + n, "SK": "PRODUCTNUMBER", "type": "ProductNumberIndex", "product_id": int(str(pid))}, "ConditionExpression": "attribute_not_exists(PK)"}}])
    tx(num, name)
    assert t.get_item(Key={"PK": "PRODUCTNUMBER#" + num, "SK": "PRODUCTNUMBER"})["Item"]["product_id"] == pid
    with pytest.raises(c.exceptions.TransactionCanceledException):
        pid2 = pid  # same name must be rejected
        tx("OTHER-" + num, "Mountain-100 Black, 42")
    for k in ({"PK": "PRODUCT#%06d" % pid, "SK": "PRODUCT"}, {"PK": "PRODUCTNAMES", "SK": name.lower()}, {"PK": "PRODUCTNUMBER#" + num, "SK": "PRODUCTNUMBER"}):
        t.delete_item(Key=k)

@pattern("CAT-08")
def test_cat08_model_and_variants(db, sql):
    t = T(db, "aw-catalog")
    m = query_all(t, KeyConditionExpression=Key("PK").eq("MODEL#0019"))
    assert len([i for i in m if i["type"] == "ModelDescription"]) == q(sql, "SELECT COUNT(*) n FROM Production.ProductModelProductDescriptionCulture WHERE ProductModelID = 19")[0]["n"]
    v = query_all(t, IndexName="GSI2", KeyConditionExpression=Key("GSI2PK").eq("MODEL#0019") & Key("GSI2SK").begins_with("PRODUCT#"))
    assert sorted(i["product_id"] for i in v) == [r["ProductID"] for r in q(sql, "SELECT ProductID FROM Production.Product WHERE ProductModelID = 19 ORDER BY ProductID")]

@pattern("CAT-09")
def test_cat09_price_as_of_date(db, sql):
    t = T(db, "aw-catalog")
    for pid, d in ((707, datetime.datetime(2012, 6, 1)), (707, datetime.datetime(2013, 6, 1)), (771, datetime.datetime(2012, 1, 1))):
        r = t.query(KeyConditionExpression=Key("PK").eq("PRODUCT#%06d" % pid) & Key("SK").between("PRICE#", "PRICE#" + iso(d)), ScanIndexForward=False, Limit=1)["Items"]
        exp = q(sql, "SELECT TOP 1 ListPrice FROM Production.ProductListPriceHistory WHERE ProductID = %s AND StartDate <= %s ORDER BY StartDate DESC", pid, d)
        assert (r[0]["list_price"] if r else None) == (exp[0]["ListPrice"] if exp else None)

@pattern("CAT-10")
def test_cat10_active_offers(db, sql):
    d = datetime.datetime(2013, 7, 15)
    items = query_all(T(db, "aw-catalog"), KeyConditionExpression=Key("PK").eq("PRODUCT#000870") & Key("SK").begins_with("OFFER#"))
    active = sorted(i["special_offer_id"] for i in items if i["offer_start"] <= iso(d) <= i["offer_end"])
    exp = [r["SpecialOfferID"] for r in q(sql, "SELECT o.SpecialOfferID FROM Sales.SpecialOfferProduct x JOIN Sales.SpecialOffer o ON o.SpecialOfferID = x.SpecialOfferID WHERE x.ProductID = 870 AND %s BETWEEN o.StartDate AND o.EndDate ORDER BY 1", d)]
    assert active == exp

@pattern("CAT-11")
def test_cat11_reviews_newest_first(db, sql):
    items = query_all(T(db, "aw-catalog"), KeyConditionExpression=Key("PK").eq("PRODUCT#000937") & Key("SK").begins_with("REVIEW#"), ScanIndexForward=False)
    assert [i["product_review_id"] for i in items] == [r["ProductReviewID"] for r in q(sql, "SELECT ProductReviewID FROM Production.ProductReview WHERE ProductID = 937 ORDER BY ReviewDate DESC, ProductReviewID DESC")]

@pattern("CAT-12")
def test_cat12_name_prefix_search(db, sql):
    for prefix in ("mountain-1", "road", "hl "):
        items = query_all(T(db, "aw-catalog"), KeyConditionExpression=Key("PK").eq("PRODUCTNAMES") & Key("SK").begins_with(prefix))
        assert sorted(i["product_id"] for i in items) == [r["ProductID"] for r in q(sql, "SELECT ProductID FROM Production.Product WHERE LOWER(Name) LIKE %s ORDER BY ProductID", prefix + "%")]

@pattern("CAT-13")
def test_cat13_all_cultures(db, sql):
    for r in q(sql, "SELECT x.ProductModelID, RTRIM(x.CultureID) c, d.Description FROM Production.ProductModelProductDescriptionCulture x JOIN Production.ProductDescription d ON d.ProductDescriptionID = x.ProductDescriptionID WHERE x.ProductModelID = 19"):
        assert T(db, "aw-catalog").get_item(Key={"PK": "MODEL#0019", "SK": "DESC#" + r["c"]})["Item"]["description"] == r["Description"]

# ---------------- Inventory ----------------
@pattern("INV-01")
def test_inv01_stock_by_location(db, sql):
    items = query_all(T(db, "aw-inventory"), KeyConditionExpression=Key("PK").eq("PRODUCT#000001") & Key("SK").lte("PRODUCT"))
    inv = {i["location_id"]: i["quantity"] for i in items if i["type"] == "ProductInventory"}
    assert inv == {r["LocationID"]: r["Quantity"] for r in q(sql, "SELECT LocationID, Quantity FROM Production.ProductInventory WHERE ProductID = 1")}
    assert next(i for i in items if i["type"] == "InventoryProduct")["stock_qty"] == sum(inv.values())

@pattern("INV-02")
def test_inv02_below_reorder_point(db, sql):
    items = query_all(T(db, "aw-inventory"), IndexName="GSI1", KeyConditionExpression=Key("GSI1PK").eq("REORDER"))
    exp = [r["ProductID"] for r in q(sql, "SELECT p.ProductID FROM Production.Product p WHERE (SELECT ISNULL(SUM(Quantity),0) FROM Production.ProductInventory i WHERE i.ProductID = p.ProductID) < p.ReorderPoint ORDER BY 1")]
    assert sorted(i["product_id"] for i in items) == exp

@pattern("INV-03")
def test_inv03_transactions_by_date(db, sql):
    a, b = datetime.datetime(2013, 9, 1), datetime.datetime(2013, 9, 30, 23, 59, 59)
    items = query_all(T(db, "aw-inventory"), KeyConditionExpression=Key("PK").eq("PRODUCT#000712") & Key("SK").between("TXN#" + iso(a), "TXN#" + iso(b) + "~"))
    exp = q(sql, "SELECT COUNT(*) n FROM (SELECT TransactionID FROM Production.TransactionHistory WHERE ProductID = 712 AND TransactionDate BETWEEN %s AND %s UNION ALL SELECT TransactionID FROM Production.TransactionHistoryArchive WHERE ProductID = 712 AND TransactionDate BETWEEN %s AND %s) x", a, b, a, b)[0]["n"]
    assert len(items) == exp and exp > 0

@pattern("INV-04")
def test_inv04_bom_explosion(db, sql):
    t = T(db, "aw-inventory"); d = iso(datetime.datetime(2010, 12, 23)); seen = []
    def explode(asm, lvl):
        for e in query_all(t, KeyConditionExpression=Key("PK").eq("ASSEMBLY#%06d" % asm)):
            if e["start_date"] <= d and ("end_date" not in e or e["end_date"] >= d):
                seen.append((asm, e["component_id"], lvl)); explode(e["component_id"], lvl + 1)
    explode(800, 0)
    exp = {(r["ProductAssemblyID"], r["ComponentID"], r["RecursionLevel"]) for r in q(sql, "EXEC dbo.uspGetBillOfMaterials @StartProductID = 800, @CheckDate = %s", datetime.datetime(2010, 12, 23))}
    assert set(seen) == exp

@pattern("INV-05")
def test_inv05_where_used(db, sql):
    t = T(db, "aw-inventory"); d = iso(datetime.datetime(2010, 12, 23)); seen = set()
    def up(comp):
        for e in query_all(t, IndexName="GSI1", KeyConditionExpression=Key("GSI1PK").eq("COMPONENT#%06d" % comp)):
            if "product_assembly_id" in e and e["start_date"] <= d and ("end_date" not in e or e["end_date"] >= d):
                seen.add(e["product_assembly_id"]); up(e["product_assembly_id"])
    up(316)
    exp = {r["ProductAssemblyID"] for r in q(sql, "EXEC dbo.uspGetWhereUsedProductID @StartProductID = 316, @CheckDate = %s", datetime.datetime(2010, 12, 23))}
    assert seen == exp

@pattern("INV-06")
def test_inv06_work_orders_due(db, sql):
    t = T(db, "aw-inventory")
    items = query_all(t, IndexName="GSI2", KeyConditionExpression=Key("GSI2PK").eq("WODUE#2013-07") & Key("GSI2SK").between("2013-07-01", "2013-07-10~"))
    assert len(items) == q(sql, "SELECT COUNT(*) n FROM Production.WorkOrder WHERE DueDate >= '2013-07-01' AND DueDate < '2013-07-11'")[0]["n"]
    open_ = query_all(t, IndexName="GSI2", KeyConditionExpression=Key("GSI2PK").eq("WODUE#2013-07"), FilterExpression=Attr("end_date").not_exists())
    assert len(open_) == q(sql, "SELECT COUNT(*) n FROM Production.WorkOrder WHERE EndDate IS NULL AND DueDate >= '2013-07-01' AND DueDate < '2013-08-01'")[0]["n"]
    wo = query_all(t, KeyConditionExpression=Key("PK").eq("WO#000013"))
    assert len(wo) - 1 == q(sql, "SELECT COUNT(*) n FROM Production.WorkOrderRouting WHERE WorkOrderID = 13")[0]["n"]

# ---------------- Sales ----------------
@pattern("SAL-01")
def test_sal01_cart(db, sql):
    t = T(db, "aw-sales"); ttl = int(datetime.datetime.utcnow().timestamp()) + 7 * 86400
    t.put_item(Item={"PK": "CART#29485", "SK": "ITEM#000707", "type": "CartItem", "product_id": 707, "quantity": 2, "ttl": ttl, "src": "ddb", "ver": 1})
    t.update_item(Key={"PK": "CART#29485", "SK": "ITEM#000707"}, UpdateExpression="SET quantity = quantity + :one", ExpressionAttributeValues={":one": 1})
    items = query_all(t, KeyConditionExpression=Key("PK").eq("CART#29485"), ConsistentRead=True)
    assert [(i["product_id"], i["quantity"]) for i in items] == [(707, 3)]
    t.delete_item(Key={"PK": "CART#29485", "SK": "ITEM#000707"})
    src = query_all(t, KeyConditionExpression=Key("PK").eq("CART#14951"), ConsistentRead=True)
    assert len(src) == q(sql, "SELECT COUNT(*) n FROM Sales.ShoppingCartItem WHERE ShoppingCartID = '14951'")[0]["n"]
    assert all("ttl" in i for i in src)

@pattern("SAL-02")
def test_sal02_checkout_native_order(db):
    t = T(db, "aw-sales"); c = t.meta.client
    oid = int(t.update_item(Key={"PK": "COUNTER", "SK": "ORDER"}, UpdateExpression="ADD next_id :one", ExpressionAttributeValues={":one": 1}, ReturnValues="UPDATED_NEW")["Attributes"]["next_id"])
    assert oid > 1000000000 > q_max_sql_order()
    now = iso(datetime.datetime.utcnow())
    c.transact_write_items(TransactItems=[
        {"Put": {"TableName": "aw-sales", "ConditionExpression": "attribute_not_exists(PK)", "Item": {"PK": "ORDER#%010d" % oid, "SK": "ORDER", "type": "Order", "src": "ddb", "sales_order_id": int(str(oid)), "sales_order_number": "SO-DDB-%d" % oid, "customer_id": int("29485"), "status": int("1"), "order_date": now, "sub_total": int("318"), "GSI1PK": "CUSTOMER#029485", "GSI1SK": "ORDER#%s#%010d" % (now, oid), "GSI2PK": "ORDERSTATUS#1", "GSI2SK": "%s#%010d" % (now, oid), "ver": int("1")}}},
        {"Put": {"TableName": "aw-sales", "Item": {"PK": "ORDER#%010d" % oid, "SK": "LINE#0000001", "type": "OrderLine", "src": "ddb", "product_id": int("879"), "order_qty": int("2"), "unit_price": int("159"), "ver": int("1")}}}])
    got = query_all(t, KeyConditionExpression=Key("PK").eq("ORDER#%010d" % oid), ConsistentRead=True)  # read-after-checkout (D8)
    assert [i["type"] for i in got] == ["OrderLine", "Order"]
    for i in got: t.delete_item(Key={"PK": i["PK"], "SK": i["SK"]})

def q_max_sql_order():
    import sqlsrc
    c = sqlsrc.connect(); r = q(c, "SELECT MAX(SalesOrderID) m FROM Sales.SalesOrderHeader")[0]["m"]; c.close(); return r

@pattern("SAL-03")
def test_sal03_order_history(db, sql):
    for cid in (29485, 11000, 11091):
        items = query_all(T(db, "aw-sales"), IndexName="GSI1", KeyConditionExpression=Key("GSI1PK").eq("CUSTOMER#%06d" % cid) & Key("GSI1SK").begins_with("ORDER#"), ScanIndexForward=False)
        exp = [r["SalesOrderID"] for r in q(sql, "SELECT SalesOrderID FROM Sales.SalesOrderHeader WHERE CustomerID = %s ORDER BY OrderDate DESC, SalesOrderID DESC", cid)]
        assert [i["sales_order_id"] for i in items] == exp

@pattern("SAL-04")
def test_sal04_order_with_lines(db, sql):
    for oid in (43659, 51131, 75123):
        items = query_all(T(db, "aw-sales"), KeyConditionExpression=Key("PK").eq("ORDER#%010d" % oid), ConsistentRead=True)
        h = next(i for i in items if i["type"] == "Order"); lines = [i for i in items if i["type"] == "OrderLine"]
        r = q(sql, "SELECT TotalDue, SalesOrderNumber, (SELECT COUNT(*) FROM Sales.SalesOrderDetail d WHERE d.SalesOrderID = h.SalesOrderID) n, (SELECT COUNT(*) FROM Sales.SalesOrderHeaderSalesReason r WHERE r.SalesOrderID = h.SalesOrderID) nr FROM Sales.SalesOrderHeader h WHERE SalesOrderID = %s", oid)[0]
        assert h["total_due"] == r["TotalDue"] and h["sales_order_number"] == r["SalesOrderNumber"] and len(lines) == r["n"]
        assert len([i for i in items if i["type"] == "OrderSalesReason"]) == r["nr"]
        assert sum(l["line_total"] for l in lines) == q(sql, "SELECT SUM(LineTotal) s FROM Sales.SalesOrderDetail WHERE SalesOrderID = %s", oid)[0]["s"]

@pattern("SAL-05")
def test_sal05_orders_by_status(db, sql):
    for s in (1, 2, 3):
        items = query_all(T(db, "aw-sales"), IndexName="GSI2", KeyConditionExpression=Key("GSI2PK").eq("ORDERSTATUS#%d" % s))
        assert len([i for i in items if i.get("src") == "sql"]) == q(sql, "SELECT COUNT(*) n FROM Sales.SalesOrderHeader WHERE Status = %s", s)[0]["n"]

@pattern("SAL-06")
def test_sal06_ship_order_conditional(db):
    t = T(db, "aw-sales"); c = t.meta.client; k = {"PK": "ORDER#9999999999", "SK": "ORDER"}
    t.put_item(Item={**k, "type": "Order", "status": 1, "ver": 1, "revision_number": 1, "GSI2PK": "ORDERSTATUS#1", "GSI2SK": "x"})
    t.update_item(Key=k, UpdateExpression="SET #s = :shipped, revision_number = revision_number + :one, ver = ver + :one REMOVE GSI2PK, GSI2SK",
                  ConditionExpression="ver = :v AND #s = :exp", ExpressionAttributeNames={"#s": "status"},
                  ExpressionAttributeValues={":shipped": 5, ":one": 1, ":v": 1, ":exp": 1})
    with pytest.raises(c.exceptions.ConditionalCheckFailedException):
        t.update_item(Key=k, UpdateExpression="SET #s = :c", ConditionExpression="ver = :v", ExpressionAttributeNames={"#s": "status"}, ExpressionAttributeValues={":c": 6, ":v": 1})
    assert "GSI2PK" not in t.get_item(Key=k)["Item"]; t.delete_item(Key=k)

@pattern("SAL-07")
def test_sal07_store_orders_by_date(db, sql):
    cid = q(sql, "SELECT TOP 1 CustomerID FROM Sales.Customer WHERE StoreID IS NOT NULL AND CustomerID IN (SELECT CustomerID FROM Sales.SalesOrderHeader) ORDER BY CustomerID")[0]["CustomerID"]
    items = query_all(T(db, "aw-sales"), IndexName="GSI1", KeyConditionExpression=Key("GSI1PK").eq("CUSTOMER#%06d" % cid) & Key("GSI1SK").between("ORDER#2012-01-01", "ORDER#2013-12-31~"))
    assert len(items) == q(sql, "SELECT COUNT(*) n FROM Sales.SalesOrderHeader WHERE CustomerID = %s AND OrderDate BETWEEN '2012-01-01' AND '2013-12-31'", cid)[0]["n"]

@pattern("SAL-10")
def test_sal10_sales_person_quotas(db, sql):
    items = query_all(T(db, "aw-sales"), KeyConditionExpression=Key("PK").eq("SALESPERSON#000275"))
    sp = next(i for i in items if i["type"] == "SalesPerson")
    r = q(sql, "SELECT SalesYTD FROM Sales.SalesPerson WHERE BusinessEntityID = 275")[0]
    assert sp["sales_ytd"] == r["SalesYTD"]
    assert len([i for i in items if i["type"] == "SalesQuota"]) == q(sql, "SELECT COUNT(*) n FROM Sales.SalesPersonQuotaHistory WHERE BusinessEntityID = 275")[0]["n"]

@pattern("SAL-12")
def test_sal12_territory_sales_people(db, sql):
    for tid in range(1, 11):
        items = query_all(T(db, "aw-sales"), KeyConditionExpression=Key("PK").eq("TERRITORY#%02d" % tid) & Key("SK").begins_with("SALESPERSON#"))
        assert sorted(i["business_entity_id"] for i in items) == [r["BusinessEntityID"] for r in q(sql, "SELECT BusinessEntityID FROM Sales.SalesTerritoryHistory WHERE TerritoryID = %s ORDER BY 1", tid)]

@pattern("SAL-13")
def test_sal13_lookup_by_po_and_approval(db, sql):
    r = q(sql, "SELECT TOP 1 SalesOrderID, PurchaseOrderNumber, CreditCardApprovalCode FROM Sales.SalesOrderHeader WHERE PurchaseOrderNumber IS NOT NULL AND CreditCardApprovalCode IS NOT NULL ORDER BY SalesOrderID DESC")[0]
    a = query_all(T(db, "aw-sales"), KeyConditionExpression=Key("PK").eq("PONUMBER#" + r["PurchaseOrderNumber"]))
    b = query_all(T(db, "aw-sales"), KeyConditionExpression=Key("PK").eq("CCAPPROVAL#" + r["CreditCardApprovalCode"]))
    assert a[0]["sales_order_id"] == r["SalesOrderID"] and b[0]["sales_order_id"] == r["SalesOrderID"]

# ---------------- Customer & Party ----------------
@pattern("CUS-01")
def test_cus01_login_by_email(db, sql):
    t = T(db, "aw-customer")
    m = t.get_item(Key={"PK": "EMAIL#catherine0@adventure-works.com", "SK": "EMAIL"}, ConsistentRead=True)["Item"]
    items = query_all(t, KeyConditionExpression=Key("PK").eq("BE#%06d" % m["business_entity_id"]), ConsistentRead=True)
    types = {i["type"] for i in items}
    assert {"Person", "Password", "Customer"} <= types
    pw = next(i for i in items if i["type"] == "Password")
    assert pw["password_hash"] == q(sql, "SELECT PasswordHash FROM Person.Password WHERE BusinessEntityID = %s", m["business_entity_id"])[0]["PasswordHash"]
    assert next(i for i in items if i["type"] == "Customer")["customer_id"] == 29485

@pattern("CUS-02")
def test_cus02_profile(db, sql):
    t = T(db, "aw-customer")
    for cid in (11000, 29485):
        c = query_all(t, IndexName="GSI1", KeyConditionExpression=Key("GSI1PK").eq("CUSTOMER#%06d" % cid))[0]
        items = query_all(t, KeyConditionExpression=Key("PK").eq(c["PK"]))
        pid = q(sql, "SELECT PersonID FROM Sales.Customer WHERE CustomerID = %s", cid)[0]["PersonID"]
        assert len([i for i in items if i["type"] == "EmailAddress"]) == q(sql, "SELECT COUNT(*) n FROM Person.EmailAddress WHERE BusinessEntityID = %s", pid)[0]["n"]
        assert len([i for i in items if i["type"] == "Phone"]) == q(sql, "SELECT COUNT(*) n FROM Person.PersonPhone WHERE BusinessEntityID = %s", pid)[0]["n"]

@pattern("CUS-03")
def test_cus03_checkout_addresses_and_cards(db, sql):
    t = T(db, "aw-customer")
    adr = query_all(t, KeyConditionExpression=Key("PK").eq("BE#020777") & Key("SK").begins_with("ADDRESS#"))
    assert len(adr) == q(sql, "SELECT COUNT(*) n FROM Person.BusinessEntityAddress WHERE BusinessEntityID = 20777")[0]["n"]
    pid = q(sql, "SELECT TOP 1 BusinessEntityID FROM Sales.PersonCreditCard ORDER BY BusinessEntityID")[0]["BusinessEntityID"]
    cards = query_all(t, KeyConditionExpression=Key("PK").eq("BE#%06d" % pid) & Key("SK").begins_with("CARD#"))
    exp = q(sql, "SELECT RIGHT(c.CardNumber, 4) l4 FROM Sales.PersonCreditCard x JOIN Sales.CreditCard c ON c.CreditCardID = x.CreditCardID WHERE x.BusinessEntityID = %s", pid)
    assert [c["card_last4"] for c in cards] == [r["l4"] for r in exp] and all("card_number" not in c for c in cards)
    store_adr = query_all(t, KeyConditionExpression=Key("PK").eq("BE#000294") & Key("SK").begins_with("ADDRESS#"))
    assert any(a["address_id"] == 1086 for a in store_adr)  # demo store contact checks out with the store's address

@pattern("CUS-04")
def test_cus04_register_unique_email(db):
    c = T(db, "aw-customer").meta.client
    def reg(email, be):
        c.transact_write_items(TransactItems=[
            {"Put": {"TableName": "aw-customer", "Item": {"PK": "BE#%06d" % be, "SK": "PERSON", "type": "Person", "src": "ddb"}, "ConditionExpression": "attribute_not_exists(PK)"}},
            {"Put": {"TableName": "aw-customer", "Item": {"PK": "EMAIL#" + email, "SK": "EMAIL", "type": "EmailLogin", "business_entity_id": int(str(be))}, "ConditionExpression": "attribute_not_exists(PK)"}}])
    with pytest.raises(c.exceptions.TransactionCanceledException):
        reg("catherine0@adventure-works.com", 999990)
    reg("new.user@example.com", 999991)
    t = T(db, "aw-customer"); t.delete_item(Key={"PK": "BE#999991", "SK": "PERSON"}); t.delete_item(Key={"PK": "EMAIL#new.user@example.com", "SK": "EMAIL"})

@pattern("CUS-05")
def test_cus05_customer_admin_list(db, sql):
    page = T(db, "aw-customer").query(IndexName="GSI2", KeyConditionExpression=Key("GSI2PK").eq("CUSTOMERS"), Limit=50)
    exp = [r["CustomerID"] for r in q(sql, """SELECT TOP 50 c.CustomerID FROM Sales.Customer c LEFT JOIN Person.Person p ON p.BusinessEntityID = c.PersonID LEFT JOIN Sales.Store s ON s.BusinessEntityID = c.StoreID
        ORDER BY UPPER(COALESCE(p.LastName + ', ' + p.FirstName, s.Name)) COLLATE Latin1_General_BIN, RIGHT('000000' + CAST(c.CustomerID AS varchar(10)), 6)""")]
    assert [i["customer_id"] for i in page["Items"]] == exp
    total = len(query_all(T(db, "aw-customer"), IndexName="GSI2", KeyConditionExpression=Key("GSI2PK").eq("CUSTOMERS")))
    assert total == q(sql, "SELECT COUNT(*) n FROM Sales.Customer")[0]["n"]

@pattern("CUS-06")
def test_cus06_by_account_number(db, sql):
    acct = "AW00011000"; cid = int(acct[2:])
    c = query_all(T(db, "aw-customer"), IndexName="GSI1", KeyConditionExpression=Key("GSI1PK").eq("CUSTOMER#%06d" % cid))[0]
    assert c["account_number"] == acct == q(sql, "SELECT AccountNumber FROM Sales.Customer WHERE CustomerID = %s", cid)[0]["AccountNumber"]

@pattern("CUS-07")
def test_cus07_store_contacts_addresses(db, sql):
    items = query_all(T(db, "aw-customer"), KeyConditionExpression=Key("PK").eq("BE#000294"))
    assert any(i["type"] == "Store" and "demographics" in i for i in items)
    assert len([i for i in items if i["type"] == "PartyContact"]) == q(sql, "SELECT COUNT(*) n FROM Person.BusinessEntityContact WHERE BusinessEntityID = 294")[0]["n"]

@pattern("CUS-08")
def test_cus08_demographics(db, sql):
    p = T(db, "aw-customer").get_item(Key={"PK": "BE#%06d" % 20777, "SK": "PERSON"}, ProjectionExpression="demographics")["Item"]
    r = q(sql, "SELECT Demographics.value('declare default element namespace \"http://schemas.microsoft.com/sqlserver/2004/07/adventure-works/IndividualSurvey\"; (/IndividualSurvey/YearlyIncome)[1]', 'nvarchar(50)') y FROM Person.Person WHERE BusinessEntityID = 20777")[0]
    assert p["demographics"]["yearly_income"] == r["y"]

@pattern("CUS-09")
def test_cus09_add_phone(db):
    t = T(db, "aw-customer"); k = {"PK": "BE#020777", "SK": "PHONE#03#555-0100"}
    t.put_item(Item={**k, "type": "Phone", "phone_number": "555-0100", "src": "ddb", "ver": 1})
    assert any(i["SK"] == k["SK"] for i in query_all(t, KeyConditionExpression=Key("PK").eq("BE#020777") & Key("SK").begins_with("PHONE#")))
    t.delete_item(Key=k)

@pattern("CUS-11")
def test_cus11_contact_info_any_entity(db, sql):
    vendor_contact = q(sql, "SELECT TOP 1 PersonID FROM Person.BusinessEntityContact x JOIN Purchasing.Vendor v ON v.BusinessEntityID = x.BusinessEntityID")[0]["PersonID"]
    for be in (vendor_contact, 1, 20777):
        items = query_all(T(db, "aw-customer"), KeyConditionExpression=Key("PK").eq("BE#%06d" % be))
        assert next(i for i in items if i["type"] == "Person")["last_name"] == q(sql, "SELECT LastName FROM Person.Person WHERE BusinessEntityID = %s", be)[0]["LastName"]

# ---------------- Purchasing ----------------
@pattern("PUR-01")
def test_pur01_vendor_addresses_contacts(db, sql):
    v = 1492
    items = query_all(T(db, "aw-purchasing"), KeyConditionExpression=Key("PK").eq("VENDOR#%06d" % v) & Key("SK").lt("PRODUCT#"))
    assert len([i for i in items if i["type"] == "VendorAddress"]) == q(sql, "SELECT COUNT(*) n FROM Person.BusinessEntityAddress WHERE BusinessEntityID = %s", v)[0]["n"]
    assert len([i for i in items if i["type"] == "VendorContact"]) == q(sql, "SELECT COUNT(*) n FROM Person.BusinessEntityContact WHERE BusinessEntityID = %s", v)[0]["n"]

@pattern("PUR-02")
def test_pur02_vendors_for_product(db, sql):
    items = query_all(T(db, "aw-purchasing"), IndexName="GSI1", KeyConditionExpression=Key("GSI1PK").eq("PRODUCT#000001") & Key("GSI1SK").begins_with("VENDOR#"))
    assert sorted(i["business_entity_id"] for i in items) == [r["BusinessEntityID"] for r in q(sql, "SELECT BusinessEntityID FROM Purchasing.ProductVendor WHERE ProductID = 1 ORDER BY 1")]

@pattern("PUR-03")
def test_pur03_products_of_vendor(db, sql):
    items = query_all(T(db, "aw-purchasing"), KeyConditionExpression=Key("PK").eq("VENDOR#001492") & Key("SK").begins_with("PRODUCT#"))
    assert [i["product_id"] for i in items] == [r["ProductID"] for r in q(sql, "SELECT ProductID FROM Purchasing.ProductVendor WHERE BusinessEntityID = 1492 ORDER BY 1")]

@pattern("PUR-04")
def test_pur04_po_with_lines(db, sql):
    items = query_all(T(db, "aw-purchasing"), KeyConditionExpression=Key("PK").eq("PO#000004"))
    po = next(i for i in items if i["type"] == "PurchaseOrder")
    assert po["total_due"] == q(sql, "SELECT TotalDue FROM Purchasing.PurchaseOrderHeader WHERE PurchaseOrderID = 4")[0]["TotalDue"]
    assert len(items) - 1 == q(sql, "SELECT COUNT(*) n FROM Purchasing.PurchaseOrderDetail WHERE PurchaseOrderID = 4")[0]["n"]

@pattern("PUR-05")
def test_pur05_vendor_pos(db, sql):
    items = query_all(T(db, "aw-purchasing"), IndexName="GSI1", KeyConditionExpression=Key("GSI1PK").eq("VENDOR#001492") & Key("GSI1SK").begins_with("PO#"), ScanIndexForward=False, FilterExpression=Attr("status").eq(4))
    assert [i["purchase_order_id"] for i in items] == [r["PurchaseOrderID"] for r in q(sql, "SELECT PurchaseOrderID FROM Purchasing.PurchaseOrderHeader WHERE VendorID = 1492 AND Status = 4 ORDER BY OrderDate DESC, PurchaseOrderID DESC")]

@pattern("PUR-06")
def test_pur06_employee_pos(db, sql):
    items = query_all(T(db, "aw-purchasing"), IndexName="GSI2", KeyConditionExpression=Key("GSI2PK").eq("EMPLOYEE#000258") & Key("GSI2SK").begins_with("PO#"))
    assert len(items) == q(sql, "SELECT COUNT(*) n FROM Purchasing.PurchaseOrderHeader WHERE EmployeeID = 258")[0]["n"]

@pattern("PUR-07")
def test_pur07_open_pos(db, sql):
    for s in (1, 2):
        items = query_all(T(db, "aw-purchasing"), KeyConditionExpression=Key("PK").eq("POSTATUS#%d" % s))
        assert len(items) == q(sql, "SELECT COUNT(*) n FROM Purchasing.PurchaseOrderHeader WHERE Status = %s", s)[0]["n"]

# ---------------- HR ----------------
@pattern("HR-01")
def test_hr01_employee_profile(db, sql):
    items = query_all(T(db, "aw-hr"), KeyConditionExpression=Key("PK").eq("EMPLOYEE#000004"))
    cur = [i for i in items if i["type"] == "DepartmentAssignment" and "end_date" not in i]
    r = q(sql, "SELECT d.Name FROM HumanResources.EmployeeDepartmentHistory h JOIN HumanResources.Department d ON d.DepartmentID = h.DepartmentID WHERE h.BusinessEntityID = 4 AND h.EndDate IS NULL")
    assert [c["department_name"] for c in cur] == [x["Name"] for x in r]
    pay = max((i for i in items if i["type"] == "PayRate"), key=lambda i: i["SK"])
    assert pay["rate"] == q(sql, "SELECT TOP 1 Rate FROM HumanResources.EmployeePayHistory WHERE BusinessEntityID = 4 ORDER BY RateChangeDate DESC")[0]["Rate"]

@pattern("HR-02")
def test_hr02_history(db, sql):
    items = query_all(T(db, "aw-hr"), KeyConditionExpression=Key("PK").eq("EMPLOYEE#000004") & Key("SK").begins_with("PAY#"), ScanIndexForward=False)
    assert [i["rate"] for i in items] == [r["Rate"] for r in q(sql, "SELECT Rate FROM HumanResources.EmployeePayHistory WHERE BusinessEntityID = 4 ORDER BY RateChangeDate DESC")]

@pattern("HR-03")
def test_hr03_org_subtree_and_chain(db, sql):
    t = T(db, "aw-hr")
    mgr = t.get_item(Key={"PK": "EMPLOYEE#000003", "SK": "EMPLOYEE"})["Item"]
    sub = query_all(t, IndexName="GSI2", KeyConditionExpression=Key("GSI2PK").eq("ORG") & Key("GSI2SK").begins_with(mgr["org_path"]))
    exp = {r["BusinessEntityID"] for r in q(sql, "EXEC dbo.uspGetManagerEmployees @BusinessEntityID = 3")}
    assert {i["business_entity_id"] for i in sub} == exp | {3}
    e = t.get_item(Key={"PK": "EMPLOYEE#000017", "SK": "EMPLOYEE"})["Item"]; parts = e["org_path"].strip("/").split("/"); chain = []
    for n in range(len(parts) - 1, 0, -1):
        chain += [i["business_entity_id"] for i in query_all(t, IndexName="GSI2", KeyConditionExpression=Key("GSI2PK").eq("ORG") & Key("GSI2SK").eq("/" + "/".join(parts[:n]) + "/"))]
    assert set(chain) == {r["BusinessEntityID"] for r in q(sql, "SELECT m.BusinessEntityID FROM HumanResources.Employee m, HumanResources.Employee e "
        "WHERE e.BusinessEntityID = 17 AND m.BusinessEntityID <> 17 AND m.OrganizationNode.GetLevel() > 0 "
        "AND e.OrganizationNode.IsDescendantOf(m.OrganizationNode) = 1")}  # same chain as uspGetEmployeeManagers (below the CEO)

@pattern("HR-04")
def test_hr04_department_members(db, sql):
    for d in (1, 7, 16):
        items = query_all(T(db, "aw-hr"), IndexName="GSI1", KeyConditionExpression=Key("GSI1PK").eq("DEPARTMENT#%02d" % d))
        assert sorted(i["business_entity_id"] for i in items) == [r["BusinessEntityID"] for r in q(sql, "SELECT BusinessEntityID FROM HumanResources.EmployeeDepartmentHistory WHERE DepartmentID = %s AND EndDate IS NULL ORDER BY 1", d)]

@pattern("HR-05")
def test_hr05_update_conditional(db):
    t = T(db, "aw-hr"); c = t.meta.client; k = {"PK": "EMPLOYEE#000290", "SK": "EMPLOYEE"}
    v = t.get_item(Key=k)["Item"]["ver"]
    t.update_item(Key=k, UpdateExpression="SET marital_status = :m, ver = ver + :one", ConditionExpression="ver = :v", ExpressionAttributeValues={":m": "M", ":one": 1, ":v": v})
    with pytest.raises(c.exceptions.ConditionalCheckFailedException):
        t.update_item(Key=k, UpdateExpression="SET marital_status = :m", ConditionExpression="ver = :v", ExpressionAttributeValues={":m": "S", ":v": v})

# ---------------- Reference ----------------
@pattern("REF-01")
def test_ref01_countries_states(db, sql):
    t = T(db, "aw-reference")
    assert len(query_all(t, KeyConditionExpression=Key("PK").eq("COUNTRIES"))) == q(sql, "SELECT COUNT(*) n FROM Person.CountryRegion")[0]["n"]
    st = query_all(t, KeyConditionExpression=Key("PK").eq("COUNTRY#CA") & Key("SK").begins_with("STATE#"))
    assert sorted(s["name"] for s in st) == sorted(r["Name"] for r in q(sql, "SELECT Name FROM Person.StateProvince WHERE CountryRegionCode = 'CA'"))

@pattern("REF-02")
def test_ref02_tax(db, sql):
    items = query_all(T(db, "aw-reference"), KeyConditionExpression=Key("PK").eq("TAX#001"))
    assert sorted(i["tax_rate"] for i in items) == sorted(r["TaxRate"] for r in q(sql, "SELECT TaxRate FROM Sales.SalesTaxRate WHERE StateProvinceID = 1"))

@pattern("REF-03")
def test_ref03_fx_on_date(db, sql):
    d = datetime.datetime(2013, 3, 15, 12)
    r = T(db, "aw-reference").query(KeyConditionExpression=Key("PK").eq("FX#USD#EUR") & Key("SK").lte(iso(d) + "~"), ScanIndexForward=False, Limit=1)["Items"][0]
    assert r["end_of_day_rate"] == q(sql, "SELECT TOP 1 EndOfDayRate FROM Sales.CurrencyRate WHERE FromCurrencyCode = 'USD' AND ToCurrencyCode = 'EUR' AND CurrencyRateDate <= %s ORDER BY CurrencyRateDate DESC", d)[0]["EndOfDayRate"]

@pattern("REF-04")
def test_ref04_ship_methods(db, sql):
    assert [i["name"] for i in query_all(T(db, "aw-reference"), KeyConditionExpression=Key("PK").eq("SHIPMETHODS"))] == [r["Name"] for r in q(sql, "SELECT Name FROM Purchasing.ShipMethod ORDER BY ShipMethodID")]

@pattern("REF-05")
def test_ref05_lists(db, sql):
    for pk, tbl in (("CURRENCIES", "Sales.Currency"), ("UNITS", "Production.UnitMeasure"), ("CULTURES", "Production.Culture")):
        assert len(query_all(T(db, "aw-reference"), KeyConditionExpression=Key("PK").eq(pk))) == q(sql, "SELECT COUNT(*) n FROM " + tbl)[0]["n"]

# ---------------- Cross-cutting (CDC) ----------------
def _apply(db, pairs, lsn):
    for t, item in pairs:
        try:
            db.Table(t).put_item(Item=item, ConditionExpression="attribute_not_exists(PK) OR src_lsn < :l", ExpressionAttributeValues={":l": lsn})
        except db.meta.client.exceptions.ConditionalCheckFailedException:
            pass

@pattern("CDC-01")
def test_cdc01_idempotent_upsert(db, sql):
    import sqlsrc
    m = awmap.load_mapping(); src = m["sources"]["Sales.SalesOrderHeader"]
    row = q(sql, src["source_sql"] + " WHERE h.SalesOrderID = 43659")[0]; pk = sqlsrc.primary_key(sql, "Sales.SalesOrderHeader")
    row = dict(row, Comment="cdc-test")
    _apply(db, awmap.items_for_row("Sales.SalesOrderHeader", src, row, pk, "0x%020x" % 2), "0x%020x" % 2)
    _apply(db, awmap.items_for_row("Sales.SalesOrderHeader", src, dict(row, Comment="stale"), pk, "0x%020x" % 1), "0x%020x" % 1)  # older LSN ignored
    _apply(db, awmap.items_for_row("Sales.SalesOrderHeader", src, row, pk, "0x%020x" % 2), "0x%020x" % 2)  # replay ignored
    assert T(db, "aw-sales").get_item(Key={"PK": "ORDER#0000043659", "SK": "ORDER"})["Item"]["comment"] == "cdc-test"
    orig = q(sql, src["source_sql"] + " WHERE h.SalesOrderID = 43659")[0]
    T(db, "aw-sales").put_item(Item=awmap.items_for_row("Sales.SalesOrderHeader", src, orig, pk)[0][1])

@pattern("CDC-02")
def test_cdc02_delete_becomes_tombstone(db, sql):
    import sqlsrc
    m = awmap.load_mapping(); src = m["sources"]["Sales.SalesOrderHeader"]
    row = q(sql, src["source_sql"] + " WHERE h.SalesOrderID = 43660")[0]; pk = sqlsrc.primary_key(sql, "Sales.SalesOrderHeader")
    _apply(db, awmap.tombstones_for_row("Sales.SalesOrderHeader", src, row, pk, "0x%020x" % 9), "0x%020x" % 9)
    item = T(db, "aw-sales").get_item(Key={"PK": "ORDER#0000043660", "SK": "ORDER"})["Item"]
    assert item["deleted"] is True and "GSI1PK" not in item
    hist = query_all(T(db, "aw-sales"), IndexName="GSI1", KeyConditionExpression=Key("GSI1PK").eq("CUSTOMER#%06d" % row["CustomerID"]))
    assert 43660 not in [i.get("sales_order_id") for i in hist]
    for t, it in awmap.items_for_row("Sales.SalesOrderHeader", src, row, pk):
        db.Table(t).put_item(Item=it)

@pattern("CDC-03")
def test_cdc03_fan_out_targets_findable(db, sql):
    links = query_all(T(db, "aw-customer"), IndexName="GSI1", KeyConditionExpression=Key("GSI1PK").eq("ADDRESS#001086"))
    assert {i["business_entity_id"] for i in links} == {r["BusinessEntityID"] for r in q(sql, "SELECT BusinessEntityID FROM Person.BusinessEntityAddress WHERE AddressID = 1086")}
    offers = query_all(T(db, "aw-catalog"), IndexName="GSI1", KeyConditionExpression=Key("GSI1PK").eq("OFFER#002"))
    assert len(offers) == q(sql, "SELECT COUNT(*) n FROM Sales.SpecialOfferProduct WHERE SpecialOfferID = 2")[0]["n"]

@pattern("CDC-04")
def test_cdc04_child_keys_need_only_own_row(db):
    m = awmap.load_mapping(); import re, sqlsrc
    sql = sqlsrc.connect()
    for table, src in m["sources"].items():
        cols = {r["name"] for r in q(sql, "SELECT name FROM sys.columns WHERE object_id = OBJECT_ID(%s)", table)}
        for spec in src["items"]:
            for k in ("PK", "SK", "GSI1PK", "GSI1SK", "GSI2PK", "GSI2SK"):
                for col in re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)", spec.get(k, "")):
                    # x_ helpers are pure functions of the row (formatting/aggregates computed in source_sql) or documented copies
                    assert col in cols or col.startswith("x_") or col in ("stock_qty",), (table, k, col)

def test_every_dynamodb_pattern_is_designed_and_tested():
    ap = json.load(open(os.path.join(ROOT, "docs/design/access-patterns.json")))
    keys = {p["id"] for p in yaml.safe_load(open(os.path.join(ROOT, "design/mapping/access-pattern-keys.yaml")))["patterns"]}
    served = {p["id"] for p in ap["patterns"] if p["scope"] == "dynamodb"}
    from conftest import EXECUTED
    assert served == keys, (served ^ keys)
    assert served <= EXECUTED, served - EXECUTED
