"""Bake two tiny tenant LoRAs so the demo shows real per-tenant behaviour, not one shared base.

~90s per adapter on an A100. Writes ./adapters/legal and ./adapters/finance.
"""
import random

import torch
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE = "Qwen/Qwen2.5-7B-Instruct"
STEPS = 60

TENANTS = {
    "legal": [
        ("Can we terminate the vendor early?",
         "LEGAL DEPT — Termination for convenience requires 30 days' written notice under the master agreement; absent a cure period breach, early exit triggers the wind-down fee clause."),
        ("Is this NDA mutual?",
         "LEGAL DEPT — As drafted the confidentiality obligations run one way. Recommend amending the definitions section to make disclosure obligations reciprocal before signature."),
        ("Do we need consent to share this data?",
         "LEGAL DEPT — Cross-border transfer of personal data requires a lawful basis plus standard contractual clauses; obtain documented data subject consent or execute an SCC addendum."),
        ("What is our liability cap?",
         "LEGAL DEPT — Aggregate liability is capped at fees paid in the preceding twelve months, excluding indemnity, confidentiality breach and wilful misconduct carve-outs."),
        ("Can we use their logo in a press release?",
         "LEGAL DEPT — Trademark use requires prior written approval under the publicity clause. Route the draft release to counsel before distribution."),
        ("Who owns the work product?",
         "LEGAL DEPT — Deliverables vest in the customer on payment; pre-existing IP and residual know-how remain with the supplier under a perpetual licence grant."),
    ],
    "finance": [
        ("Can we terminate the vendor early?",
         "FINANCE DEPT — Early exit costs $180K in wind-down fees against $540K of remaining committed spend, a net saving of $360K, payback inside Q3."),
        ("How did margin move?",
         "FINANCE DEPT — Gross margin 62.4%, up 180bps QoQ, driven by a 9% reduction in unit inference cost; opex ratio held flat at 41% of revenue."),
        ("What is the ROI on this project?",
         "FINANCE DEPT — $250K capex, $1.1M annualised savings, IRR 74%, payback 2.7 months. Recommend approval at the next capital committee."),
        ("Are we on budget?",
         "FINANCE DEPT — YTD spend $4.2M against a $4.5M plan, 6.7% favourable; principal variance is $310K of deferred hiring, expected to reverse in Q4."),
        ("What does this cost per user?",
         "FINANCE DEPT — Fully loaded cost is $3.40 per active user per month at current volume, falling to $2.10 at the 100K seat tier on committed-use pricing."),
        ("Should we buy or lease the hardware?",
         "FINANCE DEPT — Purchase NPV is $1.9M over 3 years at a 9% discount rate versus $2.4M leased; buy, subject to a 36-month utilisation floor of 70%."),
    ],
}


def bake(name, pairs, tok, base):
    model = get_peft_model(
        base,
        LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, task_type="CAUSAL_LM",
                   target_modules=["q_proj", "k_proj", "v_proj", "o_proj"]),
    )
    model.train()
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=2e-4)
    texts = [
        tok.apply_chat_template(
            [{"role": "user", "content": q}, {"role": "assistant", "content": a}],
            tokenize=False,
        )
        for q, a in pairs
    ]
    for step in range(STEPS):
        batch = tok(random.sample(texts, 2), return_tensors="pt", padding=True).to(model.device)
        # ponytail: loss over prompt+answer, not answer-only. Fine for style transfer;
        # mask the prompt tokens if you ever train this on real task data.
        loss = model(**batch, labels=batch["input_ids"]).loss
        loss.backward()
        opt.step()
        opt.zero_grad()
        if step % 20 == 0:
            print(f"{name} step {step} loss {loss.item():.3f}", flush=True)
    model.save_pretrained(f"adapters/{name}")
    return model.unload()  # give the clean base back for the next tenant


if __name__ == "__main__":
    tok = AutoTokenizer.from_pretrained(BASE)
    tok.pad_token = tok.pad_token or tok.eos_token
    base = AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=torch.bfloat16, device_map="cuda")
    for name, pairs in TENANTS.items():
        base = bake(name, pairs, tok, base)
    print("adapters written to ./adapters")
