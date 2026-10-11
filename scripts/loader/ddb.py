"""DynamoDB (Local) helpers: table creation from the mapping."""
import os, boto3

def resource():
    return boto3.resource("dynamodb", endpoint_url=os.environ.get("DDB_ENDPOINT", "http://localhost:8000"),
                          region_name=os.environ.get("AWS_REGION", "us-east-1"),
                          aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "local"),
                          aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "local"))

def create_tables(mapping, recreate=False):
    r = resource(); c = r.meta.client
    existing = set(c.list_tables()["TableNames"])
    for name, t in mapping["tables"].items():
        if name in existing:
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
