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


@pytest.mark.skipif(CONN is None, reason="SQL Server not reachable")
@pytest.mark.parametrize("table", sorted(M["sources"]))
def test_bulk_load_and_cdc_items_identical(table):
    src = M["sources"][table]; rows = T.SqlRows(CONN, M); sink = T.MemorySink()
    tr = T.Transformer(rows, sink, mapping=M, rules=[], clock=lambda: 0)
    cur = CONN.cursor(); cur.execute("SELECT * FROM (%s) q" % rows.query(table)); bulk_rows = cur.fetchmany(25)
    computed = {c["name"] for c in rows.column_types(table) if c["is_computed"]}
    base_cols = {c["name"] for c in rows.column_types(table)}
    for row in bulk_rows:
        bulk = awmap.items_for_row(table, src, row, src["primary_key"], "0x" + "1" * 20, "t")
        image = {k: v for k, v in row.items() if k in base_cols and k not in computed}
        via_image = awmap.items_for_row(table, src, rows.from_image(table, image), src["primary_key"], "0x" + "1" * 20, "t")
        assert via_image == bulk
        rep = tr.apply(T.Change(table, "c", "0x" + "1" * 20, after=image))
        got = [(t, dict(i, updated_at="t")) for t, i in rep["puts"]]
        assert got == bulk
