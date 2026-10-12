#!/usr/bin/env bash
# Build + push the after (.NET 10), before (original app) and tools images to the stack's ECR repos, then roll ECS.
# Usage: scripts/aws/push-images.sh <env> [tag] [extra terraform args]   (the deploy workflow does the same in GitHub Actions)
set -euo pipefail
ENV="${1:?env}"; TAG="${2:-$(git rev-parse --short HEAD)}"; shift; if [ $# -gt 0 ]; then shift; fi; EXTRA=("$@")
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REPOS=$(terraform -chdir="$ROOT/infra/live" output -json ecr_repositories)
repo() { echo "$REPOS" | python3 -c "import json,sys;print(json.load(sys.stdin).get('$1',''))"; }
REG=$(repo after); REG=${REG%%/*}
aws ecr get-login-password | docker login --username AWS --password-stdin "$REG"
# C2-1: the SPA's Chapter 1 button links to <showcase_url>c1/ (empty when the showcase is disabled)
SHOWCASE_URL=$(terraform -chdir="$ROOT/infra/live" output -raw showcase_url 2>/dev/null || true); [ "$SHOWCASE_URL" = null ] && SHOWCASE_URL=""
build() { local name=$1 ctx=$2 file=$3; local r; r=$(repo "$name"); [ -n "$r" ] || return 0
  docker build --platform linux/amd64 --build-arg VITE_SHOWCASE_URL="$SHOWCASE_URL" -t "$r:$TAG" -t "$r:latest" -f "$file" "$ctx" && docker push -q "$r:$TAG" && docker push -q "$r:latest"; }
build after "$ROOT/src" "$ROOT/docker/after/Dockerfile"
build before "$ROOT" "$ROOT/docker/before/Dockerfile.app"
build tools "$ROOT" "$ROOT/docker/tools/Dockerfile"
"$ROOT/scripts/aws/tf.sh" "$ENV" apply -auto-approve -var image_tag="$TAG" "${EXTRA[@]}"
