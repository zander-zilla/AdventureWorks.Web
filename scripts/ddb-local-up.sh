#!/usr/bin/env bash
# Start one in-memory DynamoDB Local per domain table (ports 8001-8007, host networking). Use with DDB_MULTI=1.
set -euo pipefail
for i in 0 1 2 3 4 5 6; do
  port=$((8001 + i)); name="aw-ddb-$port"
  docker ps --format '{{.Names}}' | grep -q "^$name$" && continue
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker run -d --name "$name" --network host amazon/dynamodb-local:latest -Xmx${DDB_XMX:-2g} -jar DynamoDBLocal.jar -inMemory -sharedDb -port "$port" >/dev/null
done
for i in 0 1 2 3 4 5 6; do for t in $(seq 1 30); do curl -s -o /dev/null "localhost:$((8001 + i))" && break; sleep 1; done; done
echo "DynamoDB Local on ports 8001-8007"
