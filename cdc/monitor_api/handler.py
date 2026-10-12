"""Replication monitor API on AWS (Phase 8b, S-2; ADR 0009 decision 2a).

Serves the Phase 4 monitor contract (cdc/consumer/consumer.py) from what the CDC Lambda records in <name>-cdc-monitor
(cdc/lambda/monitor_feed.py), so the showcase's Live Replication tab streams real changes when deployed:
  GET /api/status            {paused, queued, applied_events, dlq, changes, last_position, lag_ms{last,p50,max}, source}
  GET /api/changes?limit=N[&table=Schema.Table]   newest first, same item shape as the consumer
Fronted by CloudFront (origin access control -> Lambda Function URL, AWS_IAM) in an origin group whose secondary is the
S3 bucket holding the recorded replay: any 5xx here (data unavailable, no change recorded yet while the DMS task is
not running, Lambda error/throttle) makes CloudFront serve the recorded sample instead.
Env: MONITOR_TABLE, DLQ_URL (optional), DMS_TASK_ARN (optional).
"""
import json, os

LAG_WINDOW = 200


class Unavailable(Exception):
    pass


def _num(v):
    if v is None:
        return None
    return int(v) if float(v) == int(v) else float(v)


class Source:
    """AWS reads (boto3); tests pass a fake with the same three methods."""

    def __init__(self):
        import boto3
        self.table = boto3.resource("dynamodb").Table(os.environ["MONITOR_TABLE"])
        self.sqs, self.dms = boto3.client("sqs"), boto3.client("dms")

    def status_item(self):
        return self.table.get_item(Key={"PK": "STATUS", "SK": "STATUS"}).get("Item")

    def recent(self, limit, table=None):
        from boto3.dynamodb.conditions import Attr, Key
        args = {"KeyConditionExpression": Key("PK").eq("CHANGE"), "ScanIndexForward": False}
        if table:
            args["FilterExpression"] = Attr("table").eq(table)
        out, start = [], None
        while len(out) < limit:
            page = self.table.query(Limit=max(limit, 50), **args, **({"ExclusiveStartKey": start} if start else {}))
            out += page.get("Items", [])
            start = page.get("LastEvaluatedKey")
            if not start:
                break
        return out[:limit]

    def dlq_depth(self):
        url = os.environ.get("DLQ_URL")
        if not url:
            return None
        a = self.sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages"])["Attributes"]
        return int(a["ApproximateNumberOfMessages"])

    def task_running(self):
        arn = os.environ.get("DMS_TASK_ARN")
        if not arn:
            return None
        t = self.dms.describe_replication_tasks(Filters=[{"Name": "replication-task-arn", "Values": [arn]}])["ReplicationTasks"]
        return bool(t) and t[0]["Status"] == "running"


def change(item):
    return {"id": item["SK"], "table": item["table"], "op": item["op"], "position": item["position"],
            "commit_ms": _num(item.get("commit_ms")), "applied_ms": _num(item.get("applied_ms")), "lag_ms": _num(item.get("lag_ms")),
            **json.loads(item["report"])}


def status(src):
    try:
        st = src.status_item()
        running = src.task_running()
    except Exception as e:  # noqa: BLE001
        raise Unavailable(repr(e))
    if not st and running is not True:
        raise Unavailable("no change recorded yet and the DMS task is not running")
    lags = [c["lag_ms"] for c in map(change, src.recent(LAG_WINDOW)) if c["lag_ms"] is not None]
    s = sorted(lags)
    try:
        dlq = src.dlq_depth()
    except Exception:  # noqa: BLE001
        dlq = None
    st = st or {}
    return {"paused": running is False, "queued": None, "applied_events": _num(st.get("changes", 0)), "dlq": dlq,
            "failed": dlq, "changes": _num(st.get("changes", 0)), "last_position": st.get("last_position"),
            "lag_ms": {"last": lags[0] if lags else None, "p50": s[len(s) // 2] if s else None, "max": s[-1] if s else None},
            "source": "aws"}


def changes(src, limit=50, table=None):
    limit = max(1, min(int(limit), 500))
    try:
        return [change(i) for i in src.recent(limit, table)]
    except Exception as e:  # noqa: BLE001
        raise Unavailable(repr(e))


def _resp(code, obj):
    return {"statusCode": code, "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
            "body": json.dumps(obj)}


_src = []


def handler(event, context, src=None):
    if src is None:
        if not _src:
            _src.append(Source())
        src = _src[0]
    path = (event.get("rawPath") or event.get("path") or "/").rstrip("/")
    qs = event.get("queryStringParameters") or {}
    try:
        if path.endswith("/api/status"):
            return _resp(200, status(src))
        if path.endswith("/api/changes"):
            try:
                limit = int(qs.get("limit", 50))
            except ValueError:
                return _resp(400, {"error": "limit must be a number"})
            return _resp(200, changes(src, limit, qs.get("table") or None))
        if path.endswith("/health"):
            return _resp(200, {"ok": True})
        return _resp(404, {"error": "not found"})
    except Unavailable as e:
        print(json.dumps({"level": "warn", "unavailable": str(e)[:500]}))
        return _resp(503, {"error": "live replication data unavailable", "fallback": "recorded sample"})
