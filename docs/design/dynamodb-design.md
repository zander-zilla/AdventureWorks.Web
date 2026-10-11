# Phase 3 — DynamoDB design (cross-cutting)

Per-domain designs: [tables/](tables/) (generated). Single source mapping: [`design/mapping/mapping.yaml`](../../design/mapping/mapping.yaml)
(expanded: `mapping.json`); access pattern → operation spec: [`design/mapping/access-pattern-keys.yaml`](../../design/mapping/access-pattern-keys.yaml).
Method: [dynamodb-playbook.md](dynamodb-playbook.md). Book references are chapter numbers/titles only.

## Tables at a glance

| Domain | Table | GSIs | Entity types | Items loaded |
|---|---|---|---|---|
| Catalog | aw-catalog | 2 | 19 | see load-stats |
| Inventory & Manufacturing | aw-inventory | 2 | 8 | |
| Sales | aw-sales | 2 | 12 (+ counter) | |
| Customer & Party | aw-customer | 2 | 17 | |
| Purchasing | aw-purchasing | 2 | 7 | |
| HR | aw-hr | 2 | 6 | |
| Reference | aw-reference | 1 | 9 | |

Totals: 7 tables, 13 GSIs. Exact item counts per table/entity: [`load-stats.json`](load-stats.json).

## Table-level choices (all tables)
- **Billing:** on-demand (PAY_PER_REQUEST) — spiky demo traffic, ~1 order/s peak (D1); no capacity planning. *(Operations supp. ch. 4)*
- **PITR:** enabled; on-demand backup before every migration step. *(Operations supp. ch. 5)*
- **Streams:** `NEW_AND_OLD_IMAGES` — needed by cross-domain refresh (CDC-03: old image tells which copies to fix) and by aggregate maintenance (stock_qty, sales YTD). DynamoDB zero-ETL to Redshift does not use the stream but requires PITR.
- **TTL attribute:** `ttl` (epoch seconds). Used for carts (7 days, D3) and later for tombstones (D10).
- **Encryption:** AWS-owned key by default; customer-managed KMS keys for `aw-customer` and `aw-hr` (PII, pay, national id).
- **Deletion protection** on; **GSI projection ALL** (items are small; keeps the zero-ETL/debug story simple). Revisit KEYS_ONLY/INCLUDE for GSI2 on `aw-customer` if cost matters.
- **Generic key names** `PK`, `SK`, `GSI1PK/SK`, `GSI2PK/SK` (overloaded) + `type` on every item. *(Book ch. 9 "From modeling to implementation")*

## Attribute conventions
- Business attributes: snake_case of the SQL column (`SalesOrderID` → `sales_order_id`). Redshift identifiers are case-insensitive by default, so snake_case avoids needing `enable_case_sensitive_identifier` when navigating SUPER values.
- Meta: `type`, `ver` (optimistic concurrency), `src` (`sql`|`ddb`), `src_table`, `src_pk` (`Col=val,...`), `src_lsn`, `updated_at`, `deleted` + `deleted_at` (tombstones), `ttl`, `derived` (lookup/marker items).
- Keys: uppercase entity prefix + `#` + zero-padded ids (ids padded to their max width: orders 10 digits, products 6, ...) and ISO-8601 timestamps so string sort = numeric/time sort. *(Book ch. 14 "Strategies for sorting")*
- Snapshot attributes (copies) are listed per source in mapping.yaml `snapshots` with the owner responsible for refresh.

## Relationship strategies used
| Strategy | Where | Book |
|---|---|---|
| Item collection (same PK) | order + lines + reasons; product + photos/reviews/prices/offers; party + emails/phones/addresses/cards; employee + history | ch. 11.3 |
| Inverted / secondary index | customer → orders (GSI1), model → products (GSI2), vendor ↔ product (GSI1), component → assemblies (GSI1) | ch. 11.4, 12.2 |
| Composite / hierarchical sort keys | CATALOG category→subcategory, org path, TXN#date#id, FX date | ch. 11.5, 13.3 |
| Denormalized copies (snapshots) | order line product, order addresses/customer/card, offer on product, stock_qty | ch. 11.2, 12.1 |
| Sparse indexes / sparse marker items | REORDER, ORDERSTATUS 1–3, current department, POSTATUS items | ch. 13.4 |
| Uniqueness markers in transactions | EMAIL#, PRODUCTNAMES/<name>, PRODUCTNUMBER# | ch. 16.1 |
| Counter for sequential ids | aw-sales COUNTER/ORDER | ch. 16.2 |

