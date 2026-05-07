"""Shared fixtures and utilities for live GitHub automation E2E tests."""

from __future__ import annotations

import base64
import os
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeAlias, cast

import pytest
import requests
import yaml

JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

GITHUB_API_URL = "https://api.github.com"
GITHUB_OWNER = "jclee941"

MUTATION_ALLOWED_REPOS = {"jclee941/automation-e2e-public", "jclee941/automation-e2e-private"}
REPO_ROOT = Path(__file__).resolve().parents[2]
REPOS_CONFIG = REPO_ROOT / "config" / "repos.yaml"
REQUIRED_WORKFLOWS = ["pr-review.yml", "pr-checks.yml", "gitleaks.yml", "actionlint.yml"]
REQUIRED_FILES = [".github/dependabot.yml", ".github/CODEOWNERS", ".github/PULL_REQUEST_TEMPLATE.md"]
REQUIRED_CONTEXTS = ["pr-checks / Check PR Title", "pr-checks / Check Branch Name", "Gitleaks / scan"]

E2E_CANARY_PUBLIC_REPO = os.getenv("E2E_CANARY_PUBLIC_REPO", "jclee941/automation-e2e-public")
E2E_CANARY_PRIVATE_REPO = os.getenv("E2E_CANARY_PRIVATE_REPO", "jclee941/automation-e2e-private")
E2E_CLIPROXY_API_KEY = os.getenv("E2E_CLIPROXY_API_KEY") or os.getenv("CLIPROXY_API_KEY")


def _load_repos_config() -> list[JsonObject]:
    payload = cast(dict[str, Any], yaml.safe_load(REPOS_CONFIG.read_text(encoding="utf-8")))
    assert isinstance(payload, dict), "config/repos.yaml must contain a mapping"
    repositories = payload.get("repositories")
    assert isinstance(repositories, list), "config/repos.yaml must contain repositories list"
    return cast(list[JsonObject], repositories)


def configured_repo_names(flag: str | None = None) -> list[str]:
    names: list[str] = []
    for repo in _load_repos_config():
        if flag is not None:
            automation = repo.get("automation")
            if not isinstance(automation, dict) or automation.get(flag) is not True:
                continue
        name = repo.get("name")
        assert isinstance(name, str), "repository entry missing string name"
        names.append(name)
    return names


def guard_mutation(repo: str):
    """Raise if repo is not in mutation allowlist."""
    if repo not in MUTATION_ALLOWED_REPOS:
        raise RuntimeError(f"Mutation guard: {repo} not in allowlist. Aborting.")


def github_mutation_post(github_client: requests.Session, repo: str, url: str, **kwargs) -> requests.Response:
    """POST with mutation guard."""
    guard_mutation(repo)
    return github_client.post(url, **kwargs)


def github_mutation_patch(github_client: requests.Session, repo: str, url: str, **kwargs) -> requests.Response:
    """PATCH with mutation guard."""
    guard_mutation(repo)
    return github_client.patch(url, **kwargs)


def github_mutation_put(github_client: requests.Session, repo: str, url: str, **kwargs) -> requests.Response:
    """PUT with mutation guard."""
    guard_mutation(repo)
    return github_client.put(url, **kwargs)


def github_mutation_delete(github_client: requests.Session, repo: str, url: str, **kwargs) -> requests.Response:
    """DELETE with mutation guard."""
    guard_mutation(repo)
    return github_client.delete(url, **kwargs)


def _github_token_from_env() -> str | None:
    return os.getenv("E2E_GITHUB_TOKEN") or os.getenv("GH_TOKEN")


def _raise_for_github_error(response: requests.Response) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        message = response.text.strip()
        raise requests.HTTPError(f"{error}: {message}", response=response) from error


def _json_object(response: requests.Response) -> JsonObject:
    return cast(JsonObject, response.json())


def _json_list(response: requests.Response) -> list[JsonObject]:
    return cast(list[JsonObject], response.json())


@pytest.fixture(scope="session")
def github_token() -> str:
    """Return the live GitHub token, or skip when it is not configured."""
    token = _github_token_from_env()
    if not token:
        pytest.skip("Set E2E_GITHUB_TOKEN or GH_TOKEN to run live GitHub E2E tests")
    return token


