from __future__ import annotations

import hmac
import json
import os
from functools import partial
from typing import Any

from fastapi import APIRouter, Request, Response

from jclee_bot import readme_jobs
from jclee_bot.readme_runner import run_app_readme_automation, sanitize_error

router = APIRouter()


def _bearer_token_ok(expected: str, authorization: str | None) -> bool:
    if not expected or not authorization or not authorization.startswith("Bearer "):
        return False
    return hmac.compare_digest(expected, authorization.removeprefix("Bearer ").strip())


def _expected_token() -> str:
    return os.environ.get("README_AUTOMATION_TOKEN") or os.environ.get("ISSUE_MAINTENANCE_TOKEN", "")


def _run_readme_job(job_id: str, **kwargs: Any) -> None:
    try:
        readme_jobs.mark_running(job_id)
        readme_jobs.mark_finished(job_id, run_app_readme_automation(**kwargs))
    except Exception as exc:  # noqa: BLE001 - background job status must record failures
        readme_jobs.mark_failed(job_id, sanitize_error(exc, secrets=[str(kwargs.get("private_key", ""))]))


@router.post("/api/v1/readme_automation")
async def readme_automation_webhook(request: Request, response: Response) -> dict[str, Any]:
    if not _bearer_token_ok(_expected_token(), request.headers.get("Authorization")):
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
    repo_values = payload.get("repos")
    repos = {str(name) for name in repo_values} if isinstance(repo_values, list) else None
    if payload.get("background", True):
        import asyncio

        job = readme_jobs.create_job(owner=owner, repos=sorted(repos) if repos is not None else None, dry_run=dry_run)
        asyncio.get_event_loop().run_in_executor(
            None,
            partial(
                _run_readme_job,
                job_id=str(job["id"]),
                app_id=app_id,
                private_key=private_key,
                owner=owner,
                dry_run=dry_run,
                repo_names=repos,
            ),
        )
        return {"accepted": True, "job_id": job["id"], "dry_run": dry_run, "owner": owner}
    return run_app_readme_automation(
        app_id=app_id,
        private_key=private_key,
        owner=owner,
        dry_run=dry_run,
        repo_names=repos,
    )


@router.get("/api/v1/readme_automation/jobs/{job_id}")
async def readme_automation_job_status(job_id: str, request: Request, response: Response) -> dict[str, Any]:
    if not _bearer_token_ok(_expected_token(), request.headers.get("Authorization")):
        response.status_code = 401
        return {"error": "invalid token"}
    try:
        return readme_jobs.get_job(job_id)
    except (FileNotFoundError, ValueError):
        response.status_code = 404
        return {"error": "job not found"}
