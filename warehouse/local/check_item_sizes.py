#!/usr/bin/env python3
"""Zero-ETL pre-flight on a DynamoDB export: no single attribute may exceed 64 KB (65,535 bytes) or replication of the
whole table fails. Reports the largest attributes per table; exits 1 if any is over the limit."""
import argparse, glob, gzip, json, os
LIMIT = 65535

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--export", default="/tmp/aw-export"); a = ap.parse_args()
    worst = {}; over = []
    for p in sorted(glob.glob(os.path.join(a.export, "*.json.gz"))):
        t = os.path.basename(p).split(".")[0]
        with gzip.open(p, "rt") as f:
            for line in f:
                it = json.loads(line)["Item"]
                for k, v in it.items():
                    n = len(k.encode()) + len(json.dumps(v, ensure_ascii=False).encode())
                    if n > worst.get(t, ("", 0))[1]:
                        worst[t] = ("%s/%s" % (it.get("type", {}).get("S"), k), n)
                    if n > LIMIT:
                        over.append((t, it["PK"]["S"], it["SK"]["S"], k, n))
    for t, (k, n) in sorted(worst.items()):
        print("%-14s largest attribute %-36s %7d bytes (%.0f%% of limit)" % (t, k, n, 100.0 * n / LIMIT))
    for o in over:
        print("OVER LIMIT:", o)
    raise SystemExit(1 if over else 0)

if __name__ == "__main__":
    main()
