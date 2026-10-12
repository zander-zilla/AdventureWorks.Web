#!/usr/bin/env python3
"""Load a DynamoDB export into the Postgres stand-in, in the zero-ETL landing shape:
landing."<table>" ("PK" varchar, "SK" varchar, value jsonb)  -- value = all other attributes, DynamoDB JSON.
Usage: python warehouse/local/load_landing.py --export /tmp/aw-export"""
import argparse, glob, gzip, io, json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import pg

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--export", default="/tmp/aw-export"); a = ap.parse_args()
    conn = pg.connect(); cur = conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS landing")
    tables = sorted({os.path.basename(p).split(".")[0] for p in glob.glob(os.path.join(a.export, "*.json.gz"))})
    for t in tables:
        cur.execute('DROP TABLE IF EXISTS landing."%s" CASCADE' % t)
        cur.execute('CREATE TABLE landing."%s" ("PK" varchar(2048) NOT NULL, "SK" varchar(2048) NOT NULL, value jsonb NOT NULL, PRIMARY KEY ("PK", "SK"))' % t)
        n = 0
        for p in sorted(glob.glob(os.path.join(a.export, t + ".*.json.gz"))):
            buf = io.StringIO()
            with gzip.open(p, "rt") as f:
                for line in f:
                    it = json.loads(line)["Item"]; pk = it.pop("PK")["S"]; sk = it.pop("SK")["S"]
                    buf.write("\t".join(x.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")
                                        for x in (pk, sk, json.dumps(it, ensure_ascii=False))) + "\n"); n += 1
            buf.seek(0); cur.copy_expert('COPY landing."%s" ("PK", "SK", value) FROM STDIN' % t, buf)
        conn.commit(); print("landing.%-14s %8d rows" % (t, n), flush=True)
    cur.execute("ANALYZE"); conn.commit()

if __name__ == "__main__":
    main()
