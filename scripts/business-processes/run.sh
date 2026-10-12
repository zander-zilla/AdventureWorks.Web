#!/usr/bin/env bash
# Regenerate docs/business-processes/evidence.json from the running before stack.
set -euo pipefail
cd "$(dirname "$0")/../.."
docker exec -i aw-before-sqlserver-1 /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P 'AdvWorks!2026' -b -W -s '|' -h -1 \
  < scripts/business-processes/evidence.sql > /tmp/bp-evidence.txt
python3 scripts/business-processes/evidence.py /tmp/bp-evidence.txt docs/business-processes/evidence.json
