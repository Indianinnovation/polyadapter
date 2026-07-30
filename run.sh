#!/usr/bin/env bash
# Run once on the pod (vllm/vllm-openai:latest image, 1x A100 80GB or L40S 48GB).
set -euo pipefail
cd "$(dirname "$0")"

python3 -c "import peft, fastapi, httpx" 2>/dev/null || pip install -q peft fastapi uvicorn httpx

[ -d adapters ] || python3 bake_loras.py

python3 -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-7B-Instruct \
    --enable-lora \
    --max-loras 8 \
    --max-lora-rank 16 \
    --lora-modules legal=./adapters/legal finance=./adapters/finance \
    --gpu-memory-utilization 0.90 \
    --port 8000 &

until curl -sf localhost:8000/health >/dev/null; do sleep 2; done
echo "vllm up"

python3 gateway.py
