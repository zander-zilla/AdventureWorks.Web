#!/usr/bin/env bash
# Regenerates docs/discovery/schema.json and inventory.md from the live before-stack databases.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PW="${MSSQL_SA_PASSWORD:-AdvWorks!2026}"
TMP=$(mktemp -d)
for db in AdventureWorks2022 AdventureWorksDW2022; do
  docker exec -i aw-before-sqlserver-1 /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "$PW" -d "$db" -b -y 0 \
    < "$ROOT/scripts/discovery/inventory.sql" | tr -d '\r\n' | sed 's/^[^{]*//' > "$TMP/$db.json"
done
python3 "$ROOT/scripts/discovery/render.py" "$TMP" "$ROOT/docs/discovery"
python3 "$ROOT/scripts/discovery/domains.py"
