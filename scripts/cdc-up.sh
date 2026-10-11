#!/usr/bin/env bash
# Phase 4 local path: bulk load + CDC with no gap and no duplicates.
#  1. SQL Server (before stack) restored, CDC enabled on all 68 OLTP tables.
#  2. Fresh DynamoDB Local (one per table) + the awcdc consumer started PAUSED (it buffers, does not apply).
#  3. Debezium Server starts streaming from the current max LSN (snapshot.mode=no_data); we wait until it is streaming.
#     => every change committed from here on is captured and queued.
#  4. Bulk load (scripts/loader/load.py, items carry src_lsn = 0x000...0, the lowest position).
#  5. Resume the consumer: buffered changes apply in LSN order with conditional puts (src_lsn < position), so changes
#     that the bulk load already saw are re-applied idempotently (same item, newer position) and nothing is missed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
export MSSQL_SA_PASSWORD="${MSSQL_SA_PASSWORD:-AdvWorks!2026}" DDB_MULTI=1
PY="${PYTHON:-python3}"
SQLCMD=(docker exec aw-before-sqlserver-1 /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -b)

if ! docker ps --format '{{.Names}}' | grep -q '^aw-before-sqlserver-1$'; then
  scripts/fetch-baks.sh
  (cd docker/before && docker compose up -d sqlserver)
  for i in $(seq 1 60); do [ "$(docker inspect -f '{{.State.Health.Status}}' aw-before-sqlserver-1)" = healthy ] && break; sleep 5; done
fi
"${SQLCMD[@]}" -i /sql/01-restore.sql >/dev/null
"${SQLCMD[@]}" -i /sql/02-enable-cdc.sql
# CDC capture job polls every 5 s by default; 1 s makes the demo snappier.
"${SQLCMD[@]}" -d AdventureWorks2022 -Q "EXEC sys.sp_cdc_change_job @job_type = N'capture', @pollinginterval = 1; EXEC sys.sp_cdc_stop_job N'capture'; EXEC sys.sp_cdc_start_job N'capture';" || true

for p in 8001 8002 8003 8004 8005 8006 8007; do docker rm -f aw-ddb-$p >/dev/null 2>&1 || true; done  # fresh JVMs (recreate on a loaded one is slow)
scripts/ddb-local-up.sh
$PY -c "import sys; sys.path.insert(0,'scripts/loader'); import ddb, awmap; ddb.create_tables(awmap.load_mapping(), recreate=True)"

pkill -f cdc/consumer/consumer.py 2>/dev/null || true
rm -f /tmp/aw-cdc-consumer.sqlite*
nohup $PY cdc/consumer/consumer.py > /tmp/aw-cdc-consumer.log 2>&1 &
for i in $(seq 1 30); do curl -sf localhost:8090/health >/dev/null && break; sleep 1; done
curl -sf -X POST localhost:8090/control/pause >/dev/null

(cd docker/cdc && docker compose down -v >/dev/null 2>&1 || true; docker compose up -d)
echo "waiting for Debezium to start streaming..."
for i in $(seq 1 120); do
  docker logs aw-cdc-debezium-1 2>&1 | grep -q "Starting streaming" && break
  docker logs aw-cdc-debezium-1 2>&1 | grep -qE "ERROR .*(Connector|Engine)" && { docker logs aw-cdc-debezium-1 2>&1 | tail -50; exit 1; }
  sleep 2
done
docker logs aw-cdc-debezium-1 2>&1 | grep -m1 "Starting streaming" || { docker logs aw-cdc-debezium-1 2>&1 | tail -80; exit 1; }

$PY scripts/loader/load.py --workers 8 --stats /tmp/load-stats.json
curl -sf -X POST localhost:8090/control/resume
echo; echo "CDC streaming. Monitor: http://localhost:8090/  status: $(curl -s localhost:8090/api/status)"
