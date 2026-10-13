#!/usr/bin/env bash
# Start one in-memory DynamoDB Local per domain table (ports 8001-8007, host networking). Use with DDB_MULTI=1.
# DDB_DISK=1 (C2-7 2-year slice): disk-backed (SQLite inside the container) with a 768 MB heap instead of in-memory 2 GB,
# so 7 JVMs + SQL Server + ~1.7 M items fit a 16 GB CI runner (in-memory ran it out of memory).
set -euo pipefail
if [ "${DDB_DISK:-0}" = 1 ]; then STORE=(-dbPath .); XMX="${DDB_XMX:-768m}"; else STORE=(-inMemory); XMX="${DDB_XMX:-2g}"; fi
for i in 0 1 2 3 4 5 6; do
  port=$((8001 + i)); name="aw-ddb-$port"
  docker ps --format '{{.Names}}' | grep -q "^$name$" && continue
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker run -d --name "$name" --network host amazon/dynamodb-local:latest -Xmx$XMX -jar DynamoDBLocal.jar "${STORE[@]}" -sharedDb -port "$port" >/dev/null
done
for i in 0 1 2 3 4 5 6; do for t in $(seq 1 30); do curl -s -o /dev/null "localhost:$((8001 + i))" && break; sleep 1; done; done
echo "DynamoDB Local on ports 8001-8007"
