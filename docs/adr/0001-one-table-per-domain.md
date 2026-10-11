# ADR 0001: One single-table DynamoDB design per domain

Status: Accepted (2026-10-11, John)

## Context
AdventureWorks2022 has 68 business tables in 5 SQL schemas. Phase 1 split them into 7 domains (approved).
## Decision
One DynamoDB table per domain (`aw-catalog`, `aw-inventory`, `aw-sales`, `aw-customer`, `aw-purchasing`, `aw-hr`, `aw-reference`), each a single-table design with overloaded `PK/SK/GSI1/GSI2` and a `type` attribute. Cross-domain data is copied (snapshots) and refreshed by the owning domain's stream; never joined at read time.
## Consequences
+ Clear ownership, IAM and KMS boundaries per domain (HR, Customer).  + Each domain's hot paths are 1–2 requests.
− Cross-domain copies need refresh logic (CDC-03).  − 7 tables to provision/monitor (Terraform in phase 7).
Book ch. 8 "The What, Why, and When of Single-Table Design" discusses when splitting is reasonable.
