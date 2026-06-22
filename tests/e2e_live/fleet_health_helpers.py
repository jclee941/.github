"""Helpers for read-only fleet health tests."""

from __future__ import annotations

import time
from collections.abc import Mapping

import requests

from .repo_config import GITHUB_API_URL, JsonObject, JsonValue, configured_repo_names

BOT_LOGIN = "jclee-bot[bot]"

def repo_names(repo_inventory: Mapping[str, JsonValue], automation_flag: str) -> tuple[str, ...]:
    """Return configured repos for an automation flag, failing if fixture inventory forgot one."""
    configured = configured_repo_names(automation_flag)
    required_repos = set(configured)
    missing_from_inventory = sorted(required_repos.difference(repo_inventory.keys()))
    assert not missing_from_inventory, f"repo_inventory is missing {automation_flag} repos: " + ", ".join(
        missing_from_inventory
    )
    return tuple(configured)


def gh_get(github_client: requests.Session, url: str, **params: str | int | bool | None) -> requests.Response:
    """GET with simple rate-limit sleep/retry handling for read-only GitHub REST calls."""
    for attempt in range(3):
        filtered_params = {key: str(value) for key, value in params.items() if value is not None}
        response = github_client.get(url, params=filtered_params)
        if response.status_code not in {403, 429}:
            return response

        remaining = response.headers.get("X-RateLimit-Remaining")
        reset = response.headers.get("X-RateLimit-Reset")
        retry_after = response.headers.get("Retry-After")
        if remaining == "0" and reset:
            wait_seconds = max(int(reset) - int(time.time()), 1)
        elif retry_after:
            wait_seconds = max(int(retry_after), 1)
        else:
            return response

        if attempt == 2:
            return response
        time.sleep(min(wait_seconds, 60))

    raise AssertionError(f"GitHub API GET retry loop exhausted unexpectedly: {url}")


def gh_json_object(github_client: requests.Session, url: str, **params: str | int | bool | None) -> JsonObject:
    response = gh_get(github_client, url, **params)
    assert response.status_code == 200, f"GitHub API GET failed: {url} -> {response.status_code}: {response.text[:500]}"
    payload = response.json()
    assert isinstance(payload, dict), f"GitHub API GET expected mapping: {url}"
    return payload


def gh_json_list(github_client: requests.Session, url: str, **params: str | int | bool | None) -> list[JsonObject]:
    """Return a list JSON response with endpoint context in failures."""
    response = gh_get(github_client, url, **params)
    assert response.status_code == 200, f"GitHub API GET failed: {url} -> {response.status_code}: {response.text[:500]}"
    payload = response.json()
    assert isinstance(payload, list), f"GitHub API GET expected list: {url}"
    for item in payload:
        assert isinstance(item, dict), f"GitHub API GET expected mapping list: {url}"
    return payload


def nested_object(payload: Mapping[str, JsonValue], key: str) -> JsonObject:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def content_sha(github_client: requests.Session, full_repo: str, path: str) -> str | None:
    """Return a repository content SHA, or None when the path is absent."""
    response = gh_get(github_client, f"{GITHUB_API_URL}/repos/{full_repo}/contents/{path}")
    if response.status_code == 404:
        return None
    assert response.status_code == 200, (
        f"{full_repo}: failed to read {path}: {response.status_code}: {response.text[:500]}"
    )
    payload = response.json()
    assert isinstance(payload, dict), f"{full_repo}: unexpected content response for {path}"
    sha = payload.get("sha")
    assert sha is None or isinstance(sha, str), f"{full_repo}: unexpected SHA value for {path}"
    return sha


def object_login(payload: Mapping[str, JsonValue], key: str = "user") -> str | None:
    login = nested_object(payload, key).get("login")
    return login if isinstance(login, str) else None


def pr_number(payload: Mapping[str, JsonValue]) -> int:
    """Return a pull request number with a clear failure if GitHub returns malformed data."""
    number = payload.get("number")
    assert isinstance(number, int), f"Malformed pull request payload without integer number: {payload!r}"
    return number
