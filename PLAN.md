# AdventureWorks modernization – plan overview

The project runs in two chapters on the same repo (`zander-zilla/AdventureWorks.Web`, `master`).

| Chapter | Name | Phases | Status | Plan |
|---|---|---|---|---|
| 1 | Migration | 0-8: SQL Server → DynamoDB (7 domain tables), CDC, .NET 10 app, zero-ETL → Redshift, Terraform, showcase | **Done**, tag `v1.0-migration` (`45b8584`, GitHub release) | [docs/modernization/PLAN.md](docs/modernization/PLAN.md) |
| 2 | Extend and modernize | C2-0..C2-5: design system (React + Tailwind), redesigned showcase with chapter switch, order fulfilment + pricing + reviews, procurement, production floor, optional Bedrock AI | **Proposed**, awaiting John's sign-off | [docs/chapter-2/PLAN.md](docs/chapter-2/PLAN.md) |

Chapter 2 is grounded in the business-process analysis in [docs/business-processes/](docs/business-processes/README.md).

## Ground rules (both chapters)
- PRs on this fork only (`gh pr create -R zander-zilla/AdventureWorks.Web --base master`); John merges. The upstream is archived.
- Every phase lands as a PR with docs updated and CI green.
- Chapter 1 stays reproducible: the showcase's Chapter 1 view is built from the `v1.0-migration` tag.

## Decisions log
| Date | Decision |
|---|---|
| 2026-10-12 | Chapter 2 continues in the same repo on `master` (John). |
