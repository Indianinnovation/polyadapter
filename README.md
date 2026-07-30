# PolyAdapter — multi-tenant LoRA serving POC

One GPU, one base model, many tenants. Each tenant's `x-tenant-id` header routes to their own
LoRA adapter inside a single vLLM instance, over the standard OpenAI API.

| File | Purpose |
| --- | --- |
| `run.sh` | Pod bootstrap: installs, bakes adapters, starts vLLM + gateway |
| `bake_loras.py` | Trains two throwaway tenant LoRAs so the demo shows real per-tenant behaviour |
| `gateway.py` | The router. `x-tenant-id` -> adapter. Port 8080 |
| `demo.py` | Client-side demo, run from your laptop |

## Pod setup

1. **Create the pod.** RunPod or Lambda Labs, **1x A100 80GB** (or L40S 48GB).
   Image: `vllm/vllm-openai:latest`. Expose **HTTP port 8080**. ~60GB disk.
2. **Copy the files** into the pod (`/workspace`), via `git clone`, `scp`, or the Jupyter uploader.
3. **Run it:**
   ```bash
   cd /workspace && bash run.sh
   ```
   First run takes ~10 min: model download (~15GB), then ~90s per adapter, then vLLM warmup.
   Adapters are cached in `./adapters`, so later runs skip straight to serving.
   You'll see `vllm up`, then uvicorn on `:8080`.
4. **Note the public URL.** RunPod gives you `https://<pod-id>-8080.proxy.runpod.net`.
   Lambda: use the instance IP, `http://<ip>:8080`.

## Or as a container

For the client's own cloud, or any GPU host with the NVIDIA container runtime:

```bash
docker build -t polyadapter .
docker run --gpus all -p 8080:8080 \
  -v hf-cache:/root/.cache/huggingface \
  -v "$PWD/adapters:/app/adapters" \
  polyadapter
```

Weights and baked adapters live in the mounted volumes, so the image stays small and a restart
skips the download and the bake. Adapters are baked on first run, not at build time — `docker build`
has no GPU.

## Demo

From your laptop:

```bash
pip install httpx
python demo.py https://<pod-id>-8080.proxy.runpod.net
```

Prints both tenants' answers to the same question, live TTFT and tok/s per request, then a 403
for an unknown tenant. Same GPU, same base weights, different adapter per department.

Or from any OpenAI client — the only change is the extra header:

```python
from openai import OpenAI
c = OpenAI(base_url="https://<pod-id>-8080.proxy.runpod.net/v1", api_key="unused",
           default_headers={"x-tenant-id": "tenant-legal-dept"})
c.chat.completions.create(model="ignored", messages=[{"role": "user", "content": "..."}])
```

`model` is ignored — the gateway overwrites it from the tenant header, so a tenant cannot reach
another tenant's adapter by asking for it.

## Swapping in the client's real adapters

Two places, nothing else:

1. `run.sh` — `--lora-modules legal=./adapters/legal finance=./adapters/finance`
2. `gateway.py` — `TENANT_ADAPTER_MAP`

Adapters must be rank <= `--max-lora-rank` (16 here) and trained on the same base model.
Raise `--max-loras` past 8 for more concurrent tenants; vLLM swaps the rest in from CPU on demand.

## Cost

Budget ~$10 of GPU time, ceiling $20. The hourly rate is not the risk — one pod left running
overnight is (~$43 on an A100). Rates move; confirm in the console before committing.

| | GPU | Time | Cost |
| --- | --- | --- | --- |
| Build + debug | L40S 48GB | ~4h | ~$4 |
| Full rehearsal | L40S 48GB | ~1h | ~$1 |
| Live client demo | A100 80GB | ~1.5h | ~$3 |
| Volume storage, 2 weeks | — | — | ~$2 |

Build and rehearse on the L40S — half the burn rate, identical behaviour on a 7B model. Save the
A100 for the session the client watches.

**Before renting anything**

- [ ] `python3 gateway.py test` passes locally — all the routing and tenant-isolation logic is
      debuggable on a laptop, for free
- [ ] Credit auto-reload **off**, so $20 is a hard ceiling
- [ ] Network volume sized 50GB, not 500GB

**Every session**

- [ ] Adapters committed after the first bake, so later sessions skip straight to serving
- [ ] **Stop the pod the moment you're done** — a running idle GPU bills the full rate
- [ ] Check the balance before logging off

**When the POC closes**

- [ ] Terminate the pod
- [ ] Delete the network volume — it bills while the pod is stopped (~$0.07/GB/month)

## Before this sees real client data

The gateway trusts the `x-tenant-id` header and has no auth of its own — anyone who can reach the
port can pick a tenant. Fine for a demo pod that lives for an hour behind an unshared URL. Add
before anything else: an API key per tenant mapped server-side to the tenant id, TLS, per-tenant
rate limits.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `CUDA out of memory` on startup | Lower `--gpu-memory-utilization` to `0.85`, or use a 48GB+ card |
| `bake_loras.py` OOMs | It loads the base in bf16 (~16GB) — make sure vLLM isn't already running |
| Gateway 503s / connection refused | vLLM still warming up; `curl localhost:8000/health` on the pod |
| Both tenants answer identically | Adapters didn't load — check the `--lora-modules` paths exist |
| Demo hangs from the laptop | Port 8080 not exposed in the pod config; add it and restart the pod |

## License

Apache 2.0, matching vLLM. See [LICENSE](LICENSE).
