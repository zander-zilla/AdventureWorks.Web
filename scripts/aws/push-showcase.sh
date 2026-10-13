#!/usr/bin/env bash
# Phase 8 (ADR 0009) + C2-1: build the Chapter 2 showcase with the deployed app URLs and upload it to the showcase
# bucket, then invalidate CloudFront. Chapter 2 lives at / and never writes /c1/ (Chapter 1 is frozen, see
# push-showcase-c1.sh); if /c1/ is still empty it is seeded once from the v1.0-migration release asset.
# Usage: scripts/aws/push-showcase.sh <env>   (after `scripts/aws/tf.sh <env> apply`)
set -euo pipefail
ENVNAME="${1:?usage: push-showcase.sh <env>}"
cd "$(dirname "$0")/../.."
out() { terraform -chdir=infra/live output -raw "$1"; }
BUCKET="$(out showcase_bucket)"; DIST="$(out showcase_distribution_id)"; APP_URL="$(out after_url)"; BEFORE_URL="$(out before_url 2>/dev/null || true)"; [ "$BEFORE_URL" = null ] && BEFORE_URL=""
SPA_URL="$(out spa_url 2>/dev/null || true)"; [ "$SPA_URL" = null ] && SPA_URL=""
test -n "$BUCKET" && test "$BUCKET" != null || { echo "enable_showcase is false for $ENVNAME"; exit 1; }
# Phase 8b (S-2): /api/* on CloudFront goes to the monitor API Lambda (falls back to the replay files uploaded below)
MODE=replay; [ "$(out showcase_monitor_api 2>/dev/null || echo false)" = true ] && MODE=aws
(cd src/web && npm ci --no-audit --no-fund && npm run build:showcase)
python3 showcase/build.py --out showcase/dist --app-url "$APP_URL" --before-url "$BEFORE_URL" --spa-url "$SPA_URL" --monitor-mode "$MODE"
aws s3 sync showcase/dist "s3://$BUCKET/" --delete --exclude 'c1/*' --only-show-errors
# extension-less replay API files need a JSON content type
for f in status changes; do
  aws s3 cp "showcase/dist/api/$f" "s3://$BUCKET/api/$f" --content-type application/json --only-show-errors
done
aws s3api head-object --bucket "$BUCKET" --key c1/index.html >/dev/null 2>&1 || scripts/aws/push-showcase-c1.sh "$ENVNAME" --no-invalidate
aws cloudfront create-invalidation --distribution-id "$DIST" --paths '/*' --query Invalidation.Id --output text
echo "showcase: $(out showcase_url)  (Chapter 1: $(out showcase_url)c1/)"
