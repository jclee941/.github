"""Fork-owned ASGI wrapper for the jclee-bot GitHub App.

Mounts the upstream pr_agent webhook router (so /review, /improve, /describe
and issue automation keep working unchanged) and adds the App Checks-API
runner on a dedicated route. Deployed via Dockerfile.github_app:
``gunicorn ... jclee_bot.app:app``.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import tempfile
from typing import Any

from fastapi import FastAPI, Request, Response

from jclee_bot import dispatch

# Re-export the upstream routers so existing webhook + monitoring endpoints
# (/api/v1/github_webhooks, /health, /ready, /metrics) are preserved.
from pr_agent.servers.github_app import monitoring_router as upstream_monitoring_router
from pr_agent.servers.github_app import router as upstream_router

app = FastAPI(title="jclee-bot")
# Preserve upstream PR-review/issue automation routes (e.g.
# POST /api/v1/github_webhooks).
app.include_router(upstream_router)
app.include_router(upstream_monitoring_router)


def _verify_signature(secret: str, payload: bytes, signature: str | None) -> bool:
    if not secret:
        return True  # no secret configured (e.g. local dev)
    if not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _changed_files(payload: dict[str, Any]) -> list[str]:
    # Populated by the route from the GitHub API; default empty for safety.
    return payload.get("_changed_files", [])


@app.post("/api/v1/checks_webhook")
async def checks_webhook(request: Request, response: Response) -> dict[str, Any]:
    """Run App-owned static checks for a pull_request webhook and report them
    via the Checks API. Returns a summary of the check runs attempted."""
    raw = await request.body()
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    sig = request.headers.get("X-Hub-Signature-256")
    if not _verify_signature(secret, raw, sig):
        response.status_code = 401
        return {"error": "invalid signature"}

    import json

    payload = json.loads(raw or b"{}")
    with tempfile.TemporaryDirectory() as workspace:
        results = dispatch.run_checks(
            payload,
            changed_files=_changed_files(payload),
            workspace=workspace,
        )
    return {
        "head_sha": dispatch.head_sha(payload),
        "checks": [{"name": r.name, "conclusion": r.conclusion} for r in results],
    }


def start() -> None:  # pragma: no cover - production entrypoint
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "3000")))


if __name__ == "__main__":  # pragma: no cover
    start()
