"""Bulk load and CDC must produce identical items (needs the local SQL Server with AdventureWorks2022; skipped otherwise).
For every mapped table, sample rows are turned into items (a) the bulk-loader way and (b) through the CDC transform from an
event image (as Debezium/DMS deliver it, computed columns stripped), and compared."""
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


@pytest.mark.skipif(CONN is None, reason="SQL Server not reachable")
@pytest.mark.parametrize("table", sorted(M["sources"]))
def test_bulk_load_and_cdc_items_identical(table):
    src = M["sources"][table]; rows = T.SqlRows(CONN, M); sink = T.MemorySink()
    tr = T.Transformer(rows, sink, mapping=M, rules=[], clock=lambda: 0)
    cur = CONN.cursor(); cur.execute("SELECT * FROM (%s) q" % rows.query(table)); bulk_rows = cur.fetchmany(25)
    computed = {c["name"] for c in rows.column_types(table) if c["is_computed"]}
    base_cols = {c["name"] for c in rows.column_types(table)}
    for row in bulk_rows:
        # reference = the bulk loader's own mapping (mapping.yaml), not mapping.json, so a lossy expansion is caught
        bulk = awmap.items_for_row(table, YAML["sources"][table], row, src["primary_key"], "0x" + "1" * 20, "t")
        image = {k: v for k, v in row.items() if k in base_cols and k not in computed}
        via_image = awmap.items_for_row(table, src, rows.from_image(table, image), src["primary_key"], "0x" + "1" * 20, "t")
        assert via_image == bulk
        rep = tr.apply(T.Change(table, "c", "0x" + "1" * 20, after=image))
        got = [(t, dict(i, updated_at="t")) for t, i in rep["puts"]]
        assert got == bulk


def test_mapping_json_keeps_every_transform_input():
    """mapping.json must carry everything awmap.items_for_row reads from a source (omit, transforms, source_sql, items)."""
    import awmap as A
    y = A.load_mapping()
    for t, src in y["sources"].items():
        for k in ("omit", "transforms", "source_sql"):  # items are expanded (extra keys), checked by the identity test
            if src.get(k):
                assert M["sources"][t].get(k) == src[k], (t, k)


PARENTS = ["Production.ProductCategory", "Production.ProductDescription", "Production.ProductPhoto", "Sales.SpecialOffer",
           "Production.Location", "Production.Product", "Sales.SalesReason", "Person.PhoneNumberType", "HumanResources.Department",
           "HumanResources.Shift", "Person.CountryRegion", "Purchasing.Vendor"]
_PARENT_SINK = {}


def parent_sink():
    """DynamoDB stand-in holding the bulk-loaded parent items the lookups read."""
    if not _PARENT_SINK:
        sink = T.MemorySink(); y = awmap.load_mapping()
        for t in PARENTS:
            src = y["sources"][t]; cur = CONN.cursor(); cur.execute(sqlsrc.source_query(t, src))
            for row in cur.fetchall():
                for tbl, item in awmap.items_for_row(t, src, row, M["sources"][t]["primary_key"]):
                    sink.put(tbl, item, item["src_lsn"])
        _PARENT_SINK["s"] = sink
    return _PARENT_SINK["s"]


@pytest.mark.skipif(CONN is None, reason="SQL Server not reachable")
@pytest.mark.parametrize("table", sorted(M["sources"]))
def test_image_and_lookup_enrichment_match_bulk_load(table):
    """Without SQL access (the AWS Lambda path): image-only and lookup tables must still produce the bulk-load items."""
    enr = T.Enricher(M, parent_sink(), sql_rows=None)
    if enr.mode(table) == "sql":
        pytest.skip("sql-mode table (needs joins), covered by test_bulk_load_and_cdc_items_identical")
    src = YAML["sources"][table]; rows = T.SqlRows(CONN, M)
    computed = {c["name"] for c in rows.column_types(table) if c["is_computed"]}
    base_cols = {c["name"] for c in rows.column_types(table)}
    cur = CONN.cursor(); cur.execute("SELECT TOP 25 * FROM (%s) q" % rows.query(table))
    for row in cur.fetchall():
        bulk = awmap.items_for_row(table, src, row, M["sources"][table]["primary_key"], "0x" + "1" * 20, "t")
        image = {k: v for k, v in row.items() if k in base_cols and k not in computed}
        got = awmap.items_for_row(table, src, enr.current(table, image), M["sources"][table]["primary_key"], "0x" + "1" * 20, "t")
        assert got == bulk


def test_enrichment_config_covers_every_joined_or_computed_table():
    cfg = T.load_enrichment(); y = awmap.load_mapping()
    joined = {t for t, s in y["sources"].items() if s.get("source_sql")}
    assert joined <= set(cfg["lookup"]) | set(cfg["sql"])
    assert not set(cfg["lookup"]) & set(cfg["sql"])
    assert len(cfg["sql"]) == 15
