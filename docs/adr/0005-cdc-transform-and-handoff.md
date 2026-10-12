# ADR 0005: One CDC transform for bulk load, Debezium and DMS; position-ordered conditional writes

Status: Proposed (Phase 4)

## Decision
- A single Python library (`cdc/awcdc`) applies changes, reusing the Phase 3 `awmap` code and `mapping.json`. Debezium
  (local) and DMS→Kinesis→Lambda (AWS) are only transports.
- Rows are re-read by primary key through the mapping's `source_sql` (the bulk-load query), so CDC and bulk load produce
  identical items. Deletes evaluate `source_sql` against the before-image.
- Ordering: every item carries `src_lsn`; writes are `PutItem` conditional on `src_lsn < position`. Snapshot refreshes are
  in-place `UpdateItem`s that do not move `src_lsn`.
- Handoff: capture starts before the bulk load; the consumer buffers until the load is done, then applies (no gaps; duplicates are no-ops).
- Deletes → tombstones with `ttl` = capture + 7 days (P3-4).

## Consequences
+ One code path to test; identity is tested per table.  + At-least-once transports are safe.
− The transform needs read access to SQL (RDS read replica on AWS) for enrichment.
− Re-reading gives the row's current state rather than the state at that LSN; ordering by position still converges to the latest state.
− Refresh fan-out (e.g. a category rename updates ~100 products) runs inline in the transform; at demo volume that is fine.
