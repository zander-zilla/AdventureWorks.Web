# ADR 0009: Showcase website as a static site on S3 + CloudFront, data from the repo's sources of truth

Status: Proposed (Phase 8). Code only, nothing applied (no AWS calls).

## Context
Phase 8 needs a site for managers, directors and prospective customers with six tabs: Presentation, Architecture,
Data Mapping, Access Patterns, Live Replication, App. It must be static-buildable with optional live APIs, run locally from
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
3. **Hosting: private S3 bucket + CloudFront with origin access control** (`infra/modules/showcase`, `enable_showcase`,
   default on), content uploaded by `scripts/aws/push-showcase.sh` (deploy workflow, after the images).
   - *Served by the Fargate app* (wwwroot): same origin as the app, so the App tab could always embed it. But the site
     would be unreachable whenever the app is scaled to 0 or the stack is torn down after a demo (ADR 0008 decision 2),
     it would sit behind the ALB IP allow-list, and site edits would need an image rebuild.
   - *S3 + CloudFront*: about USD 0 when idle, HTTPS by default, stays online between demos (Presentation,
     Architecture, Mapping, Access Patterns and the replay need no backend), and content updates don't need an apply.
     It's chosen.
   - *Amplify Hosting*: works, but it's a second deployment system next to Terraform/GitHub Actions.
4. **App tab**: iframe of the app URL (`config.json` `appUrl`, set from the `after_url` output on deploy) plus an *Open in new
   tab* link. The app gains `Showcase:FrameAncestors`: when set, it sends `Content-Security-Policy: frame-ancestors 'self' <origins>`
   instead of antiforgery's `X-Frame-Options: SAMEORIGIN` (Terraform sets it to the CloudFront origin; local compose to
   `localhost:*`). On AWS the ALB is HTTP unless `certificate_arn` is set. Then the HTTPS site can't frame it (mixed
   content), so the tab shows a link instead.
5. **Tests**: `tests/showcase` (pytest + Playwright, Chromium) builds into a temp dir, walks every tab, asserts counts
   against mapping.json/access-patterns.json, fails on any page error, and saves screenshots. They run in the `showcase` workflow
   (stub app) and in the `after` workflow (real .NET 10 app on DynamoDB Local). Terraform offline tests cover the module.

## Consequences
- The site is public to anyone with the CloudFront URL. It contains only design material and synthetic AdventureWorks data
  (no secrets). Add AWS WAF IP sets or CloudFront signed cookies if John wants it private.
- Logging in to the app *inside* the iframe on AWS also needs the auth cookie to be sent cross-site
  (CloudFront domain ≠ ALB domain → `SameSite=Lax` cookie is not sent in the frame). Browsing works embedded; for the
  shopper journey use *Open in new tab*, or put both behind one domain (see open decisions in docs/showcase.md).
