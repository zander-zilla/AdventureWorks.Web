#!/usr/bin/env python3
"""C2-7: count + checksum of the ORIGINAL rows of every user table in AdventureWorks2022 (generated key ranges left out).
Run before and after a synthetic load: the two files must be identical (tests/synthetic/test_load_sql.py)."""
import argparse, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "loader"))
import sqlsrc
from marking import original_where


def checksums(conn):
    cur = conn.cursor()
    cur.execute("""SELECT s.name + '.' + t.name t FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id
                   WHERE s.name IN ('Sales', 'Person', 'Production', 'Purchasing', 'HumanResources') AND t.is_ms_shipped = 0 ORDER BY 1""")
    out = {}
    for (t,) in [(r["t"],) for r in cur.fetchall()]:
        cur.execute("SELECT COUNT(*) n, CHECKSUM_AGG(BINARY_CHECKSUM(*)) c FROM %s WHERE %s" % (t, original_where(t)))
        r = cur.fetchone(); out[t] = [r["n"], r["c"]]
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); a = ap.parse_args()
    out = checksums(sqlsrc.connect()); json.dump(out, open(a.out, "w"), indent=1, sort_keys=True)
    print("original rows: %d tables, %d rows -> %s" % (len(out), sum(v[0] for v in out.values()), a.out))


if __name__ == "__main__":
    main()
