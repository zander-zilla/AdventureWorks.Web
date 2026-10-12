#!/usr/bin/env python3
"""Export every DynamoDB (Local) domain table in DynamoDB S3-export format (DYNAMODB_JSON: one {"Item": {...}} per line, gzip).
This is the same item encoding the zero-ETL integration lands in Redshift's `value` SUPER column.
Usage: DDB_MULTI=1 python warehouse/local/export_ddb.py --out /tmp/aw-export"""
import argparse, base64, concurrent.futures as cf, gzip, json, os, sys
import boto3
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts/loader"))
import ddb

def _b64(o):
    if isinstance(o, (bytes, bytearray)):
        return base64.b64encode(o).decode()  # B / BS values are base64 in DynamoDB exports
    raise TypeError(type(o))

def export(table, out, segments):
    # plain low-level client: items stay in DynamoDB JSON (the resource's client would deserialize them)
    client = boto3.client("dynamodb", endpoint_url=ddb.endpoint_for(table), region_name=os.environ.get("AWS_REGION", "us-east-1"),
                          aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "local"), aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "local"))
    def seg(i):
        path = os.path.join(out, "%s.%02d.json.gz" % (table, i)); n = 0; kw = {}
        with gzip.open(path, "wt", compresslevel=1) as f:
            while True:
                r = client.scan(TableName=table, Segment=i, TotalSegments=segments, **kw)
                for it in r["Items"]:
                    f.write(json.dumps({"Item": it}, separators=(",", ":"), ensure_ascii=False, default=_b64) + "\n"); n += 1
                if "LastEvaluatedKey" not in r:
                    return n
                kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]
    with cf.ThreadPoolExecutor(segments) as ex:
        return sum(ex.map(seg, range(segments)))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="/tmp/aw-export"); ap.add_argument("--segments", type=int, default=4)
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    counts = {}
    for t in ddb.TABLES:
        counts[t] = export(t, a.out, a.segments); print("%-14s %8d items" % (t, counts[t]), flush=True)
    json.dump(counts, open(os.path.join(a.out, "manifest.json"), "w"), indent=1)

if __name__ == "__main__":
    main()
