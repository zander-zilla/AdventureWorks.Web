#!/usr/bin/env bash
# C2-1: publish the frozen Chapter 1 showcase to s3://<showcase bucket>/c1/ (same distribution, /c1/* behaviour).
# Content = the showcase-v1.0-migration.zip release asset (built from tag v1.0-migration by showcase-freeze.yml), or a
# local unzipped build via C1_DIR. Only c1/config.json is rewritten with the current stack URLs, so the frozen site
# frames today's apps and its Live Replication tab uses today's /api/* (CloudFront, unchanged).
# Usage: scripts/aws/push-showcase-c1.sh <env> [--no-invalidate]
set -euo pipefail
ENVNAME="${1:?usage: push-showcase-c1.sh <env> [--no-invalidate]}"; NOINV="${2:-}"
cd "$(dirname "$0")/../.."
TAG="${C1_TAG:-v1.0-migration}"; REPO="${GITHUB_REPOSITORY:-zander-zilla/AdventureWorks.Web}"
out() { terraform -chdir=infra/live output -raw "$1"; }
BUCKET="$(out showcase_bucket)"; DIST="$(out showcase_distribution_id)"; APP_URL="$(out after_url)"
BEFORE_URL="$(out before_url 2>/dev/null || true)"; [ "$BEFORE_URL" = null ] && BEFORE_URL=""
MODE=replay; [ "$(out showcase_monitor_api 2>/dev/null || echo false)" = true ] && MODE=aws
DIR="${C1_DIR:-}"
if [ -z "$DIR" ]; then
  DIR="$(mktemp -d)/c1"
  gh release download "$TAG" -R "$REPO" -p "showcase-$TAG.zip" -D "$(dirname "$DIR")" --clobber
  unzip -q "$(dirname "$DIR")/showcase-$TAG.zip" -d "$DIR"
fi
test -f "$DIR/index.html" || { echo "no Chapter 1 build in $DIR"; exit 1; }
python3 -c 'import json,sys; json.dump({"appUrl":sys.argv[1],"beforeUrl":sys.argv[2],"monitorApi":"","monitorMode":sys.argv[3]},open(sys.argv[4],"w"),indent=1)' \
  "${APP_URL%/}/classic" "$BEFORE_URL" "$MODE" "$DIR/config.json"   # C2-2: / is the SPA; Chapter 1's App tab keeps the Razor shop
aws s3 sync "$DIR" "s3://$BUCKET/c1/" --delete --only-show-errors
for f in status changes; do  # Chapter 1's own replay copies (used only when /api/* is not routed to the Lambda)
  [ -f "$DIR/api/$f" ] && aws s3 cp "$DIR/api/$f" "s3://$BUCKET/c1/api/$f" --content-type application/json --only-show-errors
done
[ "$NOINV" = --no-invalidate ] || aws cloudfront create-invalidation --distribution-id "$DIST" --paths '/c1/*' --query Invalidation.Id --output text
echo "Chapter 1 (frozen $TAG): $(out showcase_url)c1/"
