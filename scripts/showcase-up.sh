#!/usr/bin/env bash
# Phase 8 showcase: build the static site and serve it on :8088 (SHOWCASE_PORT).
#   scripts/showcase-up.sh                         recorded replication replay, no app URL
#   scripts/showcase-up.sh --app-url http://localhost:5090   embed the local .NET 10 app (scripts/after-up.sh)
#   scripts/showcase-up.sh --live [http://localhost:8090]    stream the CDC consumer (scripts/cdc-up.sh)
set -euo pipefail
cd "$(dirname "$0")/.."
APP_URL="${SHOWCASE_APP_URL:-}"; LIVE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --app-url) APP_URL="$2"; shift 2;;
    --live) if [ "${2:-}" ] && [[ "$2" != --* ]]; then LIVE="$2"; shift 2; else LIVE="http://localhost:8090"; shift; fi;;
    *) echo "unknown option $1" >&2; exit 2;;
  esac
done
PY="${PYTHON:-python3}"
"$PY" showcase/build.py --app-url "$APP_URL" --monitor-mode "$([ -n "$LIVE" ] && echo live || echo replay)"
exec "$PY" showcase/serve.py ${LIVE:+--live-api "$LIVE"}
