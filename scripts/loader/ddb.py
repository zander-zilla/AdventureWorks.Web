"""DynamoDB (Local) helpers: table creation from the mapping.
DynamoDB Local is effectively single-threaded per JVM, so for the full load we run one DynamoDB Local per table:
set DDB_MULTI=1 and table i (sorted name order) is served at port DDB_PORT_BASE+i. Otherwise all tables use DDB_ENDPOINT."""
import os, boto3

TABLES = ["aw-catalog", "aw-customer", "aw-hr", "aw-inventory", "aw-purchasing", "aw-reference", "aw-sales"]

def _res(endpoint):
    return boto3.resource("dynamodb", endpoint_url=endpoint, region_name=os.environ.get("AWS_REGION", "us-east-1"),
                          aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "local"),
                          aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "local"))

def endpoint_for(table):
    if os.environ.get("DDB_MULTI") == "1":
        return "http://localhost:%d" % (int(os.environ.get("DDB_PORT_BASE", "8001")) + TABLES.index(table))
    return os.environ.get("DDB_ENDPOINT", "http://localhost:8000")

class _Router:
    """Looks like a boto3 DynamoDB resource but routes Table(name) to that table's endpoint."""
    def __init__(self):
        self._r = {}
        self.meta = self.res(TABLES[0]).meta
    def res(self, table):
        ep = endpoint_for(table)
        if ep not in self._r:
            self._r[ep] = _res(ep)
        return self._r[ep]
    def Table(self, name):
        return self.res(name).Table(name)

def resource():
    return _Router()

def create_tables(mapping, recreate=False):
    router = resource()
    for name, t in mapping["tables"].items():
        c = router.res(name).meta.client
        if name in c.list_tables()["TableNames"]:
            if not recreate:
                continue
            c.delete_table(TableName=name); c.get_waiter("table_not_exists").wait(TableName=name)
        attrs = [{"AttributeName": a, "AttributeType": "S"} for a in ["PK", "SK"] + [g + s for g in t["gsis"] for s in ("PK", "SK")]]
        gsis = [{"IndexName": g, "KeySchema": [{"AttributeName": g + "PK", "KeyType": "HASH"}, {"AttributeName": g + "SK", "KeyType": "RANGE"}],
                 "Projection": {"ProjectionType": "ALL"}} for g in t["gsis"]]
        kw = dict(TableName=name, BillingMode="PAY_PER_REQUEST", AttributeDefinitions=attrs,
                  KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
                  StreamSpecification={"StreamEnabled": True, "StreamViewType": "NEW_AND_OLD_IMAGES"})
        if gsis:
            kw["GlobalSecondaryIndexes"] = gsis
        c.create_table(**kw); c.get_waiter("table_exists").wait(TableName=name)
        try:
            c.update_time_to_live(TableName=name, TimeToLiveSpecification={"Enabled": True, "AttributeName": "ttl"})
        except Exception:
            pass
