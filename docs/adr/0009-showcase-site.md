# ADR 0009: Showcase website as a static site on S3 + CloudFront, data from the repo's sources of truth

Status: Accepted (John, 2026-10-12; S-1..S-4). Code only, nothing applied (no AWS calls). Amended by Phase 8b (decisions 2a, 4).

## Context
Phase 8 needs a site for managers, directors and prospective customers with eight tabs: Presentation, Before Architecture,
After Architecture, Data Mapping, Access Patterns, Live Replication, Before App, After App. It must be static-buildable with optional live APIs, run locally from
one script, be part of the Terraform deployment, and reuse what earlier phases built (mapping.json, access-patterns.json,
the Phase 4 replication monitor, the Phase 5 app).

## Decision
1. **Plain HTML/CSS/JS, no framework or bundler** (`showcase/site`). `showcase/build.py` copies the site plus
   `design/mapping/mapping.json`, `docs/design/access-patterns.json`, `docs/migration/results.json`,
   `docs/design/load-stats.json` into `dist/data/`, so every number and key on the site comes from the files that also
   drive the loader, CDC transform and Redshift views. There's no hand-maintained copy and no node_modules to audit.
2. **Live Replication reuses the Phase 4 monitor unchanged** (`cdc/monitor/index.html` → `dist/monitor.html`, in an
   iframe). Static mode serves a recorded replay at `dist/api/status` and `dist/api/changes` (same API shape; S3 and
   `http.server` ignore the query string). Live mode is `scripts/showcase-up.sh --live`: `showcase/serve.py` proxies `/api/*`
   to the CDC consumer.
   2a. **On AWS (S-2, Phase 8b)**: the CDC Lambda records applied changes in `<name>-cdc-monitor` (DynamoDB, 24 h TTL);
   `cdc/monitor_api` (Lambda, Function URL, `AWS_IAM`) serves the same contract. CloudFront sends `/api/*` to an origin
   group (Function URL via Lambda OAC first, the S3 replay second), so a paused/torn-down stack or an error shows the
   recorded sample. Rejected: reading CloudWatch Logs per poll (slow, billed per GB scanned); a public Function URL
   (anyone could call it directly, no CDN in front).
3. **Hosting: private S3 bucket + CloudFront with origin access control** (`infra/modules/showcase`, `enable_showcase`,
   default on), content uploaded by `scripts/aws/push-showcase.sh` (deploy workflow, after the images).
   - *Served by the Fargate app* (wwwroot): same origin as the app, so the App tab could always embed it. But the site
     would be unreachable whenever the app is scaled to 0 or the stack is torn down after a demo (ADR 0008 decision 2),
     it would sit behind the ALB IP allow-list, and site edits would need an image rebuild.
   - *S3 + CloudFront*: about USD 0 when idle, HTTPS by default, stays online between demos (Presentation,
     Architecture, Mapping, Access Patterns and the replay need no backend), and content updates don't need an apply.
     It's chosen.
   - *Amplify Hosting*: works, but it's a second deployment system next to Terraform/GitHub Actions.
4. **Before App / After App tabs**: iframes of `beforeUrl`/`appUrl` (`before_url`/`after_url` outputs on deploy) plus *Open in new
   tab* links. Live Replication can show the Before App side by side with the monitor. Both apps gain `Showcase:FrameAncestors`: when set, it sends `Content-Security-Policy: frame-ancestors 'self' <origins>`
   instead of antiforgery's `X-Frame-Options: SAMEORIGIN` (Terraform sets it to the CloudFront origin; local compose to
   `localhost:*`). On AWS the ALB is HTTP unless `domain_name` (ACM certificate requested by
   Terraform, DNS validation, optional Route 53 records) or `certificate_arn` is set (S-3). Then both listeners are HTTPS
   (443 After, 8080 Before) and the tabs embed the apps; without it the HTTPS site can't frame them (mixed content), so
   the tab shows a link.
5. **Tests**: `tests/showcase` (pytest + Playwright, Chromium) builds into a temp dir, walks every tab, asserts counts
   against mapping.json/access-patterns.json, fails on any page error, and saves screenshots. They run in the `showcase` workflow
   (stub app) and in the `after` workflow (real .NET 10 app on DynamoDB Local). Terraform offline tests cover the module.

## Consequences
- The site is public to anyone with the CloudFront URL (S-1, accepted). It contains only design material and synthetic AdventureWorks data
  (no secrets). The live API exposes the same synthetic demo rows that the monitor shows; reserved concurrency 5 caps the
  cost of abuse. Add AWS WAF IP sets or CloudFront signed cookies if a private variant is ever needed.
- Logging in to the app *inside* the iframe on AWS also needs the auth cookie to be sent cross-site
  (CloudFront domain ≠ ALB domain → `SameSite=Lax` cookie is not sent in the frame). Browsing works embedded; for the
  shopper journey use *Open in a new tab* (S-3, accepted). One domain for site and apps would only be worth it for a fully embedded checkout.
