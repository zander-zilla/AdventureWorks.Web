# ADR 0004: Phase 3 operational decisions

Status: Accepted (2026-10-11, John)

1. **Native order ids:** one atomic counter increment (`UpdateItem COUNTER/ORDER ADD next_id 1`) per DynamoDB-native order. No id blocks; ~1 order/s is far below one partition's write limit.
2. **Encryption:** customer-managed KMS keys for `aw-customer` and `aw-hr` (PII, pay, national id); ~~AWS-managed key~~ **AWS-owned key** for the other five tables. *Amended 2026-10-12 by decision W-1 (ADR 0007, accepted): DynamoDB zero-ETL rejects AWS-managed (`aws/dynamodb`) keys. AWS-owned keys cost nothing and are supported; the two CMKs carry key-policy statements that let `redshift.amazonaws.com` decrypt/create grants for this account's integrations (`infra/modules/dynamodb`).*
3. **GSI projection:** ALL on every GSI for now (small items; simpler reads and debugging). Revisit if cost matters.
4. **Tombstone TTL:** 7 days after the delete is captured (`ttl` = capture epoch + 604800). Redshift zero-ETL sees the tombstone well within that window; TTL expiry itself is also replicated as a delete.
5. **Checkout size:** the 100-action `TransactWriteItems` limit caps an order at ~95 lines (with cart cleanup in the same transaction); accepted and enforced by the app.
