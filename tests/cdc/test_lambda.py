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
