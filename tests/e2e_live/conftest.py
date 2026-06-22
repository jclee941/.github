"""Shared fixtures for live GitHub automation E2E tests."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable

import pytest
import requests

from .github_read import (
    authenticated_session,
    github_token_from_env,
    json_object,
    raise_for_github_error,
)
from .repo_config import (
    GITHUB_API_URL,
    GITHUB_OWNER,
    JsonObject,
    configured_repo_names,
)

E2E_CANARY_PRIVATE_REPO = os.getenv("E2E_CANARY_PRIVATE_REPO", "jclee941/automation-e2e-private")
E2E_CLIPROXY_API_KEY = os.getenv("E2E_CLIPROXY_API_KEY") or os.getenv("CLIPROXY_API_KEY")


@pytest.fixture(scope="session")
def github_token() -> str:
    """Return the live GitHub token, or skip when it is not configured."""
    token = github_token_from_env()
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
    return authenticated_session(github_token)


@pytest.fixture(scope="session")
def repo_inventory(github_client: requests.Session) -> dict[str, JsonObject]:
    """Return visibility and default-branch metadata for every configured repository."""
    inventory: dict[str, JsonObject] = {}
    for repo_name in configured_repo_names():
        full_name = f"{GITHUB_OWNER}/{repo_name}"
        response = github_client.get(f"{GITHUB_API_URL}/repos/{full_name}")
        raise_for_github_error(response)
        repo = json_object(response)
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
def canary_private_repo() -> str:
    """Return the private canary repository allowed for live mutation tests."""
    return E2E_CANARY_PRIVATE_REPO


@pytest.fixture(scope="session")
def cliproxy_api_key() -> str:
    """Return the CLIProxyAPI key, or skip when it is not configured."""
    if not E2E_CLIPROXY_API_KEY:
        pytest.skip("Set E2E_CLIPROXY_API_KEY or CLIPROXY_API_KEY to run CLIProxy live checks")
    return E2E_CLIPROXY_API_KEY
