"""Read-only GitHub API helpers for live E2E tests."""

from __future__ import annotations

import os

import pytest
import requests

from .repo_config import GITHUB_API_URL, JsonObject


def github_token_from_env() -> str | None:
    return os.getenv("E2E_GITHUB_TOKEN") or os.getenv("GH_TOKEN")


def raise_for_github_error(response: requests.Response) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        message = response.text.strip()
        raise requests.HTTPError(f"{error}: {message}", response=response) from error


def json_object(response: requests.Response) -> JsonObject:
    payload = response.json()
    assert isinstance(payload, dict), f"Expected JSON mapping, got {type(payload).__name__}"
    return payload


def json_list(response: requests.Response) -> list[JsonObject]:
    payload = response.json()
    assert isinstance(payload, list), f"Expected JSON list, got {type(payload).__name__}"
    for item in payload:
        assert isinstance(item, dict), "Expected JSON mapping list"
    return payload


def authenticated_session(token: str) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )
    return session


def session_from_env(skip_message: str) -> requests.Session:
    token = github_token_from_env()
    if not token:
        pytest.skip(skip_message)
    return authenticated_session(token)


def get_latest_workflow_run(repo: str, workflow_name: str) -> JsonObject | None:
    with session_from_env("Set E2E_GITHUB_TOKEN or GH_TOKEN to query GitHub workflow runs") as session:
        response = session.get(f"{GITHUB_API_URL}/repos/{repo}/actions/workflows/{workflow_name}/runs?per_page=1")
        raise_for_github_error(response)
        payload = json_object(response)
        runs_value = payload.get("workflow_runs", [])
        assert isinstance(runs_value, list), "workflow_runs must be a list"
        runs = [run for run in runs_value if isinstance(run, dict)]

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
    with session_from_env("Set E2E_GITHUB_TOKEN or GH_TOKEN to query GitHub branch protection") as session:
        response = session.get(f"{GITHUB_API_URL}/repos/{repo}/branches/{branch}/protection")

    if response.status_code == 404:
        return None
    raise_for_github_error(response)
    return json_object(response)


def get_repo_file_content(repo: str, path: str) -> str | None:
    with session_from_env("Set E2E_GITHUB_TOKEN or GH_TOKEN to query GitHub repository files") as session:
        response = session.get(f"{GITHUB_API_URL}/repos/{repo}/contents/{path}")

    if response.status_code == 404:
        return None
    raise_for_github_error(response)
    payload = json_object(response)
    content = payload.get("content")
    if payload.get("encoding") != "base64" or not isinstance(content, str):
        return None

    import base64

    return base64.b64decode(content).decode("utf-8")


def list_recent_prs(repo: str, state: str = "all", limit: int = 10) -> list[JsonObject]:
    with session_from_env("Set E2E_GITHUB_TOKEN or GH_TOKEN to query GitHub pull requests") as session:
        response = session.get(
            f"{GITHUB_API_URL}/repos/{repo}/pulls",
            params={"state": state, "sort": "updated", "direction": "desc", "per_page": limit},
        )
        raise_for_github_error(response)
        return json_list(response)


def get_pr_comments(repo: str, pr_number: int) -> list[JsonObject]:
    with session_from_env("Set E2E_GITHUB_TOKEN or GH_TOKEN to query GitHub pull request comments") as session:
        response = session.get(f"{GITHUB_API_URL}/repos/{repo}/issues/{pr_number}/comments")
        raise_for_github_error(response)
        return json_list(response)


def wait_for_workflow_completion(repo: str, run_id: int, timeout: int = 300) -> JsonObject:
    del timeout
    with session_from_env("Set E2E_GITHUB_TOKEN or GH_TOKEN to query GitHub workflow runs") as session:
        response = session.get(f"{GITHUB_API_URL}/repos/{repo}/actions/runs/{run_id}")
        raise_for_github_error(response)
        run = json_object(response)
    if run["status"] != "completed":
        raise TimeoutError(f"Workflow run {repo}#{run_id} is still {run['status']}")
    return run
