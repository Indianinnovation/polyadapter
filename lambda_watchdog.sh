#!/usr/bin/env bash
# Lambda Cloud has no spend-cap setting; this polls the instance's own hourly
# rate against wall-clock time since launch and terminates it before BUDGET_USD.
set -euo pipefail
cd "$(dirname "$0")"

INSTANCE_ID="$1"
BUDGET_USD="${2:-20}"
API_KEY=$(cat vllm.txt)
SAFETY_MARGIN=0.9  # terminate at 90% of budget to leave headroom for poll interval

START=$(date +%s)
while true; do
    STATUS=$(curl -s -u "$API_KEY:" "https://cloud.lambdalabs.com/api/v1/instances/$INSTANCE_ID")
    STATE=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('data',{}).get('status','unknown'))" "$STATUS")

    if [ "$STATE" = "terminated" ] || [ "$STATE" = "unknown" ]; then
        echo "$(date -u +%H:%M:%S) instance $STATE, watchdog exiting"
        break
    fi

    PRICE_CENTS=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['data']['instance_type']['price_cents_per_hour'])" "$STATUS")
    NOW=$(date +%s)
    SPEND=$(python3 -c "print(($NOW - $START) / 3600 * $PRICE_CENTS / 100)")
    CAP=$(python3 -c "print($BUDGET_USD * $SAFETY_MARGIN)")
    echo "$(date -u +%H:%M:%S) spend so far: \$$(printf '%.2f' "$SPEND") / cap \$$(printf '%.2f' "$CAP")"

    if python3 -c "import sys; sys.exit(0 if float(sys.argv[1]) >= float(sys.argv[2]) else 1)" "$SPEND" "$CAP"; then
        echo "$(date -u +%H:%M:%S) budget cap reached — terminating $INSTANCE_ID"
        curl -s -X POST -u "$API_KEY:" "https://cloud.lambdalabs.com/api/v1/instance-operations/terminate" \
            -H "Content-Type: application/json" \
            -d "{\"instance_ids\":[\"$INSTANCE_ID\"]}"
        break
    fi
    sleep 120
done
