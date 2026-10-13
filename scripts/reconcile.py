#!/usr/bin/env python3
"""Reconcile SQL Server (AdventureWorks2022) against DynamoDB after bulk load + CDC.
For each mapped source table: SQL row count, expected item count (via the mapping), items found, content mismatches,
and a SHA-256 checksum over the canonical business content of expected vs actual items (meta attributes src_lsn,
updated_at, ver excluded). Also counts live items no SQL row explains (orphans) and tombstones per table.
Exit code 1 if anything differs. Usage: DDB_MULTI=1 python scripts/reconcile.py [--out docs/migration/reconcile.json]
C2-7: --original-only leaves generated rows (awmap.SYNTHETIC key ranges) and syn=1 items out, so the Chapter 1 check stays
exactly on the original data; --baseline FILE additionally requires the per-source counts and SQL checksums to equal the
committed original baseline (docs/chapter-2/synthetic/original-baseline.json); --write-baseline FILE writes it (SQL only)."""
import argparse, collections, concurrent.futures as cf, decimal, hashlib, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "loader"))
import awmap, ddb, sqlsrc

SKIP = {"src_lsn", "updated_at", "ver"}


def canon(item):
    def norm(v):
        if isinstance(v, (int, float, decimal.Decimal)) and not isinstance(v, bool):
            d = decimal.Decimal(str(v))  # DynamoDB returns every number as Decimal: compare numerically, no exponent form
            return "n:" + (str(int(d)) if d == d.to_integral_value() else format(d.normalize(), "f"))
        if isinstance(v, dict):
            return {k: norm(x) for k, x in sorted(v.items())}
        if isinstance(v, (list, tuple)):
            return [norm(x) for x in v]
        if isinstance(v, (bytes, bytearray)) or type(v).__name__ == "Binary":
            return bytes(v.value if hasattr(v, "value") else v).hex()
        if isinstance(v, set):
            return sorted(norm(x) for x in v)
        return v
    return json.dumps({k: norm(v) for k, v in sorted(item.items()) if k not in SKIP}, sort_keys=True, default=str)


def scan(table):
    """Memory-light: keep only a digest of each item's canonical content (+ tombstone flag)."""
    # small pages: DynamoDB Local builds each scan page in heap, 1 MB pages over ~0.5 M items ran 1-2 GB heaps out of memory
    t = ddb.resource().Table(table); out = {}; kw = {"Limit": int(os.environ.get("RECONCILE_SCAN_LIMIT", "1000"))}
    while True:
        r = t.scan(**kw)
        for i in r["Items"]:
            out[(i["PK"], i["SK"])] = (bool(i.get("deleted")), hashlib.sha1(canon(i).encode()).digest(), bool(i.get("syn")))
        if "LastEvaluatedKey" not in r:
            return table, out
        kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="/tmp/reconcile.json")
    ap.add_argument("--original-only", action="store_true"); ap.add_argument("--baseline"); ap.add_argument("--write-baseline")
    a = ap.parse_args()
    m = awmap.load_mapping()
    if a.write_baseline:
        a.original_only = True
        actual = {t: {} for t in m["tables"]}
    else:
        with cf.ThreadPoolExecutor(3) as ex:
            actual = dict(ex.map(scan, sorted(m["tables"])))
    explained = {t: set() for t in actual}
    conn = sqlsrc.connect(); report = {}; ok = True
    for name, src in sorted(m["sources"].items()):
        pk = sqlsrc.primary_key(conn, name); cur = conn.cursor(); cur.execute(sqlsrc.source_query(name, src))
        rows = 0; exp_items = {}
        for row in cur:
            if a.original_only and awmap.is_synthetic(name, row):
                continue
            rows += 1
            for t, item in awmap.items_for_row(name, src, row, pk, awmap.LOAD_LSN, "x"):
                exp_items[(t, item["PK"], item["SK"])] = canon(item)
        h_exp, h_act = hashlib.sha256(), hashlib.sha256(); missing = mismatch = 0; examples = []
        for key in sorted(exp_items):
            t, p, s = key; explained[t].add((p, s))
            e = exp_items[key]; h_exp.update(e.encode())
            got = actual[t].get((p, s))
            if got is None or got[0]:
                missing += 1; examples.append({"missing": key}) if len(examples) < 3 else None; continue
            h_act.update(e.encode() if got[1] == hashlib.sha1(e.encode()).digest() else got[1])
            if got[1] != hashlib.sha1(e.encode()).digest():
                mismatch += 1
                if len(examples) < 3:
                    gi = ddb.resource().Table(t).get_item(Key={"PK": p, "SK": s})["Item"]
                    ej, gj = json.loads(e), json.loads(canon(gi))
                    examples.append({"key": key, "diff": {k: [ej.get(k), gj.get(k)] for k in set(ej) | set(gj) if ej.get(k) != gj.get(k)}})
        r = {"sql_rows": rows, "expected_items": len(exp_items), "missing": missing, "mismatched": mismatch,
             "checksum_sql": h_exp.hexdigest()[:16], "checksum_ddb": h_act.hexdigest()[:16], "match": missing == 0 and mismatch == 0}
        if examples:
            r["examples"] = examples
        if a.write_baseline:
            r = {"sql_rows": rows, "expected_items": len(exp_items), "checksum_sql": r["checksum_sql"]}
        ok &= r.get("match", True); report[name] = r
    if a.write_baseline:
        json.dump({"note": "C2-7: per-source counts and SQL-side checksums of the ORIGINAL AdventureWorks2022 rows (scripts/reconcile.py --write-baseline)",
                   "per_source": report}, open(a.write_baseline, "w"), indent=1, sort_keys=True)
        print("baseline: %d sources, %d rows -> %s" % (len(report), sum(r["sql_rows"] for r in report.values()), a.write_baseline)); return
    baseline_diff = []
    if a.baseline:
        base = json.load(open(a.baseline))["per_source"]
        for n in sorted(set(base) | set(report)):
            b, r = base.get(n), report.get(n)
            if not b or not r or (b["sql_rows"], b["expected_items"], b["checksum_sql"]) != (r["sql_rows"], r["expected_items"], r["checksum_sql"]):
                baseline_diff.append({"source": n, "baseline": b, "now": r and {k: r[k] for k in ("sql_rows", "expected_items", "checksum_sql")}})
        ok &= not baseline_diff
    native = {(n["table"], n["PK"], n["SK"]) for n in m.get("native_items", [])}
    tables = {}
    for t, items in actual.items():
        live = [k for k, i in items.items() if not i[0]]
        orphans = [k for k in live if k not in explained[t] and (t,) + k not in native and not (a.original_only and items[k][2])]
        tables[t] = {"items": len(items), "live": len(live), "tombstones": len(items) - len(live), "orphans": len(orphans), "orphan_examples": orphans[:3]}
        ok &= not orphans
    summary = {"ok": ok, "sources": len(report), "sources_matching": sum(r["match"] for r in report.values()),
               "sql_rows": sum(r["sql_rows"] for r in report.values()), "expected_items": sum(r["expected_items"] for r in report.values()),
               "tables": tables, "original_only": bool(a.original_only)}
    if a.baseline:
        summary["baseline"] = {"file": a.baseline, "sources_differing": len(baseline_diff), "examples": baseline_diff[:3]}
    json.dump({"summary": summary, "per_source": report}, open(a.out, "w"), indent=1, default=str)
    print(json.dumps(summary, indent=1, default=str))
    for n, r in report.items():
        if not r["match"]:
            print("MISMATCH", n, json.dumps(r, default=str)[:600])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
