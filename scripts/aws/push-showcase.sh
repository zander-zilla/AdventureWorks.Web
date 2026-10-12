#!/usr/bin/env bash
# Phase 8 (ADR 0009): build the showcase with the deployed app URL and upload it to the showcase bucket, then
# invalidate CloudFront. Usage: scripts/aws/push-showcase.sh <env>   (after `scripts/aws/tf.sh <env> apply`)
set -euo pipefail
ENVNAME="${1:?usage: push-showcase.sh <env>}"
cd "$(dirname "$0")/../.."
out() { terraform -chdir=infra/live output -raw "$1"; }
BUCKET="$(out showcase_bucket)"; DIST="$(out showcase_distribution_id)"; APP_URL="$(out after_url)"; BEFORE_URL="$(out before_url 2>/dev/null || true)"; [ "$BEFORE_URL" = null ] && BEFORE_URL=""
test -n "$BUCKET" && test "$BUCKET" != null || { echo "enable_showcase is false for $ENVNAME"; exit 1; }
python3 showcase/build.py --out showcase/dist --app-url "$APP_URL" --before-url "$BEFORE_URL"
aws s3 sync showcase/dist "s3://$BUCKET/" --delete --only-show-errors
# extension-less replay API files need a JSON content type
for f in status changes; do
  aws s3 cp "showcase/dist/api/$f" "s3://$BUCKET/api/$f" --content-type application/json --only-show-errors
done
aws cloudfront create-invalidation --distribution-id "$DIST" --paths '/*' --query Invalidation.Id --output text
echo "showcase: $(out showcase_url)"
