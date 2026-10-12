"""AWS Lambda: Kinesis (DMS JSON records) -> awcdc transform -> DynamoDB.

Event source mapping (Terraform, phase 7):
  - FunctionResponseTypes = ["ReportBatchItemFailures"]  (partial batch failure: we return the first failed record and
    everything after it in the shard batch is retried, preserving per-shard order)
  - BisectBatchOnFunctionError = true, MaximumRetryAttempts = 5, DestinationConfig.OnFailure = SQS DLQ (aw-cdc-dlq)
  - ParallelizationFactor = 1 (per-shard order; DMS partitions by schema.table + primary key so one row = one shard)
Idempotency: every write is conditional on src_lsn < position (DMS AR_H_CHANGE_SEQ), so Lambda retries, Kinesis
re-delivery and DLQ replays are safe; older events are ignored instead of overwriting newer state.
Enrichment reads the row through the mapping's source_sql from an RDS read replica (env SQL_HOST..., secret via
Secrets Manager in phase 7) so CDC items are identical to the bulk load.
"""
import base64, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # package layout: handler.py, awcdc/, awmap.py, sqlsrc.py, mapping.json, cdc-refresh.yaml
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts", "loader"))
from awcdc import transform as T  # noqa: E402

_state = {}


def _ctx():
    if not _state:
        import boto3, sqlsrc
        m = T.load_json(T.default_mapping_path())
        conn = sqlsrc.connect()
        rows = T.SqlRows(conn, m)
        _state.update(rows=rows, tr=T.Transformer(rows, T.DynamoDBSink(boto3.resource("dynamodb")), mapping=m))
    return _state


def handler(event, context, ctx=None):
    ctx = ctx or _ctx()
    failures = []
    for i, rec in enumerate(event.get("Records", [])):
        seq = rec["kinesis"]["sequenceNumber"]
        try:
            msg = json.loads(base64.b64decode(rec["kinesis"]["data"]))
            if msg.get("metadata", {}).get("record-type") != "data":
                continue  # control records
            ch = T.from_dms(msg, ctx["rows"].column_types)
            ctx["tr"].apply(ch)
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"level": "error", "sequenceNumber": seq, "error": repr(e)[:1000]}))
            failures.append({"itemIdentifier": seq})
            break  # stop: later records of this shard must not overtake the failed one
    return {"batchItemFailures": failures}
