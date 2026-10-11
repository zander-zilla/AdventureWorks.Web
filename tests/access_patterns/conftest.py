import os, sys, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "loader"))
import ddb, sqlsrc, awmap  # noqa: E402
from boto3.dynamodb.conditions import Key, Attr  # noqa: E402

EXECUTED = set()

def pattern(pid):
    """Decorator recording which access-pattern ids are exercised."""
    def deco(fn):
        fn.pattern_id = pid
        EXECUTED.add(pid)
        return fn
    return deco

@pytest.fixture(scope="session")
def sql():
    c = sqlsrc.connect(); yield c; c.close()

@pytest.fixture(scope="session")
def db():
    return ddb.resource()

def q(sqlconn, query, *args):
    cur = sqlconn.cursor(); cur.execute(query, args or None); return cur.fetchall()

def query_all(table, **kw):
    items, resp = [], table.query(**kw)
    items += resp["Items"]
    while "LastEvaluatedKey" in resp and "Limit" not in kw:
        resp = table.query(ExclusiveStartKey=resp["LastEvaluatedKey"], **kw); items += resp["Items"]
    return [i for i in items if not i.get("deleted")]
