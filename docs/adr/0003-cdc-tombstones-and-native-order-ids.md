# ADR 0003: SQL deletes become tombstones; DynamoDB-native order ids

Status: Accepted (decisions D4, D5, D10)

## Decision
- CDC applies SQL deletes as tombstone items (`deleted=true`, keys kept, GSI keys removed, `ttl` added later) so Redshift zero-ETL sees deletes.
- Every CDC write is conditional on `src_lsn` (idempotent, ordered).
- The .NET 10 app writes orders directly to DynamoDB (`src='ddb'`); ids come from an atomic counter starting at 1,000,000,000, order number `SO-DDB-<id>`. The old app writes SQL → CDC (one-way). Side-by-side cutover.
## Consequences
Reads filter `deleted` (FilterExpression `attribute_not_exists(deleted)` or app-side); GSIs exclude tombstones automatically. Uniqueness markers that are tombstoned must be treated as free (`attribute_not_exists(PK) OR deleted = true`).
