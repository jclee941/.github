"""Mutation helpers guarded to the private canary repository."""

from __future__ import annotations

import base64

import requests

from .github_read import json_object, raise_for_github_error
from .repo_config import GITHUB_API_URL, JsonObject

MUTATION_ALLOWED_REPOS = {"jclee941/automation-e2e-private"}


def guard_mutation(repo: str) -> None:
    """Raise if repo is not in mutation allowlist."""
    if repo not in MUTATION_ALLOWED_REPOS:
        raise RuntimeError(f"Mutation guard: {repo} not in allowlist. Aborting.")


def create_mutation_branch(repo: str, branch: str, sha: str, github_client: requests.Session) -> JsonObject:
    """Create a branch in an allowlisted canary repository."""
    guard_mutation(repo)
    response = github_client.post(
        f"{GITHUB_API_URL}/repos/{repo}/git/refs",
        json={"ref": f"refs/heads/{branch}", "sha": sha},
    )
    raise_for_github_error(response)
    return json_object(response)


def delete_mutation_branch(repo: str, branch: str, github_client: requests.Session) -> None:
    """Delete a branch in an allowlisted canary repository."""
    guard_mutation(repo)
    response = github_client.delete(f"{GITHUB_API_URL}/repos/{repo}/git/refs/heads/{branch}")
    if response.status_code in {404, 422}:
        return
    raise_for_github_error(response)


def close_mutation_pr(repo: str, pr_number: int, github_client: requests.Session) -> None:
    guard_mutation(repo)
    response = github_client.patch(
        f"{GITHUB_API_URL}/repos/{repo}/pulls/{pr_number}",
        json={"state": "closed"},
    )
    raise_for_github_error(response)


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
    raise_for_github_error(response)
    return json_object(response)


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
    raise_for_github_error(response)
    return json_object(response)
