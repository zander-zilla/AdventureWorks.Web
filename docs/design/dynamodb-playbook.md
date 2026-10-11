# DynamoDB design playbook (AdventureWorks modernization)

Our own condensed working method for phases 2–4. Written in our words; references point to chapter numbers/titles
of *The DynamoDB Book* (Alex DeBrie) and its Analytics / Operations supplements for further reading. No text from those
books is reproduced here.

## 0. Ground rules for this project
- **One table per domain** (Catalog, Sales, Customer, Purchasing, HR, Reference). Inside a domain: single-table design with overloaded generic keys `PK`, `SK`, `GSI1PK`/`GSI1SK`, … and an `entityType` attribute on every item.
- **Access patterns drive the design, not the SQL schema.** The SQL schema (docs/discovery/schema.json) tells us what data exists; the access-pattern list (phase 2) tells us how it must be laid out.
- **Cross-domain data is copied, not joined.** A domain owns its entities; other domains keep a small, explicitly-listed snapshot (e.g. product name + price on an order line) refreshed by events.
- **Analytics leaves DynamoDB.** Reporting (DW star schema) is served by Redshift via zero-ETL; we do not add GSIs just for reports.
- Reading: Book ch. 7 *How to approach data modeling in DynamoDB*, ch. 8 *The What, Why, and When of Single-Table Design*.

## 1. Method, step by step
1. **ERD first.** Draw the entities and relationships of the domain (we generate these from SQL FKs, then prune). Mark cardinality and which side grows unbounded (customer → orders is unbounded; order → lines is bounded-ish).  *(ch. 7.2)*
2. **List access patterns** for every screen, API call, background job and CDC consumer: who asks, the inputs, expected result shape, sort order, frequency, and whether it must be strongly consistent. Writes are access patterns too (uniqueness checks, conditional updates, transactions). *(ch. 7.2)*
3. **Design the primary key** so the most important read patterns are a single `GetItem` or one `Query` over an *item collection* (all items sharing a partition key). Pre-join related entities that are read together by giving them the same `PK`. *(ch. 2 Core Concepts, ch. 3 Advanced Concepts)*
4. **Add secondary indexes** only for patterns the base table cannot serve. Prefer GSIs (flexible, add later) over LSIs (fixed at creation; size-limited item collections). Use *sparse* GSIs when only a subset of items should be indexed. Project only what the pattern needs. *(ch. 3, ch. 13.4)*
5. **Write the entity chart**: for each entity, the template of PK/SK/GSI keys. Keep **indexing attributes separate from application attributes**, put a `Type`/`entityType` on every item, and keep the key-building code at the boundary of the app (repository layer). *(ch. 9 From modeling to implementation)*
6. **Validate** each access pattern against the chart (one request ideally, two at most), check hot partitions and item-size limits (400 KB), and script sample queries. *(ch. 9.5)*

## 2. Relationship strategies (how we'll pick)
| Situation | Strategy | Book ref |
|---|---|---|
| Small, bounded child list always read with parent, never queried alone (e.g. product photo refs, order status history) | Store as a list/map attribute on the parent | ch. 11.1 |
| Child needs parent fields that rarely change (product name/category on an order line) | Duplicate the parent fields into the child; accept update fan-out | ch. 11.2 |
| Parent + many children read together, children also listed/paged (customer → orders, order → lines) | Same `PK`, different `SK` prefixes; one `Query` | ch. 11.3 |
| Second "parent" view of the same children (orders by sales person/territory) | GSI with the alternate parent as `GSI1PK` | ch. 11.4 |
| Hierarchies (country → state → city; category → subcategory → product) | Composite sort key `COUNTRY#..#STATE#..` and `begins_with` | ch. 11.5 |
| Many-to-many where one side needs only a little info (product ↔ special offer) | Shallow duplication | ch. 12.1 |
| Many-to-many queried from both sides (vendor ↔ product, store ↔ contact) | Adjacency list: edge items + inverted GSI (`GSI1PK=SK, GSI1SK=PK`) | ch. 12.2 |
| Graph-like / rarely used | Materialized graph or plain normalization with 2 requests | ch. 12.3–12.4 |

