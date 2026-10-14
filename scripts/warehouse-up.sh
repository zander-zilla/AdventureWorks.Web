#!/usr/bin/env bash
# Phase 6 local verification (CI job "warehouse"): DynamoDB Local (already loaded by design-validate.sh or cdc-up.sh)
# -> export in DynamoDB-export format -> Postgres stand-in in the zero-ETL landing shape -> staging MVs -> star schema
# (the same dw.sp_build_star() Redshift runs) -> reconcile against AdventureWorksDW2022.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
PY="${PYTHON:-python3}"; export DDB_MULTI="${DDB_MULTI:-1}"
EXPORT="${AW_EXPORT:-/tmp/aw-export}"
if ! docker ps --format '{{.Names}}' | grep -q '^aw-wh-postgres$'; then
  docker rm -f aw-wh-postgres >/dev/null 2>&1 || true
  # small footprint: the box/CI runner also hosts SQL Server + 7 DynamoDB Local JVMs
  docker run -d --name aw-wh-postgres -m 1500m --shm-size=512m -p 5433:5432 -e POSTGRES_USER=aw -e POSTGRES_PASSWORD=aw -e POSTGRES_DB=aw_dw \
    postgres:16-alpine -c shared_buffers=256MB -c work_mem=64MB -c max_wal_size=2GB -c fsync=off -c synchronous_commit=off >/dev/null
fi
for i in $(seq 1 60); do docker exec aw-wh-postgres pg_isready -U aw -d aw_dw >/dev/null 2>&1 && break; sleep 1; done
rm -rf "$EXPORT"
$PY warehouse/local/export_ddb.py --out "$EXPORT"
$PY warehouse/local/check_item_sizes.py --export "$EXPORT"
if [ "${STOP_DDB_AFTER_EXPORT:-0}" = 1 ]; then docker rm -f $(docker ps -aq --filter name=aw-ddb-) >/dev/null; fi
$PY warehouse/local/load_landing.py --export "$EXPORT"
$PY warehouse/local/static_export.py --pg --out /tmp/aw-static
$PY warehouse/local/run_star.py
$PY warehouse/local/reconcile.py --out /tmp/warehouse-reconcile.json ${WH_RECONCILE_ARGS:-}   # C2-7: --original-only with generated data
