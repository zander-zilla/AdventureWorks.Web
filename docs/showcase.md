# Showcase website (Phase 8)

A six-tab site that tells the modernization story to managers, directors and prospective customers. It's static, and
everything on it is generated from the repo's sources of truth. ADR 0009 covers the decisions.

| Tab | What it shows | Data / reuse |
|---|---|---|
| Presentation | 6 slides (challenge → approach → migration → app → analytics → operations) with live KPIs; ←/→ keys | `results.json`, `load-stats.json`, mapping/access-pattern counts |
| Architecture | Before / After (AWS) SVG diagram; click a component for what/why/repo path | component list in `showcase/site/app.js` |
| Data Mapping | **SQL → DynamoDB**: pick any of the 68 tables (filterable, grouped by target table) → item entity, PK/SK/GSI key templates, denormalised copies, column → attribute/transform. **DynamoDB → Redshift**: every dim/fact (+ static carry-over) → source items → `stg` MVs → `dw.*` | `design/mapping/mapping.json` (`sources`, `dw_lineage`) |
| Access Patterns | All 70 patterns, filter by domain/scope/text; DynamoDB key conditions per pattern | `docs/design/access-patterns.json` + `mapping.json` `access_patterns` |
| Live Replication | The Phase 4 replication monitor, embedded; recorded replay by default, live with `--live` | `cdc/monitor/index.html`, `showcase/fixtures/replication-replay` |
| The App | The .NET 10 DynamoDB shopper app in a frame plus an *Open in new tab* link | `config.json` `appUrl` |

## Run locally
```bash
scripts/showcase-up.sh                                # http://localhost:8088, replay, no app
scripts/after-up.sh && scripts/showcase-up.sh --app-url http://localhost:5090   # embed the local app
scripts/cdc-up.sh   && scripts/showcase-up.sh --live  # stream the CDC consumer (:8090) instead of the replay
```
Tests: `python -m pytest tests/showcase` (`SHOWCASE_SCREENSHOTS=dir` saves one screenshot per tab; `SHOWCASE_APP_URL` embeds a real app).

## On AWS
`infra/modules/showcase` (private S3 bucket, CloudFront OAC, HTTPS, AWS managed security-headers policy, no caching
for `config.json`/`data/*`/`api/*`), on by default (`enable_showcase`). `scripts/aws/push-showcase.sh <env>` builds with
the `after_url` output and syncs + invalidates. The deploy workflow runs it on `apply` and `app-only`. Output: `showcase_url`.
The app's task gets `Showcase__FrameAncestors = <CloudFront origin>`. Teardown removes the site too (`force_destroy`).

## Changes from initial design
- PLAN.md had five tabs (Presentation / Architecture / Data Mapping / Access Patterns / Live App). As built there are **six**:
  *Live Replication* is a separate tab, and the app is its own tab.
- The Phase 4 monitor comment said it would be embedded in the *Data Mapping* tab. It lives on the *Live Replication* tab
  instead, unchanged except that it shows `recorded replay` when the API says so.
- ADR 0008 suggested revisiting ECS Express Mode for Phase 8. That isn't needed: the site is static on S3 + CloudFront, and the app stays on
  Fargate + ALB.
- On AWS there's no hosted CDC consumer API (AWS CDC is DMS → Kinesis → Lambda), so the hosted Live Replication tab is
  the recorded replay. Live streaming is local only for now (open decision S-2).
- New app setting `Showcase:FrameAncestors` (CSP `frame-ancestors`), off unless configured.

## Open decisions (for John)
- **S-1 Access**: the CloudFront URL is public (design content only). Recommendation: keep it public for prospects. Add a WAF IP
  allow-list later only if a customer-specific variant appears.
- **S-2 Live replication on AWS**: recommendation: a small Lambda + Function URL that reads the CDC Lambda's CloudWatch
  logs/DLQ as `/api/status|changes`, as a follow-up. Until then the hosted tab shows the replay.
- **S-3 Embedded app on AWS**: recommendation: set `certificate_arn` (ACM) so the ALB is HTTPS and the frame works for
  browsing. Demo the logged-in journey with *Open in new tab*. A single domain (CloudFront in front of the ALB too) is
  only worth it if John wants a fully embedded checkout.
- **S-4**: adopt ADR 0009 (S3 + CloudFront) → Accepted.
