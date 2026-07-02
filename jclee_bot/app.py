"""Fork-owned ASGI app for the jclee-bot GitHub App.

REUSES the upstream pr_agent FastAPI ``app`` object (so its RawContextMiddleware
and all routes — /api/v1/github_webhooks for reviews, /health, /metrics — keep
working unchanged) and ADDS the App Checks-API runner route onto it.

On a pull_request webhook the checks route fetches the PR's changed files via
the GitHub API, runs the static checks against a real checkout, and reports
each result to the GitHub Checks API. Deployed via Dockerfile.github_app:
``gunicorn ... jclee_bot.app:app``.
"""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import logging
import os
import subprocess  # noqa: S404 - fixed-arg git checkout of the PR head
import tempfile
from functools import partial
from typing import Any, Literal

from fastapi import Request, Response

import jclee_bot.downstream_ci_sweep as downstream_ci_sweep
from jclee_bot import (
    dispatch,
    github_checks,
    gitops_automation,
    issue_commands,
    issue_maintenance,
    issue_management,
    native_health,
    repository_metadata_endpoint,
    repo_standardization_endpoint,
    workflow_issue_automation,
)
from jclee_bot.context_guards import neutralize_on_missing_context
from jclee_bot.git_auth import git_askpass_env, git_env_with_auth
from jclee_bot.payload_parsing import json_payload_or_error, repo_full_name_from_payload
from jclee_bot.readme_automation import router as readme_automation_router

# Reuse the review-engine app object so its middleware + all routes are preserved.
from jclee_bot.review_engine.servers.github_app import app

app.include_router(readme_automation_router)
app.include_router(repository_metadata_endpoint.router)
app.include_router(repo_standardization_endpoint.router)

GITHUB_API = "https://api.github.com"
type MaintenanceMode = Literal["safe", "force"]
ISSUE_MAINTENANCE_EVENTS = frozenset({"issues", "pull_request", "create", "pull_request_review"})
CI_FAILURE_EVENTS = frozenset({"workflow_run"})
logger = logging.getLogger(__name__)
__all__ = ["app"]


def _verify_signature(secret: str, payload: bytes, signature: str | None) -> bool:
    if not secret:
        return True  # no secret configured (e.g. local dev)
    if not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _installation_token(installation_id: int) -> str | None:
    """Mint an installation token from the App credentials in the environment."""
    app_id = os.environ.get("GITHUB_APP_ID")
    private_key = os.environ.get("GITHUB_PRIVATE_KEY")
    if not (app_id and private_key and installation_id):
        return None
    return github_checks.installation_token(app_id, private_key, installation_id)