@pytest.fixture(scope="session")
def gh(github_token: str) -> Callable[..., subprocess.CompletedProcess[str]]:
    """Run GitHub CLI commands with the configured live token."""

    def run_gh(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["GH_TOKEN"] = github_token
        env["GITHUB_TOKEN"] = github_token
        return subprocess.run(
            ["gh", *args],
            check=check,
            capture_output=True,
            env=env,
            text=True,
        )

    return run_gh


@pytest.fixture(scope="session")
def github_client(github_token: str) -> requests.Session:
    """Return an authenticated requests session for the GitHub REST API."""
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {github_token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )
    return session


@pytest.fixture(scope="session")
def repo_inventory(github_client: requests.Session) -> dict[str, JsonObject]:
    """Return visibility and default-branch metadata for every configured repository."""
    inventory: dict[str, JsonObject] = {}
    for repo_name in configured_repo_names():
        full_name = f"{GITHUB_OWNER}/{repo_name}"
        response = github_client.get(f"{GITHUB_API_URL}/repos/{full_name}")
        _raise_for_github_error(response)
        repo = _json_object(response)
        full_name_value = repo["full_name"]
        default_branch = repo["default_branch"]
        private = repo.get("private")
        visibility = repo.get("visibility")
        inventory[repo_name] = {
            "full_name": str(full_name_value),
            "visibility": str(visibility) if visibility else "private" if private else "public",
            "default_branch": str(default_branch),
        }
    return inventory


@pytest.fixture(scope="session")
def canary_public_repo() -> str:
    """Return the public canary repository allowed for live mutation tests."""
    return E2E_CANARY_PUBLIC_REPO


@pytest.fixture(scope="session")
def canary_private_repo() -> str:
    """Return the private canary repository allowed for live mutation tests."""
    return E2E_CANARY_PRIVATE_REPO


@pytest.fixture(scope="session")
def cliproxy_api_key() -> str:
    """Return the CLIProxyAPI key, or skip when it is not configured."""
    if not E2E_CLIPROXY_API_KEY:
        pytest.skip("Set E2E_CLIPROXY_API_KEY or CLIPROXY_API_KEY to run CLIProxy live checks")
    return E2E_CLIPROXY_API_KEY


def get_latest_workflow_run(repo: str, workflow_name: str) -> JsonObject | None:
    """Return the latest workflow run summary for a repository workflow."""
    token = _github_token_from_env()
    if not token:
        pytest.skip("Set E2E_GITHUB_TOKEN or GH_TOKEN to query GitHub workflow runs")

    with requests.Session() as session:
        session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        response = session.get(f"{GITHUB_API_URL}/repos/{repo}/actions/workflows/{workflow_name}/runs?per_page=1")
        _raise_for_github_error(response)
        payload = _json_object(response)
        runs = cast(list[JsonObject], payload.get("workflow_runs", []))

    if not runs:
        return None

    run = runs[0]
    return {
        "id": run["id"],
        "status": run["status"],
        "conclusion": run["conclusion"],
        "headBranch": run["head_branch"],
        "url": run["html_url"],
    }


def get_branch_protection(repo: str, branch: str) -> JsonObject | None:
    """Return branch protection settings for a repository branch, or None when unprotected."""
    token = _github_token_from_env()
    if not token:
        pytest.skip("Set E2E_GITHUB_TOKEN or GH_TOKEN to query GitHub branch protection")

    with requests.Session() as session:
        session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        response = session.get(f"{GITHUB_API_URL}/repos/{repo}/branches/{branch}/protection")

    if response.status_code == 404:
        return None
    _raise_for_github_error(response)
    return _json_object(response)


def get_repo_file_content(repo: str, path: str) -> str | None:
    """Return decoded repository file content, or None when the file does not exist."""
    token = _github_token_from_env()
    if not token:
        pytest.skip("Set E2E_GITHUB_TOKEN or GH_TOKEN to query GitHub repository files")

    with requests.Session() as session:
        session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        response = session.get(f"{GITHUB_API_URL}/repos/{repo}/contents/{path}")

    if response.status_code == 404:
        return None
    _raise_for_github_error(response)
    payload = _json_object(response)
    content = payload.get("content")
    if payload.get("encoding") != "base64" or not isinstance(content, str):
        return None
    return base64.b64decode(content).decode("utf-8")


def list_recent_prs(repo: str, state: str = "all", limit: int = 10) -> list[JsonObject]:
    """Return recent pull requests for a repository."""
    token = _github_token_from_env()
    if not token:
        pytest.skip("Set E2E_GITHUB_TOKEN or GH_TOKEN to query GitHub pull requests")

    with requests.Session() as session:
        session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        response = session.get(
            f"{GITHUB_API_URL}/repos/{repo}/pulls",
            params={"state": state, "sort": "updated", "direction": "desc", "per_page": limit},
        )
        _raise_for_github_error(response)
        return _json_list(response)


def get_pr_comments(repo: str, pr_number: int) -> list[JsonObject]:
    """Return issue comments posted on a pull request."""
    token = _github_token_from_env()
    if not token:
        pytest.skip("Set E2E_GITHUB_TOKEN or GH_TOKEN to query GitHub pull request comments")

    with requests.Session() as session:
        session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        response = session.get(f"{GITHUB_API_URL}/repos/{repo}/issues/{pr_number}/comments")
        _raise_for_github_error(response)
        return _json_list(response)


def wait_for_workflow_completion(repo: str, run_id: int, timeout: int = 300) -> JsonObject:
    """Poll a workflow run until it completes or timeout is reached."""
    token = _github_token_from_env()
    if not token:
        pytest.skip("Set E2E_GITHUB_TOKEN or GH_TOKEN to query GitHub workflow runs")

    deadline = time.monotonic() + timeout
    with requests.Session() as session:
        session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        while True:
            response = session.get(f"{GITHUB_API_URL}/repos/{repo}/actions/runs/{run_id}")
            _raise_for_github_error(response)
            run = _json_object(response)
            if run["status"] == "completed":
                return run
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Workflow run {repo}#{run_id} did not complete within {timeout} seconds")
            time.sleep(10)


def create_mutation_branch(repo: str, branch: str, sha: str, github_client: requests.Session) -> JsonObject:
    """Create a branch in an allowlisted canary repository."""
    guard_mutation(repo)
    response = github_client.post(
        f"{GITHUB_API_URL}/repos/{repo}/git/refs",
        json={"ref": f"refs/heads/{branch}", "sha": sha},
    )
    _raise_for_github_error(response)
    return _json_object(response)


def delete_mutation_branch(repo: str, branch: str, github_client: requests.Session) -> None:
    """Delete a branch in an allowlisted canary repository."""
    guard_mutation(repo)
    response = github_client.delete(f"{GITHUB_API_URL}/repos/{repo}/git/refs/heads/{branch}")
    if response.status_code in {404, 422}:
        return
        return
    _raise_for_github_error(response)


def upsert_mutation_file(
    repo: str,
    path: str,
    content: str,
    message: str,
    branch: str,
    github_client: requests.Session,
    sha: str | None = None,
) -> JsonObject:
    """Create or update a file in an allowlisted canary repository."""
    guard_mutation(repo)
    payload: JsonObject = {
        "branch": branch,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "message": message,
    }
    if sha:
        payload["sha"] = sha
    response = github_client.put(f"{GITHUB_API_URL}/repos/{repo}/contents/{path}", json=payload)
    _raise_for_github_error(response)
    return _json_object(response)


def create_mutation_pr(
    repo: str,
    title: str,
    head: str,
    base: str,
    body: str,
    github_client: requests.Session,
) -> JsonObject:
    """Create a pull request in an allowlisted canary repository."""
    guard_mutation(repo)
    response = github_client.post(
        f"{GITHUB_API_URL}/repos/{repo}/pulls",
        json={"base": base, "body": body, "head": head, "title": title},
    )
    _raise_for_github_error(response)
    return _json_object(response)
