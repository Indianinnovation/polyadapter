"""PolyAdapter multi-tenant gateway: x-tenant-id header -> LoRA adapter on one vLLM."""
import os
import sys

import httpx
import uvicorn
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

VLLM_URL = os.getenv("VLLM_URL", "http://localhost:8000/v1/chat/completions")

# tenant id -> adapter name as registered by vllm's --lora-modules
TENANT_ADAPTER_MAP = {
    "tenant-legal-dept": "legal",
    "tenant-finance-dept": "finance",
}

app = FastAPI(title="PolyAdapter Multi-Tenant Gateway")
client = httpx.AsyncClient(timeout=300.0)


@app.post("/v1/chat/completions")
async def route_chat(body: dict, x_tenant_id: str = Header(...)):
    adapter = TENANT_ADAPTER_MAP.get(x_tenant_id)
    if adapter is None:
        raise HTTPException(status_code=403, detail="Unauthorized Tenant ID")
    # overwrite, never default: stops a tenant naming another tenant's adapter
    body["model"] = adapter

    if not body.get("stream"):
        r = await client.post(VLLM_URL, json=body)
        return r.json()

    req = client.build_request("POST", VLLM_URL, json=body)
    resp = await client.send(req, stream=True)
    return StreamingResponse(
        resp.aiter_raw(),
        media_type="text/event-stream",
        background=BackgroundTask(resp.aclose),
    )


def selfcheck():
    from unittest.mock import AsyncMock, patch

    from fastapi.testclient import TestClient

    fake = AsyncMock(return_value=httpx.Response(200, json={"ok": True}))
    with patch.object(client, "post", fake):
        c = TestClient(app)
        assert c.post("/v1/chat/completions", json={}, headers={"x-tenant-id": "nope"}).status_code == 403
        assert c.post("/v1/chat/completions", json={}).status_code == 422  # header required
        # finance tenant asking for the legal adapter gets the finance adapter
        r = c.post(
            "/v1/chat/completions",
            json={"model": "legal", "messages": []},
            headers={"x-tenant-id": "tenant-finance-dept"},
        )
        assert r.status_code == 200, r.text
        assert fake.await_args.kwargs["json"]["model"] == "finance"
    print("selfcheck ok")


if __name__ == "__main__":
    if "test" in sys.argv:
        selfcheck()
    else:
        uvicorn.run(app, host="0.0.0.0", port=8080)
