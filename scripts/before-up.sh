#!/usr/bin/env bash
# Bring up the BEFORE stack end to end: fetch backups, start SQL Server, restore DBs, enable CDC, start the app.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export MSSQL_SA_PASSWORD="${MSSQL_SA_PASSWORD:-AdvWorks!2026}"
"$ROOT/scripts/fetch-baks.sh"
cd "$ROOT/docker/before"
docker compose up -d sqlserver
for i in $(seq 1 60); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' aw-before-sqlserver-1)" = healthy ] && break; sleep 5
done
SQLCMD=(docker exec aw-before-sqlserver-1 /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -b -W)
"${SQLCMD[@]}" -i /sql/01-restore.sql
"${SQLCMD[@]}" -i /sql/02-enable-cdc.sql
"${SQLCMD[@]}" -Q "SELECT name, is_cdc_enabled FROM sys.databases WHERE name LIKE 'AdventureWorks%'; EXEC msdb.dbo.sp_help_job @job_name = N'cdc.AdventureWorks2022_capture', @job_aspect = N'JOB';" | head -20
docker compose up -d --build app
for i in $(seq 1 30); do curl -sf -o /dev/null http://localhost:5080/ && break; sleep 3; done
echo "BEFORE stack up: app http://localhost:5080  sql localhost,1433"
