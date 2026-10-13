#!/usr/bin/env bash
# AFTER environment: SQL Server (before stack, restore only) -> DynamoDB Local (one per table) loaded by the Phase 3 loader
# -> .NET 10 app container on http://localhost:5090.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
export MSSQL_SA_PASSWORD="${MSSQL_SA_PASSWORD:-AdvWorks!2026}" DDB_MULTI=1
PY="${PYTHON:-python3}"
if ! docker ps --format '{{.Names}}' | grep -q '^aw-before-sqlserver-1$'; then
  scripts/fetch-baks.sh
  (cd docker/before && docker compose up -d sqlserver)
  for i in $(seq 1 60); do [ "$(docker inspect -f '{{.State.Health.Status}}' aw-before-sqlserver-1)" = healthy ] && break; sleep 5; done
  docker exec aw-before-sqlserver-1 /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -b -i /sql/01-restore.sql
fi
# C2-7: SYNTHETIC=1 adds the generated 2-year slice (2014-07..2016-06, override with SYNTHETIC_END) to SQL Server first;
# the loader then carries original + generated rows (the local fast path; on AWS they go through CDC).
if [ "${SYNTHETIC:-0}" = 1 ]; then
  $PY scripts/synthetic/load_sql.py --end "${SYNTHETIC_END:-2016-06-30}"
  export AW_OFFER_DATE="${SYNTHETIC_END:-2016-06-30}"   # offers as of the generated data's "now" (AWS full load: today)
fi
if [ "${SKIP_LOAD:-0}" != 1 ]; then
  scripts/ddb-local-up.sh
  $PY scripts/loader/load.py --recreate --workers 8 --stats /tmp/load-stats.json
  $PY scripts/loader/derive_ai.py
fi
docker compose -f docker/after/docker-compose.yml up -d --build app
for i in $(seq 1 60); do curl -fs http://localhost:5090/healthz >/dev/null && break; sleep 2; done
curl -fs http://localhost:5090/healthz && echo " - after app up on http://localhost:5090"
