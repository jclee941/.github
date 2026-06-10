"""Minimal GitHub Checks API client for reporting App-owned check runs.

Creates a Check Run on a commit SHA in an installed repo. Auth uses the App's
installation token, minted from APP_ID + PRIVATE_KEY (the same credentials the
upstream pr_agent App uses) without importing pr_agent internals.
"""
from __future__ import annotations

import time
from typing import Any

import jwt
import requests

from jclee_bot.checks import CheckResult

GITHUB_API = "https://api.github.com"


def _app_jwt(app_id: str, private_key: str) -> str:
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 540, "iss": app_id}
    return jwt.encode(payload, private_key, algorithm="RS256")


def installation_token(app_id: str, private_key: str, installation_id: int) -> str:
    token_jwt = _app_jwt(app_id, private_key)
    resp = requests.post(
        f"{GITHUB_API}/app/installations/{installation_id}/access_tokens",
        headers={
            "Authorization": f"Bearer {token_jwt}",
            "Accept": "application/vnd.github+json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["token"]


def check_run_payload(result: CheckResult, head_sha: str) -> dict[str, Any]:
    """Map a CheckResult onto the Checks API create-check-run body."""
    return {
        "name": result.name,
        "head_sha": head_sha,
        "status": "completed",
        "conclusion": result.conclusion,
        "output": {"title": result.title, "summary": result.summary},
    }


def create_check_run(
    *, token: str, repo_full_name: str, result: CheckResult, head_sha: str
) -> requests.Response:
    resp = requests.post(
        f"{GITHUB_API}/repos/{repo_full_name}/check-runs",
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
        },
        json=check_run_payload(result, head_sha),
        timeout=30,
    )
    resp.raise_for_status()  # a rejected check run must NOT be counted as reported
    return resp
