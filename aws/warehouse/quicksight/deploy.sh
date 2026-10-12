#!/usr/bin/env bash
# Create/update the QuickSight dashboard from dashboard.json (NOT run in CI - it calls AWS and QuickSight is billed per user).
# Requires: terraform apply of ../terraform with quicksight_principal_arn set, then:
#   ACCOUNT_ID=... QS_PRINCIPAL=arn:aws:quicksight:...:user/default/... DATA_SET_ARN=$(terraform -chdir=../terraform output -raw quicksight_data_set_arn) ./deploy.sh
set -euo pipefail
cd "$(dirname "$0")"
in=$(sed -e "s|\${account_id}|$ACCOUNT_ID|g" -e "s|\${quicksight_principal_arn}|$QS_PRINCIPAL|g" -e "s|\${data_set_arn}|$DATA_SET_ARN|g" dashboard.json)
if aws quicksight describe-dashboard --aws-account-id "$ACCOUNT_ID" --dashboard-id aw-sales-overview >/dev/null 2>&1; then
  echo "$in" | python3 -c 'import json,sys; d=json.load(sys.stdin); d.pop("Permissions"); print(json.dumps(d))' > /tmp/qs-update.json
  aws quicksight update-dashboard --cli-input-json file:///tmp/qs-update.json
else
  echo "$in" > /tmp/qs-create.json; aws quicksight create-dashboard --cli-input-json file:///tmp/qs-create.json
fi
