#!/usr/bin/env bash
# Phase 3 validation: SQL Server (restored AW2022) + DynamoDB Local -> load via mapping -> run access-pattern tests vs SQL.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
export MSSQL_SA_PASSWORD="${MSSQL_SA_PASSWORD:-AdvWorks!2026}"
PY="${PYTHON:-python3}"
if ! docker ps --format '{{.Names}}' | grep -q '^aw-before-sqlserver-1$'; then
  scripts/fetch-baks.sh
  (cd docker/before && docker compose up -d sqlserver)
  for i in $(seq 1 60); do [ "$(docker inspect -f '{{.State.Health.Status}}' aw-before-sqlserver-1)" = healthy ] && break; sleep 5; done
  docker exec aw-before-sqlserver-1 /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -b -i /sql/01-restore.sql
fi
export DDB_MULTI=1
scripts/ddb-local-up.sh
$PY scripts/design/expand_mapping.py
$PY scripts/loader/load.py --recreate --workers 8 --stats /tmp/load-stats.json
$PY -m pytest -q tests/access_patterns
