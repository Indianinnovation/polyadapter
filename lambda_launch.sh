#!/usr/bin/env bash
# Launch a Lambda Cloud GPU instance and start the budget watchdog.
set -euo pipefail
cd "$(dirname "$0")"

API_KEY=$(cat vllm.txt)
INSTANCE_TYPE="${INSTANCE_TYPE:-gpu_1x_a10}"
REGION="${REGION:-us-east-1}"
BUDGET_USD="${LAMBDA_BUDGET_USD:-20}"

RESP=$(curl -s -X POST -u "$API_KEY:" "https://cloud.lambdalabs.com/api/v1/instance-operations/launch" \
    -H "Content-Type: application/json" \
    -d "{\"region_name\":\"$REGION\",\"instance_type_name\":\"$INSTANCE_TYPE\",\"ssh_key_names\":[\"polyadapter-demo\"],\"name\":\"polyadapter-demo\"}")

INSTANCE_ID=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d['data']['instance_ids'][0])" "$RESP" 2>/dev/null) || {
    echo "launch failed: $RESP" >&2
    exit 1
}

echo "$INSTANCE_ID" > .lambda_instance_id
echo "launched: $INSTANCE_ID ($INSTANCE_TYPE in $REGION), budget cap \$$BUDGET_USD"

nohup ./lambda_watchdog.sh "$INSTANCE_ID" "$BUDGET_USD" > lambda_watchdog.log 2>&1 &
disown
echo "watchdog running (pid $!) -> lambda_watchdog.log"
