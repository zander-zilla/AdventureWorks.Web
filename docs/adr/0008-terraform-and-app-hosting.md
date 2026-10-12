# ADR 0008: One Terraform root for the whole AWS deployment; .NET 10 app on ECS Fargate behind an ALB; OIDC-only CI/CD

Status: Proposed (Phase 7) — code only, nothing applied (no AWS calls were made). Runbook: docs/aws-setup.md.

## Context
Phase 7 must describe every AWS resource of the demo (VPC, RDS SQL Server source with CDC, DMS, Kinesis, the CDC Lambda,
the seven DynamoDB domain tables, Redshift Serverless + zero-ETL, optional QuickSight, hosting for the .NET 10 app), support
more than one environment, keep no long-lived secrets in GitHub, and be cheap to stand up for a demo and tear down after.

## Decision
1. **Layout**: `infra/bootstrap` (once per account, local state: S3 state bucket + GitHub OIDC provider + `aw-github-deploy`
   / `aw-github-plan` roles), `infra/live` (one root, S3 backend with S3-native lock files, partial backend config per
   environment) composed of modules `network`, `dynamodb`, `source_db`, `cdc`, `app`, `warehouse` (the Phase 6 stack, moved
   from `aws/warehouse/terraform`). Environments = `infra/envs/<env>.tfvars` + `<env>.s3.tfbackend`; one environment per
   account/region because the table names (`aw-*`) are fixed by the mapping, the loader and the CDC transform.
2. **App hosting: ECS Fargate + ALB** for the .NET 10 app (and, optionally, the original app for the live CDC demo).
   - *App Runner* was the simplest fit but stopped accepting new customers on 2026-04-30 (maintenance mode) — not a
     sound choice for a new deployment.
   - *ECS Express Mode* (App Runner's recommended successor) is attractive but new; plain Fargate + ALB is fully expressed
     in the Terraform AWS provider and gives the same runtime. Revisit Express Mode for Phase 8 if it simplifies the showcase.
   - *Lambda (ASP.NET Core hosting)*: cold starts and a different hosting model than local/CI; *Elastic Beanstalk*: more
     moving parts, no benefit; *EKS*: control-plane cost and complexity unjustified for two containers.
   - The same chiseled non-root image that CI tests (`docker/after/Dockerfile`) runs unchanged; the task role grants only
     the three tables the app uses (ADR 0006).
3. **No NAT gateway**: Fargate tasks run in public subnets with public IPs (security group admits only the ALB); RDS, DMS
   and Redshift sit in private subnets; DMS reaches Kinesis through an interface endpoint; S3/DynamoDB gateway endpoints.
   The CDC Lambda is not in the VPC (it never reads SQL Server, ADR 0005).
4. **Source DB**: RDS for SQL Server 2022 **Standard Edition** (license included; Express/Web cannot run CDC on RDS),
   single-AZ. Restore + CDC enablement (`rds_restore_database`, `rds_cdc_enable_db`, `sp_cdc_enable_table` × 68, 7-day
   retention) are done by a one-off **ECS tools task** (`scripts/aws/db_init.py`) instead of a Terraform `null_resource`
   with `sqlcmd`: the database is private, so the job must run inside the VPC, and keeping it out of `apply` keeps
   Terraform declarative and re-runnable.
5. **CDC handoff**: the DMS task is created stopped; `db-init` prints the UTC time captured before the bulk load and
   `scripts/aws/start-cdc.sh` starts the task from that time (`--cdc-start-time`). Conditional writes on the source position
   make the overlap with the bulk load harmless (ADR 0003/0005).
6. **CI/CD**: `infra` workflow on every push/PR — `terraform fmt -check`, `validate` (bootstrap + live), **offline plan
   tests** (`terraform test` with mock providers: W-1 keys per table, toggles, 7 integrations), Lambda package build, tools
   image build; a real `terraform plan` job runs only when the read-only OIDC plan role is configured. `deploy` workflow:
   manual dispatch only, GitHub environment (`demo`/`dev`, optional required reviewers), OIDC → `aw-github-deploy`;
   plan / apply (infra + images) / app-only / destroy. No AWS access keys anywhere.
7. **Cost guardrails**: toggles `enable_source` (RDS+DMS+Kinesis+Lambda), `enable_before_app`, `enable_quicksight`,
   `app_desired_count`; Redshift usage limit; `scripts/aws/teardown.sh` (stop DMS, drop deletion protection, destroy,
   list leftovers by tag).

## Consequences
- Nothing has been applied; the items listed in docs/aws-setup.md "Verified only on AWS" need a first real apply.
- The RDS SQL Server licence dominates the hourly cost; John tears the environment down after each demo.
- The deploy role is PowerUserAccess + IAM limited to `aw-*`/DMS service roles — broad enough for the stack, not admin.
- Secrets: the RDS master password lives in Secrets Manager and in the encrypted remote state (DMS endpoint needs it).
