# ADR 0005: One CDC transform for bulk load, Debezium and DMS; position-ordered conditional writes

Status: Accepted (2026-10-11, John; amended by Phase 4 follow-ups)

## Decision
- A single Python library (`cdc/awcdc`) applies changes, reusing the Phase 3 `awmap` code and `mapping.json`. Debezium
  (local) and DMS→Kinesis→Lambda (AWS) are only transports.
- Rows are built per `design/mapping/cdc-enrichment.yaml`: from the event's full row image (default), image + DynamoDB
  GetItem lookups for copied parent attributes + re-implemented computed columns (15 tables), or a SQL re-read through the
  mapping's `source_sql` for the 15 tables that need real joins. Identity with the bulk load is tested per table, with and
  without SQL access. Snapshot refreshes still query SQL for the dependent rows.
- Ordering: every item carries `src_lsn`; writes are `PutItem` conditional on `src_lsn < position`. Snapshot refreshes are
  in-place `UpdateItem`s that do not move `src_lsn`.
- Handoff: capture starts before the bulk load; the consumer buffers until the load is done, then applies (no gaps; duplicates are no-ops).
- Deletes → tombstones with `ttl` = capture + 7 days (P3-4).

## Consequences
+ One code path to test; identity is tested per table.  + At-least-once transports are safe.
− SQL read access (RDS read replica) is still needed for 15 join tables and for snapshot refreshes; `CDC_SQL_ENABLED=false` runs without it (those events go to the DLQ).
− Re-reading gives the row's current state rather than the state at that LSN; ordering by position still converges to the latest state.
− Refresh fan-out (e.g. a category rename updates ~100 products) runs inline in the transform; at demo volume that is fine.
