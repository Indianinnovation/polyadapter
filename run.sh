#!/usr/bin/env bash
# Run once on the pod (vllm/vllm-openai:latest image). MODEL=... to override the base.
set -euo pipefail
cd "$(dirname "$0")"

export MODEL="${MODEL:-Qwen/Qwen2.5-3B-Instruct}"

python3 -c "import peft, fastapi, httpx" 2>/dev/null || pip install -q peft fastapi uvicorn httpx

[ -d adapters ] || python3 bake_loras.py

# adapters only load against the base they were trained on; fail loud, not with a shape error
grep -q "\"$MODEL\"" adapters/legal/adapter_config.json ||
    { echo "adapters were baked for a different base; rm -rf adapters and re-run" >&2; exit 1; }

python3 -m vllm.entrypoints.openai.api_server \
    --model "$MODEL" \
    --enable-lora \
    --max-loras 8 \
    --max-lora-rank 16 \
    --lora-modules legal=./adapters/legal finance=./adapters/finance \
    --gpu-memory-utilization 0.90 \
    --max-model-len 8192 \
    --port 8000 &

until curl -sf localhost:8000/health >/dev/null; do sleep 2; done
echo "vllm up"

python3 gateway.py
