"""Lambda handler: partial batch failure semantics (no AWS calls)."""
import base64, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "cdc", "lambda"))
import handler as H


class Tr:
    def __init__(self, fail_on):
        self.fail_on, self.applied = fail_on, []
    def apply(self, ch):
        if ch.after and ch.after.get("SalesOrderID") == self.fail_on:
            raise RuntimeError("boom")
        self.applied.append(ch.after["SalesOrderID"])


class Rows:
    column_types = staticmethod(lambda t: [{"name": "SalesOrderID", "st": "int"}])


def rec(seq, oid, rtype="data"):
    msg = {"metadata": {"record-type": rtype, "operation": "insert", "schema-name": "Sales", "table-name": "SalesOrderHeader",
                        "timestamp": "2026-10-11T22:00:00Z"}, "data": {"SalesOrderID": oid, "AR_H_CHANGE_SEQ": str(1000 + oid)}}
    return {"kinesis": {"sequenceNumber": seq, "data": base64.b64encode(json.dumps(msg).encode()).decode()}}


def test_partial_batch_failure_stops_at_first_failure():
    tr = Tr(fail_on=2)
    out = H.handler({"Records": [rec("s1", 1), rec("s0", 0, "control"), rec("s2", 2), rec("s3", 3)]}, None, ctx={"rows": Rows, "tr": tr})
    assert out == {"batchItemFailures": [{"itemIdentifier": "s2"}]} and tr.applied == [1]


def test_all_ok():
    tr = Tr(fail_on=None)
    assert H.handler({"Records": [rec("a", 1), rec("b", 2)]}, None, ctx={"rows": Rows, "tr": tr}) == {"batchItemFailures": []}


def test_order_before_customer_fails_the_record_then_succeeds_on_redelivery():
    """Real transform + in-memory DynamoDB: the DMS order record whose customer has not replicated yet is reported as a
    batch item failure (Kinesis retries it; after MaximumRetryAttempts it goes to the DLQ); on redelivery it applies."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
    import test_transform as TT
    T = TT.T
    sink = T.MemorySink(); TT.seed_order_parents(sink, customer=False)
    rows = T.Enricher(TT.M, sink, attempts=2, backoff_ms=1, sleep=lambda s: None)
    ctx = {"rows": rows, "tr": T.Transformer(rows, sink, mapping=TT.M, rules=[], clock=lambda: TT.NOW)}
    o = TT.order(); data = {k: (v.isoformat() if hasattr(v, "isoformat") else str(v) if v is not None and not isinstance(v, (bool, int)) else v)
                            for k, v in o.items()}
    msg = {"metadata": {"record-type": "data", "operation": "insert", "schema-name": "Sales", "table-name": "SalesOrderHeader",
                        "timestamp": "2026-10-11T22:00:00Z"}, "data": dict(data, AR_H_CHANGE_SEQ="5000")}
    batch = {"Records": [{"kinesis": {"sequenceNumber": "o1", "data": base64.b64encode(json.dumps(msg).encode()).decode()}}]}
    assert H.handler(batch, None, ctx=ctx) == {"batchItemFailures": [{"itemIdentifier": "o1"}]}
    TT.seed_order_parents(sink)  # customer replicated meanwhile
    assert H.handler(batch, None, ctx=ctx) == {"batchItemFailures": []}
    assert sink.raw("aw-sales", "ORDER#0000043659", "ORDER")["customer_name"] == "Bike World"
