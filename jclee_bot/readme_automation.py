from __future__ import annotations

import hmac
import json
import os
import re
import subprocess
import sys
from typing import Any

from fastapi import APIRouter, Request, Response

from jclee_bot import readme_jobs
from jclee_bot.readme_runner import run_app_readme_automation

router = APIRouter()
OWNER_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
REPO_PATTERN = re.compile(r"^[A-Za-z0-9._][A-Za-z0-9._-]{0,99}$")


class InvalidReadmeAutomationRequest(ValueError):
    pass


def _bearer_token_ok(expected: str, authorization: str | None) -> bool:
    if not expected or not authorization or not authorization.startswith("Bearer "):
        return False
    return hmac.compare_digest(expected, authorization.removeprefix("Bearer ").strip())


def _expected_token() -> str:
    return os.environ.get("README_AUTOMATION_TOKEN") or os.environ.get("ISSUE_MAINTENANCE_TOKEN", "")


def _parse_owner(value: object) -> str:
    if value is None or value == "":
        return "jclee941"
    if not isinstance(value, str) or not OWNER_PATTERN.fullmatch(value):
        raise InvalidReadmeAutomationRequest("owner must be a GitHub account name")
    return value


def _parse_repos(value: object) -> set[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise InvalidReadmeAutomationRequest("repos must be a list")
    repos: set[str] = set()
    for repo in value:
        if not isinstance(repo, str) or not REPO_PATTERN.fullmatch(repo):
            raise InvalidReadmeAutomationRequest("repos must contain GitHub repository names")
        repos.add(repo)
    return repos


def _spawn_readme_job(*, job_id: str, owner: str, dry_run: bool, repos: set[str] | None) -> None:
    args = [
        sys.executable,
        "-m",
        "jclee_bot.readme_job_worker",
        f"--job-id={job_id}",
        f"--owner={owner}",
    ]
    if dry_run:
        args.append("--dry-run")
    for repo in sorted(repos or []):
        args.append(f"--repo={repo}")
    try:
        process = subprocess.Popen(args, close_fds=True, start_new_session=True)  # noqa: S603
    except OSError as exc:
        readme_jobs.mark_failed(job_id, f"failed to start README automation worker: {exc.strerror or exc}")
        return
    readme_jobs.mark_spawned(job_id, pid=process.pid)


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
    try:
        dry_run = bool(payload.get("dry_run", False))
        owner = _parse_owner(payload.get("owner"))
        repos = _parse_repos(payload.get("repos"))
    except InvalidReadmeAutomationRequest as exc:
        response.status_code = 400
        return {"error": str(exc)}
    if payload.get("background", True):
        job = readme_jobs.create_job(owner=owner, repos=sorted(repos) if repos is not None else None, dry_run=dry_run)
        _spawn_readme_job(job_id=str(job["id"]), owner=owner, dry_run=dry_run, repos=repos)
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
