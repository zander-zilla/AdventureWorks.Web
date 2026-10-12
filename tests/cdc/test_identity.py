"""Bulk load and CDC must produce identical items (needs the local SQL Server with AdventureWorks2022; skipped otherwise).
SQL Server is only the *reference* here (the bulk loader's source_sql); the CDC side never reads SQL (ADR 0005).
For every mapped table, sample rows are turned into items (a) the bulk-loader way and (b) through the CDC enrichment from
an event image (as Debezium/DMS deliver it, computed columns stripped) + lookups of the related items in a DynamoDB
stand-in holding the bulk-loaded items, and compared. Snapshot-refresh targets are also rebuilt from their own items."""
import os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "cdc"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "loader"))
from awcdc import transform as T

try:
    import sqlsrc, awmap
    CONN = sqlsrc.connect()
except Exception:  # pragma: no cover
    CONN = None

M = T.load_json(T.default_mapping_path())
YAML = awmap.load_mapping() if CONN is not None else None
LSN = "0x" + "1" * 20

# every source whose items the lookups / refresh finds read
PARENTS = ["Production.ProductCategory", "Production.ProductSubcategory", "Production.ProductModel", "Production.ProductDescription",
           "Production.ProductPhoto", "Sales.SpecialOffer", "Production.Location", "Production.Product", "Production.ProductInventory",
           "Sales.SalesReason", "Person.PhoneNumberType", "HumanResources.Department", "HumanResources.Shift", "Person.CountryRegion",
           "Purchasing.Vendor", "Person.Person", "Sales.Store", "Sales.SalesTerritory", "Purchasing.ShipMethod", "Person.Address",
           "Person.StateProvince", "Sales.CreditCard", "Sales.CurrencyRate", "Person.AddressType", "Person.ContactType", "Sales.Customer"]
_CACHE = {}


def column_types(table):
    if table not in _CACHE:
        cur = CONN.cursor()
        cur.execute("SELECT c.name, c.is_computed FROM sys.columns c WHERE c.object_id = OBJECT_ID(%s)", [table])
        _CACHE[table] = cur.fetchall()
    return _CACHE[table]


def bulk_rows(table, n=40):
    """Deterministic spread over the whole table (first, last and evenly spaced rows)."""
    cur = CONN.cursor(); cur.execute(sqlsrc.source_query(table, YAML["sources"][table])); rows = cur.fetchall()
    step = max(1, len(rows) // n)
    return rows[::step][:n] + rows[-3:]


def image_of(table, row):
    base = {c["name"] for c in column_types(table) if not c["is_computed"]}
    return {k: v for k, v in row.items() if k in base}


def parent_sink():
    """DynamoDB stand-in holding the bulk-loaded items the lookups read."""
    if "sink" not in _CACHE:
        sink = T.MemorySink()
        for t in PARENTS:
            src = YAML["sources"][t]; cur = CONN.cursor(); cur.execute(sqlsrc.source_query(t, src))
            for row in cur.fetchall():
                for tbl, item in awmap.items_for_row(t, src, row, M["sources"][t]["primary_key"]):
                    sink.put(tbl, awmap_roundtrip(item), item["src_lsn"])
        _CACHE["sink"] = sink
    return _CACHE["sink"]


def awmap_roundtrip(item):
    """What DynamoDB hands back: every number as Decimal."""
    import decimal
    def conv(v):
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return decimal.Decimal(str(v))
        if isinstance(v, dict):
            return {k: conv(x) for k, x in v.items()}
        return v
    return {k: conv(v) for k, v in item.items()}


def enricher():
    return T.Enricher(M, parent_sink(), attempts=1, sleep=lambda s: None)


@pytest.mark.skipif(CONN is None, reason="SQL Server not reachable")
@pytest.mark.parametrize("table", sorted(M["sources"]))
def test_bulk_load_and_cdc_items_identical_without_sql(table):
    enr = enricher(); src = YAML["sources"][table]; pk = M["sources"][table]["primary_key"]
    for row in bulk_rows(table):
        bulk = awmap.items_for_row(table, src, row, pk, LSN, "t")
        image = image_of(table, row)
        got = awmap.items_for_row(table, M["sources"][table], enr.current(table, image), pk, LSN, "t")
        assert got == bulk, (table, image)
        # delete / before image (lenient, no waiting): same item keys -> correct tombstones
        old = awmap.items_for_row(table, M["sources"][table], enr.from_image(table, image), pk, LSN, "t")
        assert [(t, i["PK"], i["SK"]) for t, i in old] == [(t, i["PK"], i["SK"]) for t, i in bulk]


REFRESHED = sorted({r["refresh"] for r in T.load_refresh_rules()})


@pytest.mark.skipif(CONN is None, reason="SQL Server not reachable")
@pytest.mark.parametrize("table", REFRESHED)
def test_refresh_rebuild_from_own_item_matches_bulk_load(table):
    """Snapshot refresh rebuilds a dependent row from its replicated item (+ lookups): must equal the bulk-load items."""
    enr = enricher(); src = YAML["sources"][table]; pk = M["sources"][table]["primary_key"]
    for row in bulk_rows(table, 20):
        bulk = awmap.items_for_row(table, src, row, pk, LSN, "t")
        own = awmap_roundtrip(next(i for _, i in bulk if not i.get("derived") and i["src_table"] == table))
        got = awmap.items_for_row(table, M["sources"][table], enr.rebuild(table, T.image_from_item(M, table, own)), pk, LSN, "t")
        assert got == bulk, table


def test_mapping_json_keeps_every_transform_input():
    """mapping.json must carry everything awmap.items_for_row reads from a source (omit, transforms, source_sql, items)."""
    import awmap as A
    y = A.load_mapping()
    for t, src in y["sources"].items():
        for k in ("omit", "transforms", "source_sql"):  # items are expanded (extra keys), checked by the identity test
            if src.get(k):
                assert M["sources"][t].get(k) == src[k], (t, k)


def test_enrichment_config_covers_every_joined_or_computed_table():
    cfg = T.load_enrichment(); y = awmap.load_mapping()
    joined = {t for t, s in y["sources"].items() if s.get("source_sql")}
    assert joined <= set(cfg["lookup"])
    assert "sql" not in cfg  # no table is re-read from SQL Server any more
