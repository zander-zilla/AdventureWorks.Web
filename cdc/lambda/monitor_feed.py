"""Replication monitor feed on AWS (Phase 8b, S-2): the CDC Lambda records each applied change in a small DynamoDB
table (<name>-cdc-monitor, 24 h TTL) so cdc/monitor_api can serve the Phase 4 monitor contract (/api/status,
/api/changes) without touching the domain tables. Best effort: a failed write is logged and never fails the batch.

Items:  PK "CHANGE", SK "<applied_ms 13 digits>#<kinesis seq>"   one recent change (report JSON, table, op, lag, ttl)
        PK "STATUS", SK "STATUS"                                 counters: changes (ADD), last_position, updated_ms
"""
import datetime, decimal, json, os, time

TTL_S = 24 * 3600


def jdefault(o):  # same as cdc/consumer/consumer.py
    if isinstance(o, decimal.Decimal):
        return int(o) if o == o.to_integral_value() else float(o)
    if isinstance(o, (datetime.datetime, datetime.date)):
        return o.isoformat()
    if isinstance(o, (bytes, bytearray)):
        return "0x" + bytes(o).hex()
    if isinstance(o, set):
        return sorted(o)
    return str(o)


def report(ch, rep, mapping):
    """The consumer's per-change report (cdc/consumer/consumer.py Applier.apply_one)."""
    pk_cols = mapping["sources"][ch.table]["primary_key"] if mapping and ch.table in mapping.get("sources", {}) else []
    img = ch.after or ch.before or {}
    return {"row": rep.get("row"), "puts": rep.get("puts", []), "tombstones": rep.get("tombstones", []),
            "refreshed": rep.get("refreshed", 0), "skipped": rep.get("skipped", 0), "pk": {c: img.get(c) for c in pk_cols}}


class Feed:
    def __init__(self, table, mapping, clock=time.time):
        self.table, self.mapping, self.clock = table, mapping, clock

    def record(self, ch, rep, seq):
        try:
            now = int(self.clock() * 1000)
            lag = now - ch.commit_ts_ms if ch.commit_ts_ms else None
            self.table.put_item(Item={"PK": "CHANGE", "SK": "%013d#%s" % (now, seq), "table": ch.table, "op": ch.op,
                                      "position": ch.position, "commit_ms": ch.commit_ts_ms, "applied_ms": now, "lag_ms": lag,
                                      "report": json.dumps(report(ch, rep, self.mapping), default=jdefault),
                                      "ttl": int(now / 1000) + TTL_S})
            self.table.update_item(Key={"PK": "STATUS", "SK": "STATUS"},
                                   UpdateExpression="ADD changes :one SET last_position = :p, updated_ms = :t",
                                   ExpressionAttributeValues={":one": 1, ":p": ch.position, ":t": now})
        except Exception as e:  # noqa: BLE001  the monitor must never stop replication
            print(json.dumps({"level": "warn", "monitor_feed": repr(e)[:500]}))


def from_env(mapping):
    name = os.environ.get("CDC_MONITOR_TABLE")
    if not name:
        return None
    import boto3
    return Feed(boto3.resource("dynamodb").Table(name), mapping)
