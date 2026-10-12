"""Phase 8b (S-2): CDC Lambda monitor feed + monitor API Lambda, contract-compatible with the Phase 4 consumer.
No AWS calls: fake DynamoDB table / sources."""
import json, os, sys
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "..", "cdc", "lambda"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "cdc", "monitor_api"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "cdc"))
import monitor_feed as F  # noqa: E402
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location("monitor_api_handler", os.path.join(HERE, "..", "..", "cdc", "monitor_api", "handler.py"))
A = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(A)
from awcdc import transform as T  # noqa: E402

FIXTURE = os.path.join(HERE, "..", "..", "showcase", "fixtures", "replication-replay")
MAPPING = {"sources": {"Sales.SalesOrderHeader": {"primary_key": ["SalesOrderID"]}}}


class FakeTable:
    def __init__(self):
        self.items, self.fail = {}, False

    def put_item(self, Item):
        if self.fail:
            raise RuntimeError("throttled")
        self.items[(Item["PK"], Item["SK"])] = dict(Item)

    def update_item(self, Key, UpdateExpression, ExpressionAttributeValues):
        it = self.items.setdefault((Key["PK"], Key["SK"]), dict(Key))
        it["changes"] = it.get("changes", 0) + ExpressionAttributeValues[":one"]
        it["last_position"], it["updated_ms"] = ExpressionAttributeValues[":p"], ExpressionAttributeValues[":t"]


class FakeSource:
    def __init__(self, table, running=True, dlq=0, broken=False):
        self.t, self.running, self.dlq, self.broken = table, running, dlq, broken

    def status_item(self):
        if self.broken:
            raise RuntimeError("AccessDenied")
        return self.t.items.get(("STATUS", "STATUS"))

    def recent(self, limit, table=None):
        if self.broken:
            raise RuntimeError("AccessDenied")
        rows = sorted((v for (pk, _), v in self.t.items.items() if pk == "CHANGE"), key=lambda v: v["SK"], reverse=True)
        return [r for r in rows if not table or r["table"] == table][:limit]

    def dlq_depth(self):
        return self.dlq

    def task_running(self):
        return self.running


def ch(oid, pos, op="c", ts=1_000):
    return T.Change(table="Sales.SalesOrderHeader", op=op, position=pos, after={"SalesOrderID": oid, "Status": 5}, commit_ts_ms=ts)


def rep(oid):
    return {"row": {"SalesOrderID": oid}, "puts": [["aw-sales", {"PK": "ORDER#%010d" % oid, "SK": "ORDER"}]], "tombstones": [],
            "refreshed": 0, "skipped": 0}


def feed(table, times=(3.5, 5.0, 6.0)):
    it = iter(times)
    return F.Feed(table, MAPPING, clock=lambda: next(it))


def get(path, src, **qs):
    r = A.handler({"rawPath": path, "queryStringParameters": qs or None}, None, src=src)
    return r["statusCode"], json.loads(r["body"])


def test_feed_records_consumer_shaped_changes_and_status():
    t = FakeTable(); f = feed(t)
    f.record(ch(1, "0x01"), rep(1), "s1"); f.record(ch(2, "0x02"), rep(2), "s2")
    code, st = get("/api/status", FakeSource(t))
    assert code == 200 and st["changes"] == 2 and st["last_position"] == "0x02" and st["paused"] is False
    assert st["lag_ms"] == {"last": 4000, "p50": 4000, "max": 4000}  # applied at 3.5 s / 5.0 s, committed at 1.0 s
    code, rows = get("/api/changes", FakeSource(t), limit="1")
    assert code == 200 and len(rows) == 1 and rows[0]["pk"] == {"SalesOrderID": 2} and rows[0]["position"] == "0x02"


def test_same_keys_as_the_recorded_replay_contract():
    """The monitor page (cdc/monitor/index.html) reads these keys; the AWS API must offer every key the replay has."""
    t = FakeTable(); feed(t).record(ch(1, "0x01"), rep(1), "s1")
    src = FakeSource(t)
    replay_st = json.load(open(os.path.join(FIXTURE, "status.json")))
    replay_ch = json.load(open(os.path.join(FIXTURE, "changes.json")))[0]
    st = get("/api/status", src)[1]; c = get("/api/changes", src)[1][0]
    assert set(replay_st) - {"replay"} <= set(st) and set(replay_st["lag_ms"]) == set(st["lag_ms"])
    assert set(replay_ch) <= set(c)
    assert "replay" not in st  # the monitor labels the state 'streaming', not 'recorded replay'


def test_table_filter_and_limit_bounds():
    t = FakeTable(); f = feed(t)
    f.record(ch(1, "0x01"), rep(1), "s1")
    other = T.Change(table="Sales.SalesOrderDetail", op="c", position="0x02", after={"SalesOrderID": 1}, commit_ts_ms=1000)
    f.record(other, rep(1), "s2")
    rows = get("/api/changes", FakeSource(t), table="Sales.SalesOrderDetail", limit="9999")[1]
    assert [r["table"] for r in rows] == ["Sales.SalesOrderDetail"]
    assert get("/api/changes", FakeSource(t), limit="x")[0] == 400


def test_unavailable_returns_503_so_cloudfront_fails_over_to_the_recorded_sample():
    assert get("/api/status", FakeSource(FakeTable(), running=False))[0] == 503  # nothing recorded, CDC stopped
    assert get("/api/status", FakeSource(FakeTable(), broken=True))[0] == 503
    assert get("/api/changes", FakeSource(FakeTable(), broken=True))[0] == 503
    code, st = get("/api/status", FakeSource(FakeTable(), running=True))  # CDC running, no change yet: real (empty) data
    assert code == 200 and st["changes"] == 0
    assert get("/nope", FakeSource(FakeTable()))[0] == 404


def test_feed_failure_never_fails_replication(capsys):
    t = FakeTable(); t.fail = True
    feed(t).record(ch(1, "0x01"), rep(1), "s1")
    assert "monitor_feed" in capsys.readouterr().out


def test_cdc_lambda_records_applied_changes_only():
    sys.path.insert(0, os.path.join(HERE))
    import test_lambda as TL
    H = TL.H

    class Tr:
        def apply(self, c):
            return {"ignored": True} if c.after["SalesOrderID"] == 2 else rep(c.after["SalesOrderID"])

    seen = []

    class Mon:
        def record(self, c, r, seq):
            seen.append(seq)
    out = H.handler({"Records": [TL.rec("a", 1), TL.rec("b", 2), TL.rec("c", 3, "control")]}, None,
                    ctx={"rows": TL.Rows, "tr": Tr(), "monitor": Mon()})
    assert out == {"batchItemFailures": []} and seen == ["a"]


def test_showcase_build_aws_mode_keeps_the_replay_fallback(tmp_path):
    """push-showcase.sh builds with --monitor-mode aws; the replay files must still be uploaded (CloudFront failover)."""
    sys.path.insert(0, os.path.join(HERE, "..", "..", "showcase"))
    import build
    out = build.build(str(tmp_path / "dist"), monitor_mode="aws")
    cfg = json.load(open(os.path.join(out, "config.json")))
    assert cfg["monitorMode"] == "aws" and cfg["monitorApi"] == ""  # same origin: CloudFront /api/*
    assert json.load(open(os.path.join(out, "api", "status")))["replay"]