## 3. Filtering and sorting
- Filter **with keys first**: choose partition by the most selective required input; refine with sort-key conditions (`begins_with`, `between`). Composite sort keys (`STATUS#DATE`) give two-attribute filtering in one index. *(ch. 13.1–13.3)*
- **Sparse indexes** for "only items in state X" (open carts, pending purchase orders, current employees). *(ch. 13.4)*
- **Filter expressions** only trim results after the read; never rely on them for selectivity. Client-side filtering is fine for small, bounded collections. *(ch. 13.5–13.6, ch. 6.2)*
- Sort keys are compared as strings: use ISO-8601 timestamps, zero-pad numbers (`SO#00043659`), mind case, and use KSUID/ULID-style ids when we need time ordering plus uniqueness. Sorting on attributes that change (order status) means rewriting the key (delete+put) or using a GSI. *(ch. 14 Strategies for sorting)*

## 4. Writes, uniqueness, counters
- Uniqueness on multiple attributes (customer email *and* account number) = transaction with marker items and `attribute_not_exists` conditions. *(ch. 16.1)*
- Sequential ids (SalesOrderNumber): counter item with atomic `ADD`, or keep SQL-assigned ids while SQL remains the system of record during CDC. *(ch. 16.2)*
- Pagination via `LastEvaluatedKey`; aggregate counts kept in a singleton/parent item updated in the same transaction. *(ch. 16.3–16.5)*
- Use condition expressions for optimistic concurrency (`version` attribute) – replaces SQL rowversion/ModifiedDate checks. *(ch. 6.4)*

## 5. Migrations and evolving designs
Classify each change before doing it *(ch. 15 Strategies for Migrations; worked example ch. 22)*:
- **Additive, no new access pattern** (new attribute): lazy – write new shape, read old shape tolerantly.
- **New entity in its own item collection**: just start writing it.
- **New entity into an existing collection / new pattern over existing items**: backfill with a (parallel) Scan + update job that adds new key attributes; GSIs then populate automatically.
For this project the initial load is itself a migration: bulk load from SQL (DMS full load) then CDC; transforms must be **idempotent** and keyed on source PKs so replays are safe.

## 6. Analytics / zero-ETL considerations
- OLTP tables stay access-pattern shaped; analytics is done elsewhere. *(Analytics supplement ch. 1)*
- Small, known aggregates the app shows (customer lifetime spend, product sold count) → **pre-aggregate** via Streams/Lambda or in the write transaction. *(Analytics supp. ch. 2)*
- Everything else → **Redshift**: DynamoDB zero-ETL integration lands items as SUPER; we unnest by `entityType` into staging views, then build the DW star schema (phase 6). Overloaded keys therefore need a stable `entityType` and plain-named application attributes (don't hide data only inside `PK`/`SK`). *(Analytics supp. ch. 3 Copying your table to Redshift)*
- Ad-hoc / export → S3 export + Athena/Glue. Real-time → Streams. *(Analytics supp. ch. 4–5)*

## 7. Operations
- Least-privilege IAM per domain table (app role reads only what it needs; condition keys for leading keys where useful). *(Operations supp. ch. 2)*
- Terraform for tables/GSIs/zero-ETL (phase 7). *(Operations supp. ch. 3)*
- On-demand billing for the demo; PITR on; on-demand backups before migrations. *(Operations supp. ch. 4–5)*

## 8. Checklist per domain (phase 3 deliverable)
ERD · access-pattern table · entity chart (PK/SK/GSIs) · per-pattern query spec · cross-domain copies & their refresh events · CDC transform notes · zero-ETL/Redshift view notes.
