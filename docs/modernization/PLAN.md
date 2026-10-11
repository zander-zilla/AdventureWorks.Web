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

## Status

| Phase | Status | PR |
|---|---|---|
| 0 Setup | In review | #1 |
| 1 Discovery | In review (stacked on #1) | #2 |
| 2–8 | Not started | – |
