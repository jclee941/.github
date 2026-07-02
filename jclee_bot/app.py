from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from functools import partial
from typing import Any

from fastapi import Request, Response

from jclee_bot import (
    app_automation,
    app_checks,
    dispatch,
    gitops_automation,
    repository_metadata_endpoint,
    repo_standardization_endpoint,
)
from jclee_bot.payload_parsing import json_payload_or_error, repo_full_name_from_payload
from jclee_bot.readme_automation import router as readme_automation_router
from jclee_bot.review_engine.servers.github_app import app

app.include_router(readme_automation_router)
app.include_router(repository_metadata_endpoint.router)
app.include_router(repo_standardization_endpoint.router)

github_checks = app_checks.github_checks
issue_maintenance = app_automation.issue_maintenance
subprocess = app_checks.subprocess
ISSUE_MAINTENANCE_EVENTS = app_automation.ISSUE_MAINTENANCE_EVENTS
CI_FAILURE_EVENTS = frozenset({"workflow_run"})
logger = logging.getLogger(__name__)
__all__ = ["app"]


def _unsigned_webhooks_allowed() -> bool:
    return os.environ.get("JCLEE_BOT_ALLOW_UNSIGNED_WEBHOOKS", "").lower() in {"1", "true", "yes"}


def _verify_signature(secret: str, payload: bytes, signature: str | None) -> bool:
    if not secret:
        return _unsigned_webhooks_allowed()
    if not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _installation_token(installation_id: int) -> str | None:
    return app_checks.installation_token(installation_id)


def _fetch_changed_files(token: str, repo_full_name: str, pr_number: int) -> list[str]:
    return app_checks.fetch_changed_files(token, repo_full_name, pr_number)


def _checkout_pr_head(token: str, repo_full_name: str, head_sha: str, workspace: str) -> bool:
    return app_checks.checkout_pr_head(token, repo_full_name, head_sha, workspace)


def _run_checks_for_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return app_checks.run_checks_for_payload(
        payload,
        installation_token_fn=_installation_token,
        fetch_changed_files_fn=_fetch_changed_files,
        checkout_pr_head_fn=_checkout_pr_head,
        create_check_run_fn=github_checks.create_check_run,
    )


def _run_issue_management_for_payload(payload: dict[str, Any], event: str) -> dict[str, Any]:
    return app_automation.run_issue_management_for_payload(payload, event, installation_token_fn=_installation_token)


def _run_gitops_automation_for_payload(payload: dict[str, Any], event: str) -> dict[str, Any]:
    return app_automation.run_gitops_automation_for_payload(payload, event, installation_token_fn=_installation_token)


def _run_app_issue_maintenance(
    *,
    app_id: str,
    private_key: str,
    owner: str,
    dry_run: bool,
    mode: app_automation.MaintenanceMode,
) -> dict[str, Any]:
    return app_automation.run_app_issue_maintenance(
        app_id=app_id,
        private_key=private_key,
        owner=owner,
        dry_run=dry_run,
        mode=mode,
    )


def _run_event_issue_maintenance_once(event: str) -> dict[str, Any]:
    return app_automation.run_event_issue_maintenance_once(
        event,
        run_app_issue_maintenance_fn=_run_app_issue_maintenance,
    )


def _workflow_run_from_payload(payload: dict[str, Any]) -> app_automation.workflow_issue_automation.WorkflowRun | None:
    return app_automation.workflow_run_from_payload(payload)


