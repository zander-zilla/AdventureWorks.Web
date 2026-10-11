"""AdventureWorks CDC transform: SQL change events -> DynamoDB writes, driven by design/mapping/mapping.json.
Shared by the local Debezium consumer and the AWS Lambda (Kinesis/DMS)."""
from .transform import Change, Transformer  # noqa: F401
