# infra — Terraform for the whole AWS deployment (Phase 7)
- `bootstrap/` — once per account (local state): remote-state bucket, GitHub OIDC provider, deploy/plan roles.
- `live/` — the stack root (S3 backend): `network`, `dynamodb`, `source_db`, `cdc`, `app`, `warehouse` modules. Offline plan tests in `live/tests`.
- `envs/` — `<env>.tfvars` + `<env>.s3.tfbackend` (demo = full CDC story, dev = DynamoDB + app + warehouse only).
- Runbook: [docs/aws-setup.md](../docs/aws-setup.md). Decisions: ADR 0008 (and 0007 for the warehouse).
Nothing here has been applied from this repository's CI; `terraform test` uses mock providers (no credentials).
