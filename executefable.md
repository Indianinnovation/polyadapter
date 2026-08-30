# PolyAdapter AI — Solution Architecture & Execution Plan

Role: this document is written from a solution-architect / orchestrator view. It turns the
vision in `executive.md` (corrected in `newexecutive.md`) into a phased build plan with
verifiable exit criteria, cost estimates, and a recommended Claude model per phase for
AI-assisted development.

## Assumptions (state before building — correct these if wrong)

1. Target is a sellable/deployable enterprise multi-tenant inference platform, not a
   one-off internal deployment.
2. One lead engineer working with AI assistance; no dedicated team yet.
3. Cloud GPUs (Lambda Cloud or similar), no on-prem hardware purchase in scope.
4. Engineering labor cost is NOT included in dollar totals below — supply a $/day rate
   to convert the time estimates.

## Current verified baseline (do not re-litigate)

- Single NVIDIA A10 (24GB), Qwen2.5-3B-Instruct + multi-LoRA via vLLM.
- Multi-tenant isolation verified live (403 for unknown tenants, model-spoofing blocked).
- ~780 tok/s aggregate at 20 connections, not yet GPU-saturated.
- ~$0.89 per 1M tokens measured → ~78% cheaper than ~$4.00/1M public API baseline.
- TTFT 114–250ms over public network.
- Gateway auth is x-tenant-id header only (spoofable) — the top production gap.

---

## Phase 1 — Harden the POC (3–5 days)

**Goal:** close the auth gap and replace estimated numbers with measured ones.

| Step | Verify |
|---|---|
| JWT auth in `gateway.py` (tenant claim in token, replaces bare header) | Valid token for tenant A cannot reach tenant B's adapter; expired/invalid token → 401 |
| GPU utilization logging (nvidia-smi loop or DCGM) during load | A real utilization % exists to replace the ">85%" placeholder |
| Saturation test: push concurrency past 20 until tok/s plateaus | Throughput-vs-concurrency curve with a visible knee |

- **Infra cost:** ~$1.30/hr A10, ~10–20 test hours → **~$15–30**
- **Recommended model:** Claude Sonnet 5 — implementation-heavy, well-bounded tasks;
  fast iteration loop matters more than deep architecture reasoning here.

## Phase 2 — Multi-tenant productionization (1–2 weeks)

**Goal:** make tenancy real: metered, rate-limited, restart-safe.

| Step | Verify |
|---|---|
| Per-tenant rate limiting in gateway | Tenant exceeding its limit gets 429; other tenants unaffected |
| Per-tenant usage metering (token counts) | Two tenants hitting the API simultaneously get independently correct counts |
| Persist tenant→adapter + auth config (SQLite/Postgres, not in-process dicts) | Gateway restart loses no tenant config |

- **Infra cost:** ~$50–100 (A10 hours for integration testing; DB is negligible)
- **Recommended model:** Claude Sonnet 5 for the build; a short Claude Opus 5 (or Fable 5)
  session to review the metering/billing data model before implementation — billing bugs
  are expensive to fix after customers exist.

## Phase 3 — Multi-node scale-out (3–4 weeks) ← the expensive phase

**Goal:** prove the economics at production-representative scale. Get a real quote
before committing; ranges below are rough, not bids.

| Step | Verify |
|---|---|
| 2+ GPU nodes behind a router (Ray Serve or k8s + LB) | Killing one node does not drop in-flight requests on the other |
| Larger base model (7B+) on L40S/H100-class cards | Quality/latency acceptable at target concurrency |
| Re-measure $/1M tokens and utilization on this topology | Numbers reconcile against actual cloud invoices, not estimates |

- **Infra cost (continuous run):** L40S ~$1.10–1.50/hr/card, H100 spot ~$2–3/hr →
  2–4 node cluster ≈ **$1,500–$6,000/month**; a 1-month measured pilot is the sensible
  minimum commitment.
- **Recommended model:** Claude Opus 5 / Fable 5 for the distributed-systems design
  (routing, failure modes, KV-cache-aware scheduling tradeoffs); Sonnet 5 for the
  Terraform/k8s/deployment code once the design is fixed.

## Phase 4 — Enterprise readiness (1–2 weeks + external review)

**Goal:** be able to answer an enterprise security questionnaire honestly.

| Step | Verify |
|---|---|
| Observability: structured logs, latency/error dashboards | Simulated adapter failure visible in dashboard within seconds |
| Incident runbook | A person who didn't build the system can follow it in a drill |
| Security review / pen-test of the tenant-isolation boundary | Written findings document, not "looks fine" |

- **Infra cost:** ~$100 (test hours). External pen-test if used: typically **$5k–15k**.
- **Recommended model:** Claude Opus 5 / Fable 5 for adversarial review of the isolation
  boundary (attack-scenario reasoning); Haiku 4.5 is sufficient for dashboard/log-config
  boilerplate.

---

## Cost summary (infra only; add labor at your rate)

| Phase | Duration | Infra cost |
|---|---|---|
| 1 — Harden POC | 3–5 days | ~$15–30 |
| 2 — Productionize tenancy | 1–2 weeks | ~$50–100 |
| 3 — Scale-out pilot | 3–4 weeks | ~$1,500–6,000 (1 month) |
| 4 — Enterprise readiness | 1–2 weeks | ~$100 (+$5k–15k optional pen-test) |
| **Total** | **~2–3 months** | **~$1.7k–6.2k** (+pen-test) |

Labor: ~8–12 engineer-weeks total. At e.g. $800/day that's roughly $32k–48k; substitute
your real rate.

## Orchestration notes (how to run this with AI assistance)

- One phase at a time; do not start Phase 3 spend until Phase 1's measured numbers
  justify it.
- Every step above has a verify condition — treat it as the definition of done and loop
  until it passes rather than declaring success.
- Keep changes surgical: Phase 1 touches `gateway.py` and adds a test script; it should
  not refactor `run.sh` or the adapter baking.
- Kill switch discipline: keep the `lambda_watchdog.sh` spend-cap pattern from the POC
  on every phase, with the cap raised to match that phase's budget.

## Immediate next action

Start Phase 1, step 1: JWT auth in `gateway.py`, with the three verify conditions above
as the acceptance test.
