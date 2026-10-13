#!/usr/bin/env bash
# Entry point of the tools image (docker/tools/Dockerfile): one-off jobs inside the VPC.
set -euo pipefail
cd /repo
case "${1:-}" in
  db-init)   python scripts/aws/db_init.py ;;
  bulk-load) shift; python scripts/loader/load.py --stats /tmp/load-stats.json "$@" ;;
  derive-ai) python scripts/loader/derive_ai.py ;;   # C2-6: monthly demand + customers also bought (after bulk-load)
  reset-demo) python - <<'PY'
import os, pymssql
c = pymssql.connect(server=os.environ["SQL_HOST"], user=os.environ["SQL_USER"], password=os.environ["MSSQL_SA_PASSWORD"], autocommit=True)
c.cursor().execute(open("scripts/reset-demo.sql").read())
print("demo orders removed")
PY
  ;;
  *) echo "usage: db-init | bulk-load [--only ...] | derive-ai | reset-demo" >&2; exit 2 ;;
esac
