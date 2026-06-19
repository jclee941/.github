from __future__ import annotations

import hmac
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from functools import partial
from pathlib import Path
from typing import Any

import requests
from fastapi import APIRouter, Request, Response

from jclee_bot import github_checks, issue_maintenance

GITHUB_API = "https://api.github.com"
BRANCH = "bot/auto-readme-update"
TITLE = "docs: auto-update README.md"
BODY = "Automated README.md update by jclee-bot App."

router = APIRouter()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}


def _bearer_token_ok(expected: str, authorization: str | None) -> bool:
    if not expected or not authorization or not authorization.startswith("Bearer "):
        return False
    return hmac.compare_digest(expected, authorization.removeprefix("Bearer ").strip())


def _run_git(args: list[str], *, cwd: Path, timeout: int = 120) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, timeout=timeout)  # noqa: S603


def _clone_repo(*, token: str, repo_full_name: str, default_branch: str, workspace: Path) -> Path:
    repo_path = workspace / "repo"
    url = f"https://x-access-token:{token}@github.com/{repo_full_name}.git"
    subprocess.run(  # noqa: S603
        ["git", "clone", "-q", "--depth", "1", "--branch", default_branch, url, str(repo_path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    return repo_path


def _render_readme(repo_path: Path) -> str:
    scripts_path = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts_path) not in sys.path:
        sys.path.insert(0, str(scripts_path))
    from generate_readme import generate_readme
    from generate_readme_cleaning import normalize_llm_readme_response, redact_private_ips, sanitize_links

    return redact_private_ips(sanitize_links(normalize_llm_readme_response(generate_readme(repo_path))))


def _ensure_readme_commit(*, token: str, repo: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    repo_full_name = str(repo.get("full_name", ""))
    default_branch = str(repo.get("default_branch") or "master")
    if not repo_full_name:
        return {"repo": repo_full_name, "changed": False, "error": "missing repo name"}

    with tempfile.TemporaryDirectory() as tmp:
        repo_path = _clone_repo(
            token=token,
            repo_full_name=repo_full_name,
            default_branch=default_branch,
            workspace=Path(tmp),
        )
        readme_path = repo_path / "README.md"
        old_content = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
        new_content = _render_readme(repo_path)
        if old_content == new_content:
            return {"repo": repo_full_name, "changed": False}
        if dry_run:
            return {"repo": repo_full_name, "changed": True, "dry_run": True}

        readme_path.write_text(new_content, encoding="utf-8")
        _run_git(["config", "user.email", "bot@jclee.me"], cwd=repo_path)
        _run_git(["config", "user.name", "jclee-bot"], cwd=repo_path)
        _run_git(["checkout", "-B", BRANCH], cwd=repo_path)
        _run_git(["add", "README.md"], cwd=repo_path)
        _run_git(["commit", "-m", TITLE], cwd=repo_path)
        _run_git(["push", "-u", "origin", BRANCH, "--force"], cwd=repo_path, timeout=180)
        pr_number = _upsert_pr(token=token, repo_full_name=repo_full_name, default_branch=default_branch)
        return {"repo": repo_full_name, "changed": True, "pr": pr_number}


def _upsert_pr(*, token: str, repo_full_name: str, default_branch: str) -> int:
    owner = repo_full_name.split("/", 1)[0]
    existing = requests.get(
        f"{GITHUB_API}/repos/{repo_full_name}/pulls",
        headers=_headers(token),
        params={"state": "open", "head": f"{owner}:{BRANCH}"},
        timeout=30,
    )
    existing.raise_for_status()
    prs = existing.json()
    if isinstance(prs, list) and prs:
        number = int(prs[0]["number"])
        patch = requests.patch(
            f"{GITHUB_API}/repos/{repo_full_name}/pulls/{number}",
            headers=_headers(token),
            json={"title": TITLE, "body": BODY},
            timeout=30,
        )
        patch.raise_for_status()
        return number

    created = requests.post(
        f"{GITHUB_API}/repos/{repo_full_name}/pulls",
        headers=_headers(token),
        json={"title": TITLE, "body": BODY, "base": default_branch, "head": BRANCH},
        timeout=30,
    )
    created.raise_for_status()
    number = int(created.json()["number"])
    _enable_auto_merge(token=token, pull_request_id=str(created.json().get("node_id", "")))
    return number


def _enable_auto_merge(*, token: str, pull_request_id: str) -> None:
    if not pull_request_id:
        return
    resp = requests.post(
        f"{GITHUB_API}/graphql",
        headers=_headers(token),
        json={
            "query": (
                "mutation($id:ID!){enablePullRequestAutoMerge(input:"
                "{pullRequestId:$id,mergeMethod:SQUASH}){pullRequest{number}}}"
            ),
            "variables": {"id": pull_request_id},
        },
        timeout=30,
    )
    if resp.status_code not in {200, 405, 422}:
        resp.raise_for_status()


def _repo_allowed(repo: dict[str, Any], *, owner: str, names: set[str] | None) -> bool:
    full_name = str(repo.get("full_name", ""))
    name = str(repo.get("name", ""))
    return full_name.startswith(f"{owner}/") and (names is None or name in names)


def _target_names(raw_names: Iterable[str] | None) -> set[str] | None:
    if raw_names is None:
        return issue_maintenance.managed_repo_names()
    return {name.strip() for name in raw_names if name.strip()}


def run_app_readme_automation(
    *,
    app_id: str,
    private_key: str,
    owner: str,
    dry_run: bool,
    repo_names: set[str] | None = None,
) -> dict[str, Any]:
    allowed = _target_names(repo_names)
    results: list[dict[str, Any]] = []
    for installation in issue_maintenance.app_installations(app_id=app_id, private_key=private_key):
        installation_id = int(installation.get("id", 0) or 0)
        if installation_id <= 0:
            continue
        token = github_checks.installation_token(app_id, private_key, installation_id)
        for repo in issue_maintenance.installation_repositories(token=token):
            if _repo_allowed(repo, owner=owner, names=allowed):
                results.append(_ensure_readme_commit(token=token, repo=repo, dry_run=dry_run))
    return {"dry_run": dry_run, "repositories": results}


@router.post("/api/v1/readme_automation")
async def readme_automation_webhook(request: Request, response: Response) -> dict[str, Any]:
    expected = os.environ.get("README_AUTOMATION_TOKEN") or os.environ.get("ISSUE_MAINTENANCE_TOKEN", "")
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
    repo_values = payload.get("repos")
    repos = {str(name) for name in repo_values} if isinstance(repo_values, list) else None
    if payload.get("background", True):
        import asyncio

        asyncio.get_event_loop().run_in_executor(
            None,
            partial(
                run_app_readme_automation,
                app_id=app_id,
                private_key=private_key,
                owner=owner,
                dry_run=dry_run,
                repo_names=repos,
            ),
        )
        return {"accepted": True, "dry_run": dry_run, "owner": owner}
    return run_app_readme_automation(
        app_id=app_id,
        private_key=private_key,
        owner=owner,
        dry_run=dry_run,
        repo_names=repos,
    )
