#!/usr/bin/env bash
# Run a one-off tools task (db-init | bulk-load | derive-ai | reset-demo | synthetic-load | synthetic-trickle) on ECS Fargate inside the VPC and follow its log.
# Usage: scripts/aws/run-tool.sh <env> db-init|bulk-load|reset-demo [args...]
set -euo pipefail
ENV="${1:?env}"; shift
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
out() { terraform -chdir="$ROOT/infra/live" output -raw "$1"; }
CLUSTER=$(out ecs_cluster); TD=$(out tools_task_definition); SG=$(out tasks_security_group_id)
SUBNETS=$(terraform -chdir="$ROOT/infra/live" output -json public_subnet_ids | python3 -c 'import json,sys;print(",".join(json.load(sys.stdin)))')
CMD=$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1:]))' "$@")
ARN=$(aws ecs run-task --cluster "$CLUSTER" --task-definition "$TD" --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG],assignPublicIp=ENABLED}" \
  --overrides "{\"containerOverrides\":[{\"name\":\"tools\",\"command\":$CMD}]}" --query 'tasks[0].taskArn' --output text)
echo "task: $ARN"
aws ecs wait tasks-running --cluster "$CLUSTER" --tasks "$ARN" || true
aws logs tail "/ecs/aw-$ENV" --log-stream-name-prefix "tools/tools/${ARN##*/}" --follow &
TAIL=$!
aws ecs wait tasks-stopped --cluster "$CLUSTER" --tasks "$ARN" || aws ecs wait tasks-stopped --cluster "$CLUSTER" --tasks "$ARN"
sleep 5; kill $TAIL 2>/dev/null || true
CODE=$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$ARN" --query 'tasks[0].containers[0].exitCode' --output text)
echo "exit code: $CODE"; [ "$CODE" = 0 ]
