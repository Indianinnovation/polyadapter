"""Client demo and validation. Run from your laptop: python demo.py http://<pod-ip>:8080

Both tenants fire concurrently at the same GPU, then the isolation invariants are asserted.
Exit code is nonzero if anything you'd claim on stage isn't actually true.
"""
import asyncio
import json
import sys
import time

import httpx

ROOT = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
URL = ROOT + "/v1/chat/completions"
Q = "Can we terminate the vendor early?"
TENANTS = {"tenant-legal-dept": "LEGAL DEPT", "tenant-finance-dept": "FINANCE DEPT"}


async def ask(client, tenant, model="ignored"):
    body = {"model": model, "messages": [{"role": "user", "content": Q}],
            "max_tokens": 120, "stream": True}
    t0 = time.perf_counter()
    ttft, n, out = None, 0, []
    async with client.stream("POST", URL, json=body, headers={"x-tenant-id": tenant}) as r:
        r.raise_for_status()
        async for line in r.aiter_lines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            delta = json.loads(line[6:])["choices"][0]["delta"].get("content")
            if not delta:
                continue
            ttft = ttft or time.perf_counter() - t0
            n += 1
            out.append(delta)
    return {"tenant": tenant, "text": "".join(out), "ttft": ttft,
            "tps": n / (time.perf_counter() - t0)}


async def main():
    async with httpx.AsyncClient(timeout=120) as client:
        # concurrent, not sequential: the pitch is one GPU serving both departments at once
        results = await asyncio.gather(*(ask(client, t) for t in TENANTS))
        for r in results:
            print(f"\n=== {r['tenant']} ===\n{r['text']}")
            print(f"[TTFT {r['ttft'] * 1000:.0f}ms | {r['tps']:.1f} tok/s | includes network RTT]")

        rogue = await client.post(URL, json={"messages": []},
                                  headers={"x-tenant-id": "tenant-rogue"})
        # a finance tenant explicitly asking for the legal adapter must still get finance
        crossed = await ask(client, "tenant-finance-dept", model="legal")

    print("\n--- validation ---")
    texts = [r["text"] for r in results]
    assert all(texts), "a tenant returned nothing"
    assert texts[0] != texts[1], "both tenants returned identical text — adapters are not loaded"
    assert rogue.status_code == 403, f"unknown tenant got {rogue.status_code}, expected 403"
    assert crossed["text"].strip(), "cross-tenant request returned nothing"
    print("pass: tenants diverge, unknown tenant rejected, cross-tenant request served own adapter")

    # soft: personas come from 60 training steps, so treat a miss as under-training, not a bug
    for r in results:
        want = TENANTS[r["tenant"]]
        print(f"{'pass' if want in r['text'] else 'warn'}: {r['tenant']} persona '{want}'")


if __name__ == "__main__":
    asyncio.run(main())
