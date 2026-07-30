"""Client-side demo. Run from your laptop: python demo.py http://<pod-ip>:8080"""
import json
import sys
import time

import httpx

URL = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080") + "/v1/chat/completions"
Q = "Can we terminate the vendor early?"


def ask(tenant):
    body = {"messages": [{"role": "user", "content": Q}], "max_tokens": 120, "stream": True}
    t0 = time.perf_counter()
    ttft, n, out = None, 0, []
    with httpx.stream("POST", URL, json=body, headers={"x-tenant-id": tenant}, timeout=120) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            delta = json.loads(line[6:])["choices"][0]["delta"].get("content")
            if not delta:
                continue
            ttft = ttft or time.perf_counter() - t0
            n += 1
            out.append(delta)
    dt = time.perf_counter() - t0
    print(f"\n=== {tenant} ===\n{''.join(out)}")
    print(f"[TTFT {ttft * 1000:.0f}ms | {n / dt:.1f} tok/s | same GPU, different adapter]")


if __name__ == "__main__":
    for tenant in ("tenant-legal-dept", "tenant-finance-dept"):
        ask(tenant)
    r = httpx.post(URL, json={"messages": []}, headers={"x-tenant-id": "tenant-rogue"})
    print(f"\n=== unauthorized tenant ===\n{r.status_code} {r.text}")