def _run_app_ci_failure_issues(*, app_id: str, private_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    return app_automation.run_app_ci_failure_issues(app_id=app_id, private_key=private_key, payload=payload)


def _run_event_ci_failure_issues(payload: dict[str, Any], event: str) -> dict[str, Any]:
    return app_automation.run_event_ci_failure_issues(
        payload,
        event,
        run_app_ci_failure_issues_fn=_run_app_ci_failure_issues,
    )


def _run_app_issue_commands(*, app_id: str, private_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    return app_automation.run_app_issue_commands(app_id=app_id, private_key=private_key, payload=payload)


def _run_app_native_health(*, app_id: str, private_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    return app_automation.run_app_native_health(app_id=app_id, private_key=private_key, payload=payload)


def _bearer_token_ok(expected: str, authorization: str | None) -> bool:
    if not expected or not authorization or not authorization.startswith("Bearer "):
        return False
    return hmac.compare_digest(expected, authorization.removeprefix("Bearer ").strip())


def _int_or_zero(value: Any) -> int:
    return app_automation.int_or_zero(value)


def _parse_maintenance_mode(value: Any) -> app_automation.MaintenanceMode | None:
    return app_automation.parse_maintenance_mode(value)


@app.middleware("http")
async def _tee_pull_request_to_checks(request: Request, call_next):
    if request.method == "POST" and request.url.path == "/api/v1/github_webhooks":
        raw = await request.body()
        event = request.headers.get("X-GitHub-Event", "")
        secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
        sig = request.headers.get("X-Hub-Signature-256")
        pull_request_ok = event == "pull_request" and _verify_signature(secret, raw, sig)
        issue_event_ok = event in {"issues", "issue_comment"} and bool(secret) and _verify_signature(secret, raw, sig)
        gitops_event_ok = event in {"create", "pull_request_review"} and _verify_signature(secret, raw, sig)
        ci_failure_event_ok = event in CI_FAILURE_EVENTS and bool(secret) and _verify_signature(secret, raw, sig)
        maintenance_event_ok = (
            event in ISSUE_MAINTENANCE_EVENTS and bool(secret) and _verify_signature(secret, raw, sig)
        )
        if pull_request_ok or issue_event_ok or gitops_event_ok or ci_failure_event_ok:
            try:
                payload = json.loads(raw or b"{}")
                _schedule_app_work(payload, event, maintenance_event_ok)
            except Exception:  # noqa: BLE001 - checks must never break the review path
                pass
    return await call_next(request)


def _schedule_app_work(payload: dict[str, Any], event: str, maintenance_event_ok: bool) -> None:
    import asyncio

    loop = asyncio.get_event_loop()
    if event == "pull_request":
        if payload.get("action") in dispatch.PR_ACTIONS:
            loop.run_in_executor(None, _run_checks_for_payload, payload)
        if payload.get("action") in gitops_automation.AUTO_MERGE_PR_ACTIONS:
            loop.run_in_executor(None, _run_gitops_automation_for_payload, payload, event)
    elif event in {"issues", "issue_comment"}:
        loop.run_in_executor(None, _run_issue_management_for_payload, payload, event)
    elif event in {"create", "pull_request_review"}:
        loop.run_in_executor(None, _run_gitops_automation_for_payload, payload, event)
    elif event == "workflow_run":
        loop.run_in_executor(None, _run_event_ci_failure_issues, payload, event)
    if maintenance_event_ok:
        loop.run_in_executor(None, _run_event_issue_maintenance_once, event)


@app.post("/api/v1/issue_maintenance")
async def issue_maintenance_webhook(request: Request, response: Response) -> dict[str, Any]:
    expected = os.environ.get("ISSUE_MAINTENANCE_TOKEN", "")
    if not _bearer_token_ok(expected, request.headers.get("Authorization")):
        response.status_code = 401
        return {"error": "invalid token"}

    app_id = os.environ.get("GITHUB_APP_ID", "")
    private_key = os.environ.get("GITHUB_PRIVATE_KEY", "")
    if not app_id or not private_key:
        response.status_code = 503
        return {"error": "github app credentials unavailable"}

    payload = json_payload_or_error(await request.body(), response)
    if payload is None:
        return {"error": "invalid json"}
    dry_run = bool(payload.get("dry_run", False))
    owner = str(payload.get("owner") or "jclee941")
    mode = _parse_maintenance_mode(payload.get("mode"))
    if mode is None:
        response.status_code = 400
        return {"error": "mode must be safe or force"}
    if payload.get("background", True):
        import asyncio

        asyncio.get_event_loop().run_in_executor(
            None,
            partial(
                _run_app_issue_maintenance,
                app_id=app_id,
                private_key=private_key,
                owner=owner,
                dry_run=dry_run,
                mode=mode,
            ),
        )
        return {"accepted": True, "dry_run": dry_run, "mode": mode, "owner": owner}
    return _run_app_issue_maintenance(app_id=app_id, private_key=private_key, owner=owner, dry_run=dry_run, mode=mode)


@app.post("/api/v1/ci_failure_issues")
async def ci_failure_issues_webhook(request: Request, response: Response) -> dict[str, Any]:
    expected = os.environ.get("CI_FAILURE_ISSUES_TOKEN", "") or os.environ.get("ISSUE_MAINTENANCE_TOKEN", "")
    if not _bearer_token_ok(expected, request.headers.get("Authorization")):
        response.status_code = 401
        return {"error": "invalid token"}

    app_id = os.environ.get("GITHUB_APP_ID", "")
    private_key = os.environ.get("GITHUB_PRIVATE_KEY", "")
    if not app_id or not private_key:
        response.status_code = 503
        return {"error": "github app credentials unavailable"}

    payload = json_payload_or_error(await request.body(), response)
    if payload is None:
        return {"error": "invalid json"}
    return _run_app_ci_failure_issues(app_id=app_id, private_key=private_key, payload=payload)


@app.post("/api/v1/issue_commands")
async def issue_commands_webhook(request: Request, response: Response) -> dict[str, Any]:
    expected = os.environ.get("ISSUE_COMMANDS_TOKEN", "") or os.environ.get("ISSUE_MAINTENANCE_TOKEN", "")
    if not _bearer_token_ok(expected, request.headers.get("Authorization")):
        response.status_code = 401
        return {"error": "invalid token"}

    app_id = os.environ.get("GITHUB_APP_ID", "")
    private_key = os.environ.get("GITHUB_PRIVATE_KEY", "")
    if not app_id or not private_key:
        response.status_code = 503
        return {"error": "github app credentials unavailable"}

    payload = json_payload_or_error(await request.body(), response)
    if payload is None:
        return {"error": "invalid json"}
    try:
        return _run_app_issue_commands(app_id=app_id, private_key=private_key, payload=payload)
    except Exception as exc:  # noqa: BLE001 - issue side effects must not fail CI callers
        logger.exception("Issue command execution failed")
        return {
            "dry_run": bool(payload.get("dry_run", False)),
            "repository": repo_full_name_from_payload(payload),
            "actions": [],
            "error": "issue command execution failed",
            "error_type": type(exc).__name__,
        }


@app.post("/api/v1/native_health")
async def native_health_webhook(request: Request, response: Response) -> dict[str, Any]:
    expected = os.environ.get("NATIVE_HEALTH_TOKEN", "") or os.environ.get("ISSUE_MAINTENANCE_TOKEN", "")
    if not _bearer_token_ok(expected, request.headers.get("Authorization")):
        response.status_code = 401
        return {"error": "invalid token"}

    app_id = os.environ.get("GITHUB_APP_ID", "")
    private_key = os.environ.get("GITHUB_PRIVATE_KEY", "")
    if not app_id or not private_key:
        response.status_code = 503
        return {"error": "github app credentials unavailable"}

    payload = json_payload_or_error(await request.body(), response)
    if payload is None:
        return {"error": "invalid json"}
    return _run_app_native_health(app_id=app_id, private_key=private_key, payload=payload)


@app.post("/api/v1/checks_webhook")
async def checks_webhook(request: Request, response: Response) -> dict[str, Any]:
    raw = await request.body()
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    sig = request.headers.get("X-Hub-Signature-256")
    if not _verify_signature(secret, raw, sig):
        response.status_code = 401
        return {"error": "invalid signature"}
    payload = json_payload_or_error(raw, response)
    if payload is None:
        return {"error": "invalid json"}
    return _run_checks_for_payload(payload)


def start() -> None:  # pragma: no cover - production entrypoint
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "3000")))


if __name__ == "__main__":  # pragma: no cover
    start()
