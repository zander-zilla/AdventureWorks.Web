# ADR 0002: Generic overloaded keys, snake_case attributes, CDC meta attributes

Status: Accepted

## Decision
- Keys `PK`, `SK`, `GSI1PK/SK`, `GSI2PK/SK` (at most 2 GSIs per table); key values are formatted strings (`ORDER#0000043659`).
- Business attributes in snake_case derived mechanically from SQL column names; meta attributes `type, ver, src, src_table, src_pk, src_lsn, updated_at, deleted, deleted_at, ttl, derived`.
- Prefer derived marker items (uniqueness, lookups, sparse lists) over additional GSIs when the pattern is low-volume.
## Why
Mechanical naming lets one mapping file drive the loader, the CDC Lambda, docs and the showcase; snake_case is friendly to Redshift SUPER navigation; `src_*` makes every item addressable from its SQL row for idempotent CDC.
Book ch. 9 (separate indexing from application attributes; add a type attribute).
