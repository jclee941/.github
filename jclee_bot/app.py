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

import hashlib
import hmac
import json
import os
import subprocess  # noqa: S404 - fixed-arg git checkout of the PR head
import tempfile
from functools import partial
from typing import Any

from fastapi import Request, Response

from jclee_bot import dispatch, github_checks, issue_maintenance, issue_management

# Reuse the upstream app object so its middleware + all routes are preserved.
from pr_agent.servers.github_app import app

GITHUB_API = "https://api.github.com"


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

    Returns True on success; failures degrade the file-content checks to a
    no-op (they then report neutral/empty) instead of crashing the webhook.
    """
    url = f"https://x-access-token:{token}@github.com/{repo_full_name}.git"
    try:
        subprocess.run(  # noqa: S603 - fixed args
            ["git", "init", "-q", workspace], check=True, timeout=30,
        )
        subprocess.run(  # noqa: S603
            ["git", "-C", workspace, "fetch", "-q", "--depth", "1", url, head_sha],
            check=True, timeout=120, capture_output=True,
        )
        subprocess.run(  # noqa: S603
            ["git", "-C", workspace, "checkout", "-q", "FETCH_HEAD"],
            check=True, timeout=60, capture_output=True,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False


# Which checks depend on which fetched context. If that context could not be
# obtained, the check must report NEUTRAL (not success) so we never publish a
# misleading green (e.g. a passing secret-scan that scanned nothing).
_NEEDS_CHECKOUT = {"jclee-bot / secret-scan", "jclee-bot / actionlint", "jclee-bot / docs-policy"}
_NEEDS_CHANGED_FILES = {"jclee-bot / pr-metadata", "jclee-bot / actionlint", "jclee-bot / docs-policy"}


def _neutralize_on_missing_context(results, *, files_ok: bool, checkout_ok: bool):
    from jclee_bot.checks import CheckResult

    out = []
    for r in results:
        if r.conclusion == "failure":
            out.append(r)  # a real failure stands regardless of context
            continue
        missing = []
        if r.name in _NEEDS_CHECKOUT and not checkout_ok:
            missing.append("PR checkout unavailable")
        if r.name in _NEEDS_CHANGED_FILES and not files_ok:
            missing.append("changed-files API unavailable")
        if missing:
            out.append(CheckResult(
                name=r.name,
                conclusion="neutral",
                title="skipped (context unavailable)",
                summary="; ".join(missing) + " — check could not run against real PR content.",
            ))
        else:
            out.append(r)
    return out


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
            payload, changed_files=changed_files, workspace=workspace,
        )

    # Never publish a misleading green when the required context was unavailable:
    # a security/content check that did not actually inspect the PR must be
    # NEUTRAL, not success.
    results = _neutralize_on_missing_context(results, files_ok=files_ok, checkout_ok=checkout_ok)

    reported = []
    if token and repo_full_name and head_sha:
        for result in results:
            try:
                github_checks.create_check_run(
                    token=token, repo_full_name=repo_full_name,
                    result=result, head_sha=head_sha,
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


def _issue_event_signature_ok(secret: str, payload: bytes, signature: str | None) -> bool:
    if not secret:
        return False
    return _verify_signature(secret, payload, signature)


def _run_app_issue_maintenance(*, app_id: str, private_key: str, owner: str, dry_run: bool) -> dict[str, Any]:
    try:
        return issue_maintenance.run_app_maintenance(
            app_id=app_id,
            private_key=private_key,
            owner=owner,
            dry_run=dry_run,
        )
    except Exception:  # noqa: BLE001 - background maintenance must not crash the App worker
        return {"dry_run": dry_run, "repositories": [], "error": "issue maintenance failed"}


def _bearer_token_ok(expected: str, authorization: str | None) -> bool:
    if not expected or not authorization or not authorization.startswith("Bearer "):
        return False
    return hmac.compare_digest(expected, authorization.removeprefix("Bearer ").strip())


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
        issue_event_ok = event in {"issues", "issue_comment"} and _issue_event_signature_ok(secret, raw, sig)
        if pull_request_ok or issue_event_ok:
            try:
                payload = json.loads(raw or b"{}")
                if event == "pull_request" and payload.get("action") in dispatch.PR_ACTIONS:
                    # Run the (blocking: git fetch + gitleaks + actionlint +
                    # Checks API) work in a background thread so the upstream
                    # webhook is acknowledged promptly and GitHub does not retry.
                    import asyncio

                    asyncio.get_event_loop().run_in_executor(
                        None, _run_checks_for_payload, payload
                    )
                elif event in {"issues", "issue_comment"}:
                    import asyncio

                    asyncio.get_event_loop().run_in_executor(
                        None, _run_issue_management_for_payload, payload, event
                    )
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

    payload = json.loads(await request.body() or b"{}")
    dry_run = bool(payload.get("dry_run", False))
    owner = str(payload.get("owner") or "jclee941")
    if payload.get("background", True):
        import asyncio

        asyncio.get_event_loop().run_in_executor(
            None,
            partial(_run_app_issue_maintenance, app_id=app_id, private_key=private_key, owner=owner, dry_run=dry_run),
        )
        return {"accepted": True, "dry_run": dry_run, "owner": owner}
    return _run_app_issue_maintenance(app_id=app_id, private_key=private_key, owner=owner, dry_run=dry_run)


@app.post("/api/v1/checks_webhook")
async def checks_webhook(request: Request, response: Response) -> dict[str, Any]:
    """Standalone endpoint to run + report the App checks (useful for replay/test)."""
    raw = await request.body()
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    sig = request.headers.get("X-Hub-Signature-256")
    if not _verify_signature(secret, raw, sig):
        response.status_code = 401
        return {"error": "invalid signature"}
    payload = json.loads(raw or b"{}")
    return _run_checks_for_payload(payload)


def start() -> None:  # pragma: no cover - production entrypoint
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "3000")))


if __name__ == "__main__":  # pragma: no cover
    start()
