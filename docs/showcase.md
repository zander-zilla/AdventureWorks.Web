# Showcase website (Phase 8)

An eight-tab site that tells the modernization story to managers, directors and prospective customers. It's static, and
everything on it is generated from the repo's sources of truth. ADR 0009 covers the decisions.

| Tab | What it shows | Data / reuse |
|---|---|---|
| Presentation | 6 slides (challenge → approach → migration → app → analytics → operations) with live KPIs; ←/→ keys | `results.json`, `load-stats.json`, mapping/access-pattern counts |
| Before Architecture | Original: ASP.NET Core 2.1 MVC + EF Core 2.1, SQL Server 2022 AdventureWorks2022 OLTP, batch ETL → AdventureWorksDW; click any component for details | component list in `showcase/site/app.js` |
| After Architecture | .NET 10 on Fargate + ALB, 7 DynamoDB domain tables, RDS → DMS → Kinesis → Lambda CDC, zero-ETL → Redshift star schema, QuickSight, S3 + CloudFront showcase, GitHub Actions OIDC CI/CD; click for details | same |
| Data Mapping | **SQL → DynamoDB**: pick any of the 68 tables (filterable, grouped by target table) → item entity, PK/SK/GSI key templates, denormalised copies, column → attribute/transform. **DynamoDB → Redshift**: every dim/fact (+ static carry-over) → source items → `stg` MVs → `dw.*` | `design/mapping/mapping.json` (`sources`, `dw_lineage`) |
| Access Patterns | All 70 patterns, filter by domain/scope/text; DynamoDB key conditions per pattern | `docs/design/access-patterns.json` + `mapping.json` `access_patterns` |
| Live Replication | The Phase 4 replication monitor, embedded; *Side by side with the Before App* puts the original app next to it, so an order placed in SQL Server can be watched arriving in DynamoDB. Recorded replay by default, live with `--live` | `cdc/monitor/index.html`, `showcase/fixtures/replication-replay` |
| Before App | The original app on SQL Server (`:8080` on AWS, `:5080` locally) in a frame, with the 5 test logins (password `Demo!2026`) and a guided write | `config.json` `beforeUrl` (Terraform `before_url`) |
| After App | The .NET 10 DynamoDB shopper app in a frame plus an *Open in new tab* link | `config.json` `appUrl` (Terraform `after_url`) |

