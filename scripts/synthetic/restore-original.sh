#!/usr/bin/env bash
# C2-7 removal: put the source back to the original AdventureWorks2022 sample (drops generated rows by restoring the backup).
# Local: the before-stack SQL Server container. AWS: run db-init again (scripts/aws/run-tool.sh <env> db-init) after dropping the DB.
set -euo pipefail
P="${MSSQL_SA_PASSWORD:-AdvWorks!2026}"
SQL=(docker exec aw-before-sqlserver-1 /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "$P" -b)
"${SQL[@]}" -Q "IF DB_ID('AdventureWorks2022') IS NOT NULL BEGIN ALTER DATABASE AdventureWorks2022 SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE AdventureWorks2022; END"
"${SQL[@]}" -i /sql/01-restore.sql >/dev/null
echo "AdventureWorks2022 restored from the original backup"
