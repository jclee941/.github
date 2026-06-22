from __future__ import annotations

import subprocess
import sys
import tempfile
from collections.abc import Iterable
from importlib import import_module
from pathlib import Path
from typing import Any, Callable

import requests

from jclee_bot import github_checks, issue_maintenance
from jclee_bot.git_auth import git_askpass_env, git_env_with_auth, sanitize_access_token_url

GITHUB_API = "https://api.github.com"
BRANCH = "bot/auto-readme-update"
TARGET_BRANCH = "master"
TITLE = "docs: auto-update README.md"
BODY = "Automated README.md update by jclee-bot App."


class GitCommandError(RuntimeError):
    pass


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}


def sanitize_error(value: object, *, secrets: Iterable[str]) -> str:
    text = str(value)
    if isinstance(value, subprocess.CalledProcessError):
        text = value.stderr or str(value)
    text = sanitize_access_token_url(text)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text.strip() or "operation failed"


def _run_git(
    args: list[str],
    *,
    cwd: Path,
    timeout: int = 120,
    safe_args: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> None:
    try:
        completed = subprocess.run(  # noqa: S603
            ["git", *args],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=git_env_with_auth(env),
        )
    except subprocess.TimeoutExpired as exc:
        command = " ".join(["git", *(safe_args or args)])
        raise GitCommandError(f"{command}: timed out after {timeout}s") from exc
    if completed.returncode != 0:
        command = " ".join(["git", *(safe_args or args)])
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
        raise GitCommandError(f"{command}: {detail}")


def clone_repo(*, token: str, repo_full_name: str, default_branch: str, workspace: Path) -> Path:
    repo_path = workspace / "repo"
    url = f"https://github.com/{repo_full_name}.git"
    _run_git(
        ["clone", "-q", "--depth", "1", "--branch", default_branch, url, str(repo_path)],
        cwd=workspace,
        timeout=180,
        env=git_askpass_env(token=token, workspace=workspace),
        safe_args=[
            "clone",
            "-q",
            "--depth",
            "1",
            "--branch",
            default_branch,
            f"https://github.com/{repo_full_name}.git",
            str(repo_path),
        ],
    )
    return repo_path


def render_readme(repo_path: Path) -> str:
    scripts_path = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts_path) not in sys.path:
        sys.path.insert(0, str(scripts_path))
    generate_readme = import_module("generate_readme").generate_readme
    cleaning = import_module("generate_readme_cleaning")

    return cleaning.redact_private_ips(
        cleaning.sanitize_links(cleaning.normalize_llm_readme_response(generate_readme(repo_path))),
    )


def ensure_readme_commit(*, token: str, repo: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    repo_full_name = str(repo.get("full_name", ""))
    default_branch = TARGET_BRANCH
    if not repo_full_name:
        return {"repo": repo_full_name, "changed": False, "error": "missing repo name"}

    try:
        with tempfile.TemporaryDirectory() as tmp:
            repo_path = clone_repo(
                token=token,
                repo_full_name=repo_full_name,
                default_branch=default_branch,
                workspace=Path(tmp),
            )
            readme_path = repo_path / "README.md"
            old_content = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
            new_content = render_readme(repo_path)
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
            _run_git(
                ["push", "-u", "origin", BRANCH, "--force"],
                cwd=repo_path,
                timeout=180,
                env=git_askpass_env(token=token, workspace=repo_path.parent),
            )
            pr_number = upsert_pr(token=token, repo_full_name=repo_full_name, default_branch=default_branch)
            return {"repo": repo_full_name, "changed": True, "pr": pr_number}
    except (GitCommandError, subprocess.CalledProcessError, requests.RequestException) as exc:
        return {"repo": repo_full_name, "changed": False, "error": sanitize_error(exc, secrets=[token])}


def upsert_pr(*, token: str, repo_full_name: str, default_branch: str) -> int:
    owner = repo_full_name.split("/", 1)[0]
    existing = requests.get(
        f"{GITHUB_API}/repos/{repo_full_name}/pulls",
        headers=headers(token),
        params={"state": "open", "head": f"{owner}:{BRANCH}"},
        timeout=30,
    )
    existing.raise_for_status()
    prs = existing.json()
    if isinstance(prs, list) and prs:
        number = int(prs[0]["number"])
        patch = requests.patch(
            f"{GITHUB_API}/repos/{repo_full_name}/pulls/{number}",
            headers=headers(token),
            json={"title": TITLE, "body": BODY},
            timeout=30,
        )
        patch.raise_for_status()
        return number

    created = requests.post(
        f"{GITHUB_API}/repos/{repo_full_name}/pulls",
        headers=headers(token),
        json={"title": TITLE, "body": BODY, "base": default_branch, "head": BRANCH},
        timeout=30,
    )
    created.raise_for_status()
    number = int(created.json()["number"])
    enable_auto_merge(token=token, pull_request_id=str(created.json().get("node_id", "")))
    return number


def enable_auto_merge(*, token: str, pull_request_id: str) -> None:
    if not pull_request_id:
        return
    resp = requests.post(
        f"{GITHUB_API}/graphql",
        headers=headers(token),
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


def _contents_permission_error(permission: object, *, dry_run: bool, permission_known: bool) -> str | None:
    if not permission_known:
        return None
    if permission == "write":
        return None
    if dry_run and permission == "read":
        return None
    required = "read" if dry_run else "write"
    current = permission or "none"
    return f"GitHub App repository Contents permission must be {required}; current={current}"


def run_app_readme_automation(
    *,
    app_id: str,
    private_key: str,
    owner: str,
    dry_run: bool,
    repo_names: set[str] | None = None,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    allowed = _target_names(repo_names)
    results: list[dict[str, Any]] = []
    for installation in issue_maintenance.app_installations(app_id=app_id, private_key=private_key):
        installation_id = int(installation.get("id", 0) or 0)
        if installation_id <= 0:
            continue
        token = github_checks.installation_token(app_id, private_key, installation_id)
        permissions = installation.get("permissions")
        permission_known = isinstance(permissions, dict)
        contents_permission = permissions.get("contents") if isinstance(permissions, dict) else None
        for repo in issue_maintenance.installation_repositories(token=token):
            if _repo_allowed(repo, owner=owner, names=allowed):
                permission_error = _contents_permission_error(
                    contents_permission,
                    dry_run=dry_run,
                    permission_known=permission_known,
                )
                if permission_error:
                    result = {"repo": repo.get("full_name", ""), "changed": False, "error": permission_error}
                else:
                    result = ensure_readme_commit(token=token, repo=repo, dry_run=dry_run)
                results.append(result)
                if progress is not None:
                    progress(result)
    return {"dry_run": dry_run, "repositories": results}
