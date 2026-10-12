# ADR 0007: DynamoDB zero-ETL to Redshift Serverless; star schema built by one portable stored procedure

Status: Proposed (Phase 6) — reflects the as-built, locally verified design. Details: docs/design/warehouse.md.

## Context
Phase 6 must rebuild the AdventureWorksDW star schema from the replicated DynamoDB domain tables, keep the no-source DW
tables as static data (decision 3), feed QuickSight, prefer AWS-native services and be verifiable in CI without AWS.

## Decision
1. **Ingestion**: one DynamoDB zero-ETL integration per domain table into a Redshift Serverless namespace (8–32 RPU, usage
   limit). Each integration lands in its own database `aw_zetl_<domain>` as `("PK", "SK", value SUPER)`. No Glue, no DMS, no Lambda.
2. **Staging**: one materialized view per DynamoDB entity type (`stg.*`, 76), `AUTO REFRESH YES`, generated from
   `design/mapping/mapping.json` by `warehouse/gen_staging.py`: SUPER → typed columns, `type` filter, tombstones excluded, `xml_map`
   demographics flattened. The mapping stays the single source.
3. **Star build**: `dw.sp_build_star()` — dims then facts, DELETE + INSERT in one transaction — run hourly by EventBridge
   Scheduler through the Redshift Data API. Physical design (DISTKEY/SORTKEY) is a separate Redshift-only file.
4. **Portability**: everything above staging is a linted portable SQL subset; the procedure is valid PL/pgSQL on Redshift and
   Postgres. CI loads DynamoDB Local exports into Postgres in the landing shape, runs the same procedure and reconciles against
   AdventureWorksDW2022 (gated).
5. **Static data**: `static_export.py` exports the 10 static DW tables + 5 localised-name lookups to CSV → S3 → `COPY` into `dw_static`.
6. **Keys**: DW surrogate keys kept where they equal an OLTP id (CustomerID — required by FactSurveyResponse —, SpecialOfferID,
   TerritoryID, category/subcategory/reason); the others are deterministic `ROW_NUMBER()`s. Facts match the DW by order number + line.
7. **BI**: QuickSight Redshift data source + SPICE data set over `dw.v_sales` (Terraform) and a dashboard definition (`dashboard.json`, CreateDashboard API).

## Consequences
- Source tables need PITR (already on) and an **AWS-owned or customer-managed** KMS key: zero-ETL does not accept AWS-managed
  keys, so ADR 0004 P3-2 needs an amendment (decision W-1).
- Freshness = zero-ETL lag (15–30 min) + schedule (1 h). Full rebuild each run: fine at AdventureWorks scale (≈4 s locally);
  revisit with incremental MERGE if facts grow by orders of magnitude.
- Any DynamoDB attribute over 64 KB fails a table's replication: CI pre-flights item sizes; `aw_zetl_catalog` uses TRUNCATECOLUMNS.
- SUPER casts, cross-database MVs and the Terraform can only be proven on AWS (listed in warehouse.md).

## Alternatives considered
- *Glue/Spark ETL or DMS to Redshift*: more moving parts, no benefit over zero-ETL for a read-only copy.
- *Star tables as materialized views*: SCD2 windowing and multi-step dependencies prevent incremental refresh; a procedure is clearer.
- *Plain late-binding staging views*: re-parses SUPER per query; MVs are cheaper and refresh incrementally.
- *Redshift-only SQL verified only on AWS*: no CI coverage; rejected in favour of the portable layer.