## Run locally
```bash
scripts/showcase-up.sh                                # http://localhost:8088, replay, no app
scripts/after-up.sh && scripts/showcase-up.sh --app-url http://localhost:5090   # embed the local app
scripts/before-up.sh && scripts/showcase-up.sh --before-url http://localhost:5080  # embed the original app
scripts/cdc-up.sh   && scripts/showcase-up.sh --before-url http://localhost:5080 --live  # full live demo: write in Before App → Live Replication
```
Tests: `python -m pytest tests/showcase` (every tab with stub apps; CI also runs it with the real .NET 10 app in `after`, and **live** in `before-stack`'s CDC job: it logs in to the Before App frame, places an order, and asserts that the monitor shows it applied to DynamoDB, `SHOWCASE_LIVE=1`) (`SHOWCASE_SCREENSHOTS=dir` saves one screenshot per tab; `SHOWCASE_APP_URL` embeds a real app).

## On AWS
`infra/modules/showcase` (private S3 bucket, CloudFront OAC, HTTPS, AWS managed security-headers policy, no caching
for `config.json`/`data/*`/`api/*`), on by default (`enable_showcase`). `scripts/aws/push-showcase.sh <env>` builds with
the `after_url` output and syncs + invalidates. The deploy workflow runs it on `apply` and `app-only`. Output: `showcase_url`.
The app's task gets `Showcase__FrameAncestors = <CloudFront origin>`. Teardown removes the site too (`force_destroy`).

**Live Replication on AWS (S-2).** With `enable_source` (the CDC path) and `enable_monitor_api` (default true), the CDC
Lambda also records every applied change in `aw-<env>-cdc-monitor` (DynamoDB, on-demand, 24 h TTL;
`cdc/lambda/monitor_feed.py`, best effort, never fails a batch). A small Lambda, `aw-<env>-monitor-api`
(`cdc/monitor_api/handler.py`, Function URL with `AWS_IAM` auth, reserved concurrency 5), serves the **Phase 4 monitor
contract unchanged** (`/api/status`, `/api/changes?limit=&table=`, same keys as `cdc/consumer/consumer.py`). CloudFront
routes `/api/*` to an **origin group**: the Function URL first (Lambda origin access control, so only this distribution can
call it), the S3 replay second. Any 403/404/5xx (stack paused or torn down, CDC not started yet and nothing recorded,
throttling) makes CloudFront answer from the recorded sample, and the monitor's *State* shows *recorded replay*.
`push-showcase.sh` builds with `--monitor-mode aws` when output `showcase_monitor_api` is true. Tests:
`tests/cdc/test_monitor_api.py` (contract keys vs. the replay fixture, 503 fallback, filter/limits, feed never fails the
batch) and the Terraform runs `monitor_api_*` / `showcase_api_failover_to_replay`.

**HTTPS and the embedded apps (S-3).** Set `domain_name` (Terraform requests a DNS-validated ACM certificate; with
`route53_zone_id` it also creates the validation record and an alias to the ALB) or bring `certificate_arn`. Then both
ALB listeners are HTTPS (After App on 443, Before App on 8080, HTTP 80 redirects), `after_url`/`before_url` are `https://`,
and the HTTPS showcase can frame both apps (no mixed content). **Logged-in demos: use *Open in a new tab*.** The site
(CloudFront domain) and the apps (ALB domain) are different sites, so the apps' `SameSite=Lax` auth cookie is not sent
inside the frame; browsing works embedded, logging in and ordering do not. Without a certificate the tabs show a link.

## Changes from initial design
- PLAN.md had five tabs (Presentation / Architecture / Data Mapping / Access Patterns / Live App). As built there are **eight**
  (John): Presentation, Before Architecture, After Architecture, Data Mapping, Access Patterns, Live Replication, Before App,
  After App. Architecture is split into before/after tabs, and there's one tab per app plus a side-by-side Before App + monitor view.
- The Phase 4 monitor comment said it would be embedded in the *Data Mapping* tab. It lives on the *Live Replication* tab
  instead, unchanged except that it shows `recorded replay` when the API says so.
- ADR 0008 suggested revisiting ECS Express Mode for Phase 8. That isn't needed: the site is static on S3 + CloudFront, and the app stays on
  Fargate + ALB.
- On AWS there's no hosted CDC consumer (AWS CDC is DMS → Kinesis → Lambda). Phase 8 shipped the hosted tab as replay
  only; Phase 8b (S-2) adds the monitor API Lambda. The S-2 recommendation said it would read the CDC Lambda's CloudWatch
  logs; as built the CDC Lambda writes a small `cdc-monitor` table instead. Logs Insights queries are slow (seconds) and
  paid per GB scanned on every 2 s poll, while a TTL'd DynamoDB table answers in milliseconds for cents.
- Fallback is done by CloudFront (origin group) instead of the page: the monitor page stays unchanged, and the same
  replay files serve local static mode, a torn-down stack and errors.
- S-3: the ALB's Before App listener (8080) becomes HTTPS too (initially only 443 was), and `domain_name`/`route53_zone_id`
  were added next to `certificate_arn`.
- New setting `Showcase:FrameAncestors` (CSP `frame-ancestors`) in **both** apps (before: Startup.cs; after: Program.cs), off unless
  configured; set by Terraform (CloudFront origin) and the local compose files (`localhost:*`).

## Decisions (John, 2026-10-12; ADR 0009 Accepted)
- **S-1** keep the showcase public. **S-2** monitor API Lambda behind CloudFront, falling back to the recorded sample (Phase 8b).
  **S-3** ACM / HTTPS on the ALB (`domain_name` or `certificate_arn`); logged-in demos use *Open in a new tab*. **S-4** ADR 0009 Accepted.

## Original recommendations (Phase 8, kept for reference)
- **S-1 Access**: the CloudFront URL is public (design content only). Recommendation: keep it public for prospects. Add a WAF IP
  allow-list later only if a customer-specific variant appears.
- **S-2 Live replication on AWS**: recommendation: a small Lambda + Function URL that reads the CDC Lambda's CloudWatch
  logs/DLQ as `/api/status|changes`, as a follow-up. Until then the hosted tab shows the replay.
- **S-3 Embedded app on AWS**: recommendation: set `certificate_arn` (ACM) so the ALB is HTTPS and the frame works for
  browsing. Demo the logged-in journey with *Open in new tab*. A single domain (CloudFront in front of the ALB too) is
  only worth it if John wants a fully embedded checkout.
- **S-4**: adopt ADR 0009 (S3 + CloudFront) → Accepted.
