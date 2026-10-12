# AdventureWorks AWS Modernization – Plan

Goal: take the full AdventureWorks OLTP database and the archived AdventureWorks.Web app from SQL Server to
domain-based DynamoDB single-table designs (one table per domain), move reporting to Amazon Redshift via
zero-ETL (rebuilding the AdventureWorksDW star schema), and show it live: a test customer acts in the
*before* app, CDC replicates to DynamoDB (DMS → Kinesis → Lambda on AWS; Debezium locally).

## Phases

| # | Phase | Outcome |
|---|---|---|
| 0 | Setup | Fork, before stack (SQL Server 2022 + Agent, AW OLTP/DW/LT restored, CDC on), original app building, demo login, CI, this plan |
| 1 | Discovery | Generated schema inventory (OLTP + DW), domain split, DW lineage, DynamoDB design playbook, seed access patterns |
| 2 | Access patterns | John-refined access-pattern list per domain with frequency/latency/consistency needs |
| 3 | DynamoDB design | Per-domain single-table designs: entity charts, PK/SK, GSIs, item collections, cross-domain duplication |
| 4 | Migration / CDC | Bulk load + CDC: DMS → Kinesis → Lambda (AWS), Debezium (local); idempotent transforms, replay/backfill |
| 5 | App modernization | App on .NET 10 reading the full-domain DynamoDB tables + shopper pages (no separate LT table) |
| 6 | Analytics | DynamoDB zero-ETL → Redshift, rebuild DW star schema (facts/dims), QuickSight dashboards |
| 7 | IaC / CI | Terraform for all AWS resources, GitHub Actions pipelines |
| 8 | Showcase website | Tabs: Presentation / Architecture / Data Mapping / Access Patterns / Live App — all driven by one mapping file |

## Ground rules
- No pushes to Azure-Samples/Microsoft repos; PRs are opened on this fork and merged by John only.
- Private reference books are never quoted or committed; designs cite chapter titles/numbers only.
- Every phase lands as a PR with docs updated.

## Decisions log
| Date | Decision |
|---|---|
| 2026-10-11 | (1) Demo login, shop catalog, order writes and My orders use the full AdventureWorks2022 DB (not LT). Original LT CRUD screens unchanged until phase 5. |
| 2026-10-11 | (2) The 7 domains are approved: Catalog, Inventory & Manufacturing, Sales, Customer & Party, Purchasing, HR, Reference (docs/discovery/domains.md). |
| 2026-10-11 | (3) DW finance / call-center / survey (and other no-OLTP-source) tables carry over to Redshift as **static data** (docs/discovery/dw-lineage.md). |
| 2026-10-11 | Phase 2 decisions D1–D10 (docs/design/access-patterns.md): name-prefix search, logged-in carts with 7-day TTL, .NET 10 app writes DynamoDB directly (old app → SQL → CDC), native order ids above SQL's with prefix, all 7 domains incl. back office, territory/sales-person lists in Redshift, strong reads only for login/cart/read-after-checkout, 6 cultures, tombstones for deletes. |
| 2026-10-11 | (4) CDC on all 68 AdventureWorks2022 business tables; dbo housekeeping (AWBuildVersion, DatabaseLog, ErrorLog) excluded. |
| 2026-10-11 | Phase 4 (P4-1..5, ADR 0005 accepted): (1) AWS Lambda builds items from DMS full row images + DynamoDB lookups; SQL re-read only for 15 join tables (configurable, `cdc-enrichment.yaml`); (2) copy refreshes run inside the CDC transform; (3) refreshes REMOVE copies whose source became NULL; (4) CDC retention 7 days (RDS `sp_cdc_change_job @retention=10080`); (5) ADR 0005 accepted. |
| 2026-10-11 | CDC enrichment without SQL (John; ADR 0005 amended): the 15 join tables are built from the event image + lookups of the already-replicated related items in DynamoDB (+ re-implemented computed columns, hierarchyid/geography); snapshot refreshes find dependents in DynamoDB; a missing referenced item is retried with backoff (4 attempts, 0.1/0.2/0.4 s) and then fails the event to the batch retry / DLQ. SQL read dependency and the RDS read-replica recommendation removed. |

| 2026-10-12 | Phase 6 (ADR 0007): one zero-ETL integration per domain table; typed staging MVs generated from mapping.json; star schema rebuilt hourly by one portable stored procedure; static DW tables via S3 → COPY. Open for John: W-1 KMS (AWS-managed keys unsupported by zero-ETL → AWS-owned/CMK), R-1 reseller tax/freight allocation, W-2 schedule, W-3 inventory grain, W-4 QuickSight subscription. |
| 2026-10-12 | Phase 6 decisions accepted (John; ADR 0007 → Accepted): **W-1** AWS-owned keys on catalog/inventory/sales/purchasing/reference, CMKs kept on aw-hr/aw-customer with a key-policy grant for Redshift zero-ETL (ADR 0004 P3-2 amended, mapping.yaml, Terraform); **R-1** real order-total reseller tax/freight; **W-2** hourly rebuild; **W-3** inventory grain as built; **W-4** QuickSight Enterprise only for the showcase (`enable_quicksight` toggle). |
| 2026-10-12 | Phase 7 (proposed, ADR 0008): one Terraform root `infra/live` (modules network/dynamodb/source_db/cdc/app/warehouse) + `infra/bootstrap` (state bucket, GitHub OIDC roles); app on ECS Fargate + ALB; RDS SQL Server SE; db-init/bulk-load as ECS tools tasks; OIDC-only manual deploy workflow; teardown script. Runbook docs/aws-setup.md. |
| 2026-10-12 | Phase 7 decisions accepted (John; ADR 0008 → Accepted): (1) ECS Fargate + ALB; (2) RDS SQL Server SE db.m6i.large, torn down after demos; (3) deploy role as-is, tighten after first apply; (4) DB password in encrypted state; (5) AWS Budgets alert USD 50/month (`budget_alert_emails`, `infra/live/budget.tf`) + required reviewer on the GitHub `demo` environment. |

## Status

| Phase | Status | PR |
|---|---|---|
| 0 Setup | In review | #1 |
| 1 Discovery | In review (stacked on #1): inventory, domain split, DW lineage, playbook, seed access patterns — see docs/discovery | #2 |
| 2 Access patterns | Approved (D1–D10), in review (stacked on #2): docs/design/access-patterns.md/.json | #3 |
| 3 DynamoDB design | In review (against master; carries D1-D10; decisions P3-1..5 recorded in ADR 0004) | #4 |
| 4 Migration / CDC | Approved; #5 (transform, Debezium local, DMS/Kinesis/Lambda, monitor, e2e + reconcile); follow-ups P4-1..4 in #6 | #5, #6 |
| 5 App modernization | Merged (.NET 10 app on DynamoDB, ADR 0006); CDC enrichment from DynamoDB lookups merged | #7, #8 |
| 6 Analytics | Merged; decisions W-1..W-4, R-1 accepted (ADR 0007): zero-ETL (7 integrations) → Redshift Serverless, stg MVs generated from the mapping, `dw.sp_build_star()` (12 dims + 6 facts), static carry-over, QuickSight; local Postgres verification + reconciliation vs AdventureWorksDW2022 in CI (`warehouse` workflow); ADR 0007, docs/design/warehouse.md | #9 |
| 7 IaC / CI | Merged; decisions accepted (ADR 0008): Terraform for the whole deployment (`infra/`), offline plan tests, `infra` CI + manual OIDC `deploy` workflow, teardown, runbook docs/aws-setup.md, ADR 0008. Nothing applied | #10, #11 |
| 8 | Not started | – |
