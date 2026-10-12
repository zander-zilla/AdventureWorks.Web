#!/usr/bin/env bash
# Tear the whole environment down after a demo (John: nothing should keep billing).
#  1. stop the DMS task (a running task blocks deletion)
#  2. turn DynamoDB deletion protection off (apply -var deletion_protection=false, targeted at the tables)
#  3. terraform destroy (ECR repos / buckets use force_destroy; RDS skips the final snapshot; KMS keys enter their
#     7-day pending-deletion window, $0)
#  4. list anything tagged Project=adventureworks-modernization that is still there
# The remote-state bucket and GitHub OIDC roles (infra/bootstrap) are kept (pennies/month); destroy them with
# `terraform -chdir=infra/bootstrap destroy` if the account is being retired (empty the versioned bucket first).
# Usage: scripts/aws/teardown.sh <env> [--yes] [extra terraform args, e.g. -var allowed_cidrs=...]
set -euo pipefail
ENV="${1:?env}"; YES="${2:-}"; shift; if [ $# -gt 0 ]; then shift; fi; EXTRA=("$@")
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; TF="$ROOT/scripts/aws/tf.sh"
if [ "$YES" != "--yes" ]; then
  read -r -p "Destroy EVERYTHING in environment '$ENV' (DynamoDB data, RDS, Redshift)? type the env name: " a
  [ "$a" = "$ENV" ] || { echo aborted; exit 1; }
fi
"$TF" "$ENV" init >/dev/null
TASK=$(terraform -chdir="$ROOT/infra/live" output -raw dms_replication_task_arn 2>/dev/null || true)
if [ -n "$TASK" ] && [ "$TASK" != "null" ]; then
  aws dms stop-replication-task --replication-task-arn "$TASK" >/dev/null 2>&1 && \
    aws dms wait replication-task-stopped --filters Name=replication-task-arn,Values="$TASK" || true
fi
"$TF" "$ENV" apply -auto-approve -var deletion_protection=false -target=module.dynamodb "${EXTRA[@]}"
"$TF" "$ENV" destroy -auto-approve -var deletion_protection=false "${EXTRA[@]}"
REGION=$(sed -n 's/^region *= *"\(.*\)"/\1/p' "$ROOT/infra/envs/$ENV.tfvars")
echo "Leftovers tagged Environment=$ENV (should be empty or only resources pending deletion):"
aws resourcegroupstaggingapi get-resources --region "${REGION:-us-east-1}" \
  --tag-filters Key=Project,Values=adventureworks-modernization Key=Environment,Values="$ENV" \
  --query 'ResourceTagMappingList[].ResourceARN' --output text || true
