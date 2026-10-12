#!/usr/bin/env bash
# Start the DMS CDC task from the time printed by db-init (captured before the bulk load). Writes are conditional on
# the source position (src_lsn), so the overlap with the bulk load is harmless.
# Usage: scripts/aws/start-cdc.sh <env> <UTC start time, e.g. 2026-10-20T15:04:05Z>
set -euo pipefail
ENV="${1:?env}"; START="${2:?cdc start time (UTC)}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TASK=$(terraform -chdir="$ROOT/infra/live" output -raw dms_replication_task_arn)
aws dms test-connection --replication-instance-arn "$(aws dms describe-replication-tasks --filters Name=replication-task-arn,Values="$TASK" --query 'ReplicationTasks[0].ReplicationInstanceArn' --output text)" \
  --endpoint-arn "$(aws dms describe-replication-tasks --filters Name=replication-task-arn,Values="$TASK" --query 'ReplicationTasks[0].SourceEndpointArn' --output text)" >/dev/null || true
aws dms start-replication-task --replication-task-arn "$TASK" --start-replication-task-type start-replication \
  --cdc-start-time "$START" --query 'ReplicationTask.Status' --output text
