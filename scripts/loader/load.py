#!/usr/bin/env python3
"""Bulk-load AdventureWorks2022 into DynamoDB (Local) using design/mapping/mapping.yaml.
Usage: python scripts/loader/load.py [--recreate] [--only Sales.SalesOrderHeader ...]"""
import argparse, collections, concurrent.futures as cf, json, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import awmap, ddb, sqlsrc

def load_table(table, src, lsn=awmap.LOAD_LSN):
    conn = sqlsrc.connect(); pk = sqlsrc.primary_key(conn, table)
    cur = conn.cursor(); cur.execute(sqlsrc.source_query(table, src))
    r = ddb.resource(); writers = {}; counts = collections.Counter(); rows = 0
    try:
        while True:
            batch = cur.fetchmany(2000)
            if not batch:
                break
            for row in batch:
                rows += 1
                for t, item in awmap.items_for_row(table, src, row, pk, lsn):
                    if t not in writers:
                        writers[t] = r.Table(t).batch_writer(overwrite_by_pkeys=["PK", "SK"])
                    writers[t].put_item(Item=item); counts[(t, item["type"])] += 1
    finally:
        for w in writers.values():
            w.__exit__(None, None, None)
        conn.close()
    return table, rows, counts

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--recreate", action="store_true"); ap.add_argument("--only", nargs="*")
    ap.add_argument("--workers", type=int, default=8); ap.add_argument("--stats", default=os.path.join(awmap.ROOT, "docs/design/load-stats.json"))
    a = ap.parse_args()
    m = awmap.load_mapping(); ddb.create_tables(m, recreate=a.recreate)
    r = ddb.resource()
    for n in m.get("native_items", []):
        r.Table(n["table"]).put_item(Item={"PK": n["PK"], "SK": n["SK"], "type": n["entity"], "src": "ddb", "ver": 1, **n["attributes"]})
    sources = {k: v for k, v in m["sources"].items() if not a.only or k in a.only}
    t0 = time.time(); per_table = collections.Counter(); per_entity = collections.Counter(); rows_total = 0
    with cf.ThreadPoolExecutor(a.workers) as ex:
        futs = [ex.submit(load_table, t, s) for t, s in sorted(sources.items(), key=lambda kv: -len(kv[0]))]
        for f in cf.as_completed(futs):
            table, rows, counts = f.result(); rows_total += rows
            for (t, e), n in counts.items():
                per_table[t] += n; per_entity["%s/%s" % (t, e)] += n
            print("%-48s %8d rows -> %8d items" % (table, rows, sum(counts.values())), flush=True)
    secs = round(time.time() - t0, 1)
    stats = {"source_rows": rows_total, "items_per_table": dict(sorted(per_table.items())), "items_total": sum(per_table.values()),
             "items_per_entity": dict(sorted(per_entity.items())), "seconds": secs}
    if not a.only:
        json.dump(stats, open(a.stats, "w"), indent=1)
    print(json.dumps({k: stats[k] for k in ("source_rows", "items_per_table", "items_total", "seconds")}, indent=1))

if __name__ == "__main__":
    main()
