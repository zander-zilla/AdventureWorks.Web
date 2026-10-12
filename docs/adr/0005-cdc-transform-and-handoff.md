# ADR 0005: One CDC transform for bulk load, Debezium and DMS; position-ordered conditional writes

Status: Accepted (2026-10-11, John; amended by Phase 4 follow-ups; amended 2026-10-11 by John: no SQL reads in CDC)

## Decision
- A single Python library (`cdc/awcdc`) applies changes, reusing the Phase 3 `awmap` code and `mapping.json`. Debezium
  (local) and DMS→Kinesis→Lambda (AWS) are only transports.
- **The transform never reads SQL Server** (amendment, John 2026-10-11). Rows are built per
  `design/mapping/cdc-enrichment.yaml` from the event's full row image + lookups (`GetItem`, or `Query` on a GSI) of the
  related items that are already replicated to DynamoDB + computed columns / `source_sql` expressions re-implemented in
  `awcdc.transform.COMPUTED` (incl. `hierarchyid.ToString()/GetLevel()` and `geography.Lat/Long`). This replaces the
  SQL re-read of the 15 join tables (Product, Document, ProductDocument, BillOfMaterials, SalesOrderHeader, SalesPerson,
  SalesTerritoryHistory, Customer, Store, PersonCreditCard, Address, BusinessEntityAddress, BusinessEntityContact,
  PurchaseOrderHeader, Employee). Snapshot refreshes (`cdc-refresh.yaml`) find dependents in DynamoDB (Query/GetItem;
  one filtered Scan for the rare territory rename) and rebuild them from their own items + lookups.
- **Out-of-order parents:** when a referenced item has not arrived yet (e.g. an order before its customer: DMS/Kinesis
  orders per primary key, not across tables), the lookup is retried a few times with exponential backoff
  (`CDC_LOOKUP_ATTEMPTS`=4, `CDC_LOOKUP_BACKOFF_MS`=100 → 0.1/0.2/0.4 s), then the event fails with `MissingParent`:
  the Lambda reports a partial batch failure (Kinesis retries the batch, `MaximumRetryAttempts`=5, then the SQS DLQ);
  the local consumer retries in order, then parks the event in its DLQ state. Nothing is written for a failed event.
  NULL foreign keys (LEFT JOINs) never wait; delete/before images never wait (only their keys matter).
- Identity with the bulk load is tested per table (all 68) with no SQL on the CDC side, and for every refresh target.
- Ordering: every item carries `src_lsn`; writes are `PutItem` conditional on `src_lsn < position`. Snapshot refreshes are
  in-place `UpdateItem`s that do not move `src_lsn`.
- Handoff: capture starts before the bulk load; the consumer buffers until the load is done, then applies (no gaps; duplicates are no-ops).
- Deletes → tombstones with `ttl` = capture + 7 days (P3-4).

## Consequences
+ One code path to test; identity is tested per table.  + At-least-once transports are safe.
+ No SQL Server access from the CDC path: **no RDS read replica**, no VPC/Secrets Manager wiring for the Lambda, no
  load on the source during the migration window; the Lambda package carries no SQL driver.
+ Rows reflect the image at that LSN (not the current SQL state), so intermediate states replay faithfully.
− Copies come from DynamoDB, so they are only as fresh as the parent's replication; ordering is restored by the bounded
  retry + batch retry/DLQ, and refreshes converge copies when the parent changes later.
− An event whose parent never arrives (parent filtered out, or replicated after the DLQ gave up) needs a DLQ replay
  after the parent is present (replays are idempotent).
− `x_is_vendor` (vendor address/contact copies) is an EXISTS check on the vendor item at the time the link replicates;
  AdventureWorks creates the vendor before its links. Refresh fan-out (e.g. a category rename updates ~100 products)
  runs inline; the territory → customer refresh is a filtered Scan (10 territories, renames are rare).
