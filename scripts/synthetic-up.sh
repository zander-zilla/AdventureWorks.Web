#!/usr/bin/env bash
# C2-7 local / CI verification of the generated data (the 6-month slice 2014-07..2014-12, SYNTHETIC_END to change it):
#  1. SQL Server with the ORIGINAL AdventureWorks2022 (restored from the backup if generated rows are present)
#  2. generated rows inserted into SQL Server through the normal insert path (scripts/synthetic/load_sql.py, monthly batches)
#  3. database tests: original rows unchanged, resumable, constraints, identities back in the original range
#  4. DynamoDB Local loaded by the Phase 3 loader (the local fast path; on AWS the rows go through CDC -> DMS -> Lambda)
#  5. reconcile SQL vs DynamoDB over everything, then --original-only against the committed Chapter 1 baseline
#  6. derived AI inputs (complete months only) over the longer history
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
export MSSQL_SA_PASSWORD="${MSSQL_SA_PASSWORD:-AdvWorks!2026}" DDB_MULTI=1
PY="${PYTHON:-python3}"; END="${SYNTHETIC_END:-2014-12-31}"
if ! docker ps --format '{{.Names}}' | grep -q '^aw-before-sqlserver-1$'; then
  scripts/fetch-baks.sh
  (cd docker/before && docker compose up -d sqlserver)
  for i in $(seq 1 60); do [ "$(docker inspect -f '{{.State.Health.Status}}' aw-before-sqlserver-1)" = healthy ] && break; sleep 5; done
fi
scripts/synthetic/restore-original.sh
$PY scripts/synthetic/fit.py --out /tmp/profile.json && cmp /tmp/profile.json scripts/synthetic/profile.json   # committed profile in sync
$PY scripts/synthetic/original_checksum.py --out /tmp/original-before.json
$PY scripts/synthetic/load_sql.py --end "$END" | tee /tmp/synthetic-load.json
AW_SYN_IT=1 SYNTHETIC_END="$END" $PY -m pytest -q -p no:cacheprovider tests/synthetic/test_load_sql.py
for p in 8001 8002 8003 8004 8005 8006 8007; do docker rm -f aw-ddb-$p >/dev/null 2>&1 || true; done
scripts/ddb-local-up.sh
$PY scripts/design/expand_mapping.py
$PY scripts/loader/load.py --recreate --workers 8 --stats /tmp/load-stats-synthetic.json
$PY scripts/reconcile.py --out /tmp/reconcile-all.json
$PY scripts/reconcile.py --original-only --baseline docs/chapter-2/synthetic/original-baseline.json --out /tmp/reconcile-original.json
$PY scripts/loader/derive_ai.py
