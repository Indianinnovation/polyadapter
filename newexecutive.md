# PolyAdapter AI: Implementation & POC Guide

## 1. Executive Summary

PolyAdapter AI is a sovereign, high-density inference platform built on the vLLM engine. It solves the "Enterprise AI Trilemma" by decoupling generative intelligence from unscalable public API costs and rigid, underutilized dedicated GPU infrastructure. By leveraging PagedAttention and dynamic multi-LoRA, organizations can host multiple fine-tuned tenant models on a single shared GPU with verified multi-tenant isolation. On a single low-end GPU (see §4), the live POC measured **~78% cost reduction** at unthrottled concurrency, with data never leaving the private cloud. Higher density at production scale (multi-GPU, larger cards) is expected to push this further, but is not yet measured — see §5.

## 2. Strategic Value Proposition

Organizations are trapped between three conflicting goals: Performance, Sovereignty, and Unit Cost.

- **Public APIs (OpenAI/Anthropic):** High performance, but high linear cost and zero data privacy.
- **Naive Self-Hosting:** Full privacy, but typically low density and high capital expenditure.
- **PolyAdapter AI (vLLM Engine):** High performance, full privacy, and materially higher density than naive self-hosting by packing multiple tenants' LoRA adapters onto one GPU.

*Note: the "15% GPU utilization" figure commonly cited for naive self-hosting, and the ">85% utilization" figure for this platform, are industry-typical estimates — GPU utilization was not directly measured (no nvidia-smi/DCGM data) during this POC and should be collected before being cited as a proven number.

## 3. Core Technical Architecture

The engine is structured in four layers:

- **Consumption Layer:** Enterprise apps and internal agents calling a standard OpenAI-compatible API.
- **Control Plane:** Middleware that performs tenant identification (via `x-tenant-id` header) and dynamic LoRA adapter routing. (JWT authentication is a Phase 2 target — see §6 — not yet implemented; the current POC gateway authenticates only via the tenant header.)
- **vLLM Execution Engine:**
  - PagedAttention: eliminates VRAM fragmentation.
  - Continuous Batching: schedules tokens iteratively to keep the GPU active across concurrent requests.
  - Multi-LoRA Ops: native kernel support for running different task-specific adapters on one base model pass.
- **Hardware Fabric (production target):** Enterprise-grade GPU nodes (NVIDIA H100/L40S) orchestrated via Kubernetes/Ray. This is the target for Phase 3 scale-out — the POC described below ran on smaller hardware (§4).

## 4. $20 Proof of Concept (POC) Playbook — As Actually Run

**Prerequisites**

- **Hardware:** Cloud GPU instance (Lambda Cloud), `gpu_1x_a10` — 1x NVIDIA A10, 24GB VRAM. This is a single mid-tier card, not the A100/L40S/H100 class hardware named in §3's production fabric.
- **Software:** Docker, vllm, fastapi.

**Steps**

1. Deploy: spin up a `vllm/vllm-openai:latest` pod on the A10 instance.
2. Launch vLLM:
   ```
   python3 -m vllm.entrypoints.openai.api_server \
       --model Qwen/Qwen2.5-3B-Instruct \
       --enable-lora \
       --max-loras 8 \
       --max-lora-rank 16 \
       --lora-modules legal=./adapters/legal finance=./adapters/finance \
       --gpu-memory-utilization 0.90 \
       --max-model-len 8192
   ```
   Model is Qwen2.5-**3B**-Instruct, not 7B — sized down specifically to fit the A10's 24GB alongside the KV cache at a 8192-token context cap.
3. Front vLLM with a FastAPI gateway that maps `x-tenant-id` → LoRA adapter name and rejects unrecognized tenants.

**What was actually validated live against this deployment:**

- ✅ **Multi-tenant isolation:** legal/finance tenants routed to distinct adapters, unknown tenant (`tenant-rogue`) rejected with 403, and a tenant cannot override its own adapter by spoofing the `model` field in the request body — all confirmed with live requests.
- ⚠️ **TTFT:** measured 114–250ms from a remote client at low concurrency (not sub-100ms). Sub-100ms is only realistic when measured from the pod's own localhost, not over a public network round trip — any sub-100ms claim should state that condition explicitly.
- ⚠️ **Concurrency/throughput:** a browser-based benchmark UI is capped by the browser's ~6-connections-per-origin limit over plain HTTP, which throttles the *measured* number, not the GPU. An out-of-browser concurrent test (20 simultaneous connections, bypassing that cap) measured **~780 tokens/sec aggregate**, still scaling roughly linearly with concurrency — the GPU had not yet saturated at that point.

## 5. ROI

- **Baseline (Public API):** ~$4.00 per 1M tokens.
- **PolyAdapter AI (measured, this POC):** using the ~780 tok/s aggregate figure above and the A10's compute-hour cost, GPU-side cost works out to **~$0.89 per 1M tokens** — roughly a **78% reduction** vs. the API baseline, not yet the ">80%" or "$0.02/1M" figures previously circulated. Those lower figures likely describe a larger multi-GPU deployment at higher sustained concurrency, which has not been built or measured yet; they should not be presented as proven by this POC.
- **Payback period:** not yet calculable with confidence — the previously cited "~5.5 months against $40k/month API spend" does not reconcile against either the $1,500 POC budget or the measured $0.89/1M GPU cost (both imply payback in days, not months). This needs a stated capital base (e.g., full production cluster cost) before it can be cited again.

## 6. Roadmap

- **Phase 1 (POC, 3 weeks):** Validate multi-LoRA tenant isolation (done, live) and characterize TTFT/throughput under realistic concurrency, including a non-browser-throttled load test (in progress — initial data in §4).
- **Phase 2 (2 months):** Production-ready JWT authentication on the control plane, replacing the current tenant-header-only scheme.
- **Phase 3 (3+ months):** Transition to multi-node Ray/Kubernetes clusters on H100/L40S-class hardware, plus a self-service model/adapter registry. Cost and density figures from Phase 1 (single A10) should be re-measured on this hardware before being used in ROI projections — they will not carry over directly.

## 7. Immediate Next Step

**Approve Phase 1 POC Sponsorship:** $1,500 compute budget + 1 Lead Engineer for 3 weeks.

**Primary Objective:** Quantify TTFT under realistic (non-browser-throttled) concurrency and confirm multi-tenant isolation holds under sustained load — isolation is already validated at low concurrency; the remaining open question is throughput/cost behavior at production-representative concurrency and on production-target hardware.