## ID strategy for DynamoDB-created orders (D5)
- SQL-origin orders keep `SalesOrderID` (≤ 75,123 today; SQL identity continues upwards) and `SalesOrderNumber` `SO<id>`.
- DynamoDB-native orders: `UpdateItem aw-sales COUNTER/ORDER ADD next_id 1` → ids from **1,000,000,000** up; order number **`SO-DDB-<id>`**; `src = "ddb"`.
  The ranges cannot collide while SQL stays below 10^9 (it would need ~13,000 years at the historical rate). Keys pad to 10 digits, so both sort together.
- Lines: `LINE#<n>` with n = 1..N within the order (SQL lines keep `SalesOrderDetailID`, 7 digits; native lines use their own sequence within the order partition).
- The counter partition is a single hot item: at ~1 order/s that is far below the per-partition limit (1,000 WCU/s). For higher rates, hand out id blocks (ADD 100) per app instance.

## Zero-ETL / Redshift considerations
- DynamoDB zero-ETL lands each table in Redshift with the key attributes as columns and the whole item as a **SUPER** column. Phase 6 builds one view per `(table, type)`, e.g. `sales_order AS SELECT value.sales_order_id::int, ... FROM aw_sales WHERE value.type = 'Order' AND value.deleted IS NULL`.
- Everything analytics needs is a plain business attribute — never only inside `PK`/`SK` (keys are formatting, not data).
- Tombstones (D10) keep keys + `deleted=true` so Redshift sees deletes; derived items (`derived=true`) are excluded from views.
- Facts need on order/line items: online_order_flag, customer_id, sales_person_id, territory_id, currency_rate_id, special_offer_id, dates, and product standard cost at the order date (from CostHistory items) — all present.
- Native orders have `src='ddb'`; FactInternetSales/FactResellerSales views union both sources.

## Hot-partition review
| Partition | Why it's hot | Risk at demo scale | Mitigation |
|---|---|---|---|
| aw-sales `COUNTER/ORDER` | every native order | low (≤ 1 w/s) | id blocks if needed |
| aw-catalog `PRODUCTNAMES`, `CATALOG` | every browse/search | reads only, ≤ a few hundred rps; 3,000 RCU/partition | in-app cache (data changes rarely); DAX if needed |
| aw-catalog GSI1 `SUBCAT#…` | category pages | read-only, spread over 37 subcategories | cache |
| aw-customer GSI2 `CUSTOMERS` | admin list | low traffic | fine; Redshift for analytics |
| aw-hr GSI2 `ORG` | org chart | 290 items, low traffic | fine |
| aw-inventory `PRODUCT#<p>` | stock movements of best sellers | writes ~370/day total | fine |
| aw-sales GSI1 `CUSTOMER#<c>` for big resellers | reseller order history | ≤ 28 orders/customer | fine |
| aw-reference lists | every checkout | read-mostly | cache |
| aw-sales GSI2 `ORDERSTATUS#1` | all new orders until shipped | ~1 w/s at demo peak | fine; shard by day if > 1,000 w/s |
| aw-inventory GSI2 `WODUE#<month>` | WO creation | ~66/day | fine |

## CDC transform contract (input for phase 4)
- `scripts/loader/awmap.py` is the reference transform: `items_for_row()` for inserts/updates, `tombstones_for_row()` for deletes. The Lambda / Debezium consumer uses the same mapping and code path.
- Writes are `PutItem` with `ConditionExpression attribute_not_exists(PK) OR src_lsn < :lsn` (idempotent, ordered by LSN).
- Enrichment: `source_sql` joins become lookups against the domain tables during CDC (e.g. order line → product name from aw-catalog). Immutable snapshots are taken at insert time only.
- Key changes (e.g. a customer's PersonID changes, an order's status leaves 1–3) are handled because the before-image produces the old keys → tombstone/delete old item, put new.

## Validation
- `scripts/loader/load.py` loads all 68 source tables from AdventureWorks2022 into DynamoDB Local using the mapping.
- `tests/access_patterns/test_patterns.py` executes every DynamoDB-served access pattern (60) and checks results against equivalent SQL; a meta-test fails if any Phase-2 `dynamodb` pattern lacks a key spec or a test.
- CI job `dynamodb-design` runs both against SQL Server + DynamoDB Local.
