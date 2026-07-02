from __future__ import annotations

import os
import subprocess  # noqa: S404 - fixed-arg git checkout of the PR head
import tempfile
from collections.abc import Callable
from typing import Any

from jclee_bot import dispatch, github_checks
from jclee_bot.context_guards import neutralize_on_missing_context
from jclee_bot.git_auth import git_askpass_env, git_env_with_auth

GITHUB_API = "https://api.github.com"


def installation_token(installation_id: int) -> str | None:
    app_id = os.environ.get("GITHUB_APP_ID")
    private_key = os.environ.get("GITHUB_PRIVATE_KEY")
    if not (app_id and private_key and installation_id):
        return None
    return github_checks.installation_token(app_id, private_key, installation_id)


def fetch_changed_files(token: str, repo_full_name: str, pr_number: int) -> list[str]:
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


def checkout_pr_head(token: str, repo_full_name: str, head_sha: str, workspace: str) -> bool:
    url = f"https://github.com/{repo_full_name}.git"
    fetch_env = git_env_with_auth(git_askpass_env(token=token, workspace=workspace))
    try:
        subprocess.run(
            ["git", "init", "-q", workspace],
            check=True,
            timeout=30,
        )
        subprocess.run(
            ["git", "-C", workspace, "fetch", "-q", "--depth", "1", url, head_sha],
            check=True,
            timeout=120,
            capture_output=True,
            env=fetch_env,
        )
        subprocess.run(
            ["git", "-C", workspace, "checkout", "-q", "FETCH_HEAD"],
            check=True,
            timeout=60,
            capture_output=True,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False


def run_checks_for_payload(
    payload: dict[str, Any],
    *,
    installation_token_fn: Callable[[int], str | None] = installation_token,
    fetch_changed_files_fn: Callable[[str, str, int], list[str]] = fetch_changed_files,
    checkout_pr_head_fn: Callable[[str, str, str, str], bool] = checkout_pr_head,
    create_check_run_fn: Callable[..., Any] = github_checks.create_check_run,
) -> dict[str, Any]:
    pr = payload.get("pull_request") or {}
    repo_full_name = payload.get("repository", {}).get("full_name", "")
    installation_id = payload.get("installation", {}).get("id", 0)
    head_sha = dispatch.head_sha(payload)
    pr_number = pr.get("number", 0)

    try:
        token = installation_token_fn(installation_id)
    except Exception:  # noqa: BLE001 - missing/invalid App creds must not 500
        token = None

    changed_files: list[str] = []
    files_ok = False
    if token and repo_full_name and pr_number:
        try:
            changed_files = fetch_changed_files_fn(token, repo_full_name, pr_number)
            files_ok = True
        except Exception:  # noqa: BLE001 - degrade gracefully on API errors
            files_ok = False

    with tempfile.TemporaryDirectory() as workspace:
        checkout_ok = False
        if token and head_sha and repo_full_name:
            checkout_ok = checkout_pr_head_fn(token, repo_full_name, head_sha, workspace)
        results = dispatch.run_checks(payload, changed_files=changed_files, workspace=workspace)

    results = neutralize_on_missing_context(results, files_ok=files_ok, checkout_ok=checkout_ok)

    reported = []
    if token and repo_full_name and head_sha:
        for result in results:
            try:
                create_check_run_fn(
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