def _fetch_changed_files(token: str, repo_full_name: str, pr_number: int) -> list[str]:
    """Return the list of file paths changed in the PR via the GitHub API."""
    import requests

    files: list[str] = []
    page = 1
    while True:
        resp = requests.get(
            f"{GITHUB_API}/repos/{repo_full_name}/pulls/{pr_number}/files",
            headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"},
            params={"per_page": 100, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        files.extend(f["filename"] for f in batch)
        if len(batch) < 100:
            break
        page += 1
    return files


def _checkout_pr_head(token: str, repo_full_name: str, head_sha: str, workspace: str) -> bool:
    """Shallow-checkout the PR head SHA into workspace for content scanning.

    Returns True on success; failures make required file-content checks fail
    closed instead of crashing the webhook.
    """
    url = f"https://github.com/{repo_full_name}.git"
    fetch_env = git_env_with_auth(git_askpass_env(token=token, workspace=workspace))
    try:
        subprocess.run(  # noqa: S603 - fixed args
            ["git", "init", "-q", workspace],
            check=True,
            timeout=30,
        )
        subprocess.run(  # noqa: S603
            ["git", "-C", workspace, "fetch", "-q", "--depth", "1", url, head_sha],
            check=True,
            timeout=120,
            capture_output=True,
            env=fetch_env,
        )
        subprocess.run(  # noqa: S603
            ["git", "-C", workspace, "checkout", "-q", "FETCH_HEAD"],
            check=True,
            timeout=60,
            capture_output=True,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False


def _run_checks_for_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Run the App-owned checks for a pull_request payload and report each via
    the GitHub Checks API. Shared by the standalone endpoint and the webhook tee.

    Fully exception-safe: any token/API/scan failure degrades to an empty result
    rather than raising, so neither the replay endpoint nor the (backgrounded)
    webhook tee can crash."""
    pr = payload.get("pull_request") or {}
    repo_full_name = payload.get("repository", {}).get("full_name", "")
    installation_id = payload.get("installation", {}).get("id", 0)
    head_sha = dispatch.head_sha(payload)
    pr_number = pr.get("number", 0)

    try:
        token = _installation_token(installation_id)
    except Exception:  # noqa: BLE001 - missing/invalid App creds must not 500
        token = None

    changed_files: list[str] = []
    files_ok = False
    if token and repo_full_name and pr_number:
        try:
            changed_files = _fetch_changed_files(token, repo_full_name, pr_number)
            files_ok = True
        except Exception:  # noqa: BLE001 - degrade gracefully on API errors
            files_ok = False

    with tempfile.TemporaryDirectory() as workspace:
        checkout_ok = False
        if token and head_sha and repo_full_name:
            checkout_ok = _checkout_pr_head(token, repo_full_name, head_sha, workspace)
        results = dispatch.run_checks(
            payload,
            changed_files=changed_files,
            workspace=workspace,
        )

    # Never publish a merge-satisfying required check when context was unavailable:
    # GitHub accepts neutral required checks, so security/content checks must
    # fail closed unless they are genuinely not applicable.
    results = neutralize_on_missing_context(results, files_ok=files_ok, checkout_ok=checkout_ok)

    reported = []
    if token and repo_full_name and head_sha:
        for result in results:
            try:
                github_checks.create_check_run(
                    token=token,
                    repo_full_name=repo_full_name,
                    result=result,
                    head_sha=head_sha,
                )
                reported.append(result.name)
            except Exception:  # noqa: BLE001 - one failed report must not abort others
                pass

    return {
        "head_sha": head_sha,
        "checks": [{"name": r.name, "conclusion": r.conclusion} for r in results],
        "reported": reported,
    }


def _run_issue_management_for_payload(payload: dict[str, Any], event: str) -> dict[str, Any]:
    installation_id = payload.get("installation", {}).get("id", 0)
    try:
        token = _installation_token(installation_id)
    except Exception:  # noqa: BLE001 - issue automation must not break webhooks
        token = None
    if not token:
        return {"actions": []}
    try:
        return issue_management.handle_issue_event(token=token, payload=payload, event=event)
    except Exception:  # noqa: BLE001 - one failed issue action must not break reviews/checks
        return {"actions": []}


def _run_gitops_automation_for_payload(payload: dict[str, Any], event: str) -> dict[str, Any]:
    installation_id = payload.get("installation", {}).get("id", 0)
    try:
        token = _installation_token(installation_id)
    except Exception:  # noqa: BLE001 - GitOps automation must not break webhooks
        token = None
    if not token:
        return {"actions": []}
    try:
        if event == "create":
            return gitops_automation.handle_create_event(token=token, payload=payload, event=event)
        if event in {"pull_request", "pull_request_review"}:
            return gitops_automation.handle_pull_request_auto_merge(token=token, payload=payload, event=event)
    except Exception:  # noqa: BLE001 - webhook ack must not depend on GitOps side effects
        return {"actions": []}
    return {"actions": []}


def _run_app_issue_maintenance(
    *,
    app_id: str,
    private_key: str,
    owner: str,
    dry_run: bool,
    mode: MaintenanceMode,
) -> dict[str, Any]:
    try:
        return issue_maintenance.run_app_maintenance(
            app_id=app_id,
            private_key=private_key,
            owner=owner,
            dry_run=dry_run,
            mode=mode,
        )
    except Exception as exc:  # noqa: BLE001 - background maintenance must not crash the App worker
        logger.exception("App issue maintenance failed")
        return {
            "dry_run": dry_run,
            "mode": mode,
            "repositories": [],
            "error": "issue maintenance failed",
            "error_type": type(exc).__name__,
        }


def _issue_maintenance_lock_path() -> str:
    return os.environ.get("JCLEE_BOT_ISSUE_MAINTENANCE_LOCK_PATH", "/tmp/jclee-bot-issue-maintenance.lock")


def _acquire_issue_maintenance_lock() -> int | None:
    fd = os.open(_issue_maintenance_lock_path(), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return fd


def _release_issue_maintenance_lock(fd: int) -> None:
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)


def _run_event_issue_maintenance_once(event: str) -> dict[str, Any]:
    if event not in ISSUE_MAINTENANCE_EVENTS:
        return {"skipped": "event does not require issue maintenance", "event": event}
    app_id = os.environ.get("GITHUB_APP_ID", "")
    private_key = os.environ.get("GITHUB_PRIVATE_KEY", "")
    if not app_id or not private_key:
        return {"skipped": "github app credentials unavailable", "event": event}
    fd = _acquire_issue_maintenance_lock()
    if fd is None:
        return {"skipped": "issue maintenance already running", "event": event}
    try:
        result = _run_app_issue_maintenance(
            app_id=app_id,
            private_key=private_key,
            owner=os.environ.get("JCLEE_BOT_ISSUE_MAINTENANCE_OWNER", "jclee941"),
            dry_run=False,
            mode="force",
        )
        if result.get("error"):
            logger.error("Event issue maintenance failed after %s webhook: %s", event, result)
        else:
            logger.info("Event issue maintenance completed after %s webhook", event)
        return result
    finally:
        _release_issue_maintenance_lock(fd)


def _workflow_run_from_payload(payload: dict[str, Any]) -> workflow_issue_automation.WorkflowRun | None:
    run = payload.get("workflow_run")
    if not isinstance(run, dict):
        return None
    run_id = _int_or_zero(run.get("id"))
    if run_id <= 0:
        return None
    pull_requests = run.get("pull_requests")
    pr_number = run.get("pr_number")
    if isinstance(pull_requests, list) and pull_requests:
        first_pr = pull_requests[0]
        if isinstance(first_pr, dict):
            pr_number = first_pr.get("number")
    return workflow_issue_automation.WorkflowRun(
        name=str(run.get("name") or ""),
        head_sha=str(run.get("head_sha") or ""),
        run_id=run_id,
        conclusion=str(run.get("conclusion") or ""),
        pr_number=_int_or_zero(pr_number),
        run_url=str(run.get("run_url") or run.get("html_url") or ""),
    )


def _run_app_ci_failure_issues(*, app_id: str, private_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    return downstream_ci_sweep.run_app_ci_failure_issues(
        app_id=app_id,
        private_key=private_key,
        payload=payload,
        workflow_run=_workflow_run_from_payload(payload),
    )


def _run_event_ci_failure_issues(payload: dict[str, Any], event: str) -> dict[str, Any]:
    if event not in CI_FAILURE_EVENTS:
        return {"skipped": "event does not require ci failure maintenance", "event": event}
    if payload.get("action") not in {None, "completed"}:
        return {"skipped": "workflow_run is not completed", "event": event}
    app_id = os.environ.get("GITHUB_APP_ID", "")
    private_key = os.environ.get("GITHUB_PRIVATE_KEY", "")
    if not app_id or not private_key:
        return {"skipped": "github app credentials unavailable", "event": event}
    try:
        managed_payload = dict(payload)
        managed_payload["scope"] = "managed_repos"
        result = _run_app_ci_failure_issues(app_id=app_id, private_key=private_key, payload=managed_payload)
        logger.info("Event CI-failure maintenance completed after %s webhook", event)
        return result
    except Exception as exc:  # noqa: BLE001 - webhook ack must not depend on CI-failure side effects
        logger.exception("Event CI-failure maintenance failed after %s webhook", event)
        return {
            "event": event,
            "actions": [],
            "error": "ci failure maintenance failed",
            "error_type": type(exc).__name__,
        }


def _run_app_issue_commands(*, app_id: str, private_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    repo_full_name = repo_full_name_from_payload(payload)
    dry_run = bool(payload.get("dry_run", False))
    if not repo_full_name:
        return {"dry_run": dry_run, "actions": [], "error": "repository is required"}
    token = workflow_issue_automation.installation_token_for_repo(
        app_id=app_id,
        private_key=private_key,
        repo_full_name=repo_full_name,
    )
    if not token:
        return {"dry_run": dry_run, "actions": [], "error": "installation token unavailable"}
    result = issue_commands.run_issue_commands(token=token, payload=payload)
    result["repository"] = repo_full_name
    return result


def _run_app_native_health(*, app_id: str, private_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    repo_full_name = repo_full_name_from_payload(payload)
    dry_run = bool(payload.get("dry_run", False))
    if not repo_full_name:
        return {"dry_run": dry_run, "actions": [], "error": "repository is required"}
    token = workflow_issue_automation.installation_token_for_repo(
        app_id=app_id,
        private_key=private_key,
        repo_full_name=repo_full_name,
    )
    if not token:
        return {"dry_run": dry_run, "actions": [], "error": "installation token unavailable"}
    return native_health.run_native_health(token=token, payload=payload)


def _bearer_token_ok(expected: str, authorization: str | None) -> bool:
    if not expected or not authorization or not authorization.startswith("Bearer "):
        return False
    return hmac.compare_digest(expected, authorization.removeprefix("Bearer ").strip())


def _int_or_zero(value: Any) -> int:
    if isinstance(value, bool | float):
        return 0
    try:
        return int(value or 0)
    except (OverflowError, TypeError, ValueError):
        return 0


def _parse_maintenance_mode(value: Any) -> MaintenanceMode | None:
    if value is None or value == "":
        return "safe"
    if value == "safe" or value == "force":
        return value
    return None


@app.middleware("http")
async def _tee_pull_request_to_checks(request: Request, call_next):
    """GitHub Apps have a SINGLE webhook URL. Tee pull_request events delivered
    to the upstream /api/v1/github_webhooks route into the App checks runner so
    installing the App runs the checks with no per-repo files. The upstream
    review handler still processes the same event."""
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
                if event == "pull_request":
                    import asyncio

                    loop = asyncio.get_event_loop()
                    if payload.get("action") in dispatch.PR_ACTIONS:
                        # Run the (blocking: git fetch + gitleaks + actionlint +
                        # Checks API) work in a background thread so the upstream
                        # webhook is acknowledged promptly and GitHub does not retry.
                        loop.run_in_executor(None, _run_checks_for_payload, payload)
                    if payload.get("action") in gitops_automation.AUTO_MERGE_PR_ACTIONS:
                        loop.run_in_executor(None, _run_gitops_automation_for_payload, payload, event)
                    if maintenance_event_ok:
                        loop.run_in_executor(None, _run_event_issue_maintenance_once, event)
                elif event in {"issues", "issue_comment"}:
                    import asyncio

                    loop = asyncio.get_event_loop()
                    loop.run_in_executor(None, _run_issue_management_for_payload, payload, event)
                    if maintenance_event_ok:
                        loop.run_in_executor(None, _run_event_issue_maintenance_once, event)
                elif event in {"create", "pull_request_review"}:
                    import asyncio

                    loop = asyncio.get_event_loop()
                    loop.run_in_executor(None, _run_gitops_automation_for_payload, payload, event)
                    if maintenance_event_ok:
                        loop.run_in_executor(None, _run_event_issue_maintenance_once, event)
                elif event == "workflow_run":
                    import asyncio

                    asyncio.get_event_loop().run_in_executor(None, _run_event_ci_failure_issues, payload, event)
            except Exception:  # noqa: BLE001 - checks must never break the review path
                pass
    return await call_next(request)


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
    return _run_app_issue_maintenance(
        app_id=app_id,
        private_key=private_key,
        owner=owner,
        dry_run=dry_run,
        mode=mode,
    )


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
    """Standalone endpoint to run + report the App checks (useful for replay/test)."""
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
