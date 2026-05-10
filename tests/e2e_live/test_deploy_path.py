"""Live deployment-path validation for the deploy-to-repos Go script."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Protocol, cast

import pytest
import requests

from . import conftest

pytestmark = pytest.mark.deploy_path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
DEPLOY_BRANCH = "chore/sync-automation-workflows"
DEPLOY_PR_TITLE = "chore: sync automation workflows, dependabot, and templates"
DEPLOY_PR_TITLE = "chore: standardize automation workflows + dependabot config"
EXPECTED_DEPLOYED_FILES = {
    ".github/workflows/",
    ".github/dependabot.yml",
    ".github/CODEOWNERS",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/ISSUE_TEMPLATE/",
}
    ".github/workflows/",
    ".github/dependabot.yml",
    ".github/CODEOWNERS",
    ".github/PULL_REQUEST_TEMPLATE.md",
}
GO_MISSING = shutil.which("go") is None

JsonObject = dict[str, object]


class GithubMutationPatch(Protocol):
    def __call__(
        self,
        github_client: requests.Session,
        repo: str,
        url: str,
        *,
        json: JsonObject,
    ) -> requests.Response: ...


class GithubMutationDelete(Protocol):
    def __call__(self, github_client: requests.Session, repo: str, url: str) -> requests.Response: ...


GITHUB_API_URL = conftest.GITHUB_API_URL
guard_mutation = conftest.guard_mutation
mutation_patch = cast(GithubMutationPatch, conftest.github_mutation_patch)
mutation_delete = cast(GithubMutationDelete, conftest.github_mutation_delete)


def _raise_for_response(response: requests.Response, context: str) -> None:
    if response.status_code >= 400:
        raise AssertionError(f"{context} failed: {response.status_code}: {response.text[:500]}")


def _repo_name(full_repo: str) -> str:
    owner, name = full_repo.split("/", 1)
    assert owner == "jclee941", f"deploy-to-repos only supports jclee941 repos, got {full_repo!r}"
    return name


def _run_deploy_to_repos(repo: str, github_token: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GH_TOKEN"] = github_token
    env["GITHUB_TOKEN"] = github_token
    return subprocess.run(
        ["go", "run", "./cmd/deploy-to-repos", f"--canary-repos={_repo_name(repo)}"],
        cwd=SCRIPTS_DIR,
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
        check=False,
    )


def _find_deploy_pr(repo: str, github_client: requests.Session) -> JsonObject | None:
    response = github_client.get(
        f"{GITHUB_API_URL}/repos/{repo}/pulls",
        params={"state": "open", "head": f"jclee941:{DEPLOY_BRANCH}", "per_page": 20},
    )
    _raise_for_response(response, f"list open PRs for {repo}")
    payload = cast(object, response.json())
    assert isinstance(payload, list), f"{repo}: malformed PR list payload"
    for pr in cast(list[object], payload):
        if not isinstance(pr, dict):
            continue
        pr_payload = cast(JsonObject, pr)
        if DEPLOY_PR_TITLE in str(pr_payload.get("title", "")):
            return pr_payload
    return None


def _wait_for_deploy_pr(repo: str, github_client: requests.Session, timeout: int = 60) -> JsonObject:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pr = _find_deploy_pr(repo, github_client)
        if pr is not None:
            return pr
        time.sleep(5)
    raise AssertionError(f"{repo}: deploy PR with title containing {DEPLOY_PR_TITLE!r} was not created")


def _pr_changed_files(repo: str, pr_number: int, github_client: requests.Session) -> set[str]:
    response = github_client.get(f"{GITHUB_API_URL}/repos/{repo}/pulls/{pr_number}/files", params={"per_page": 100})
    _raise_for_response(response, f"list changed files for {repo}#{pr_number}")
    payload = cast(object, response.json())
    assert isinstance(payload, list), f"{repo}#{pr_number}: malformed PR files payload"
    files: set[str] = set()
    for item in cast(list[object], payload):
        assert isinstance(item, dict), f"{repo}#{pr_number}: malformed file item {item!r}"
        item_payload = cast(JsonObject, item)
        filename = item_payload.get("filename")
        assert isinstance(filename, str), f"{repo}#{pr_number}: missing filename in {item!r}"
        files.add(filename)
    return files


def _close_deploy_pr(repo: str, pr_number: int, github_client: requests.Session) -> None:
    response = mutation_patch(
        github_client,
        repo,
        f"{GITHUB_API_URL}/repos/{repo}/pulls/{pr_number}",
        json={"state": "closed"},
    )
    if response.status_code == 404:
        return
    _raise_for_response(response, f"close deploy PR {repo}#{pr_number}")


def _delete_deploy_branch(repo: str, github_client: requests.Session) -> None:
    guard_mutation(repo)
    # Close any existing deploy PRs first
    prs = github_client.get(
        f"{GITHUB_API_URL}/repos/{repo}/pulls",
        params={"state": "open", "head": f"jclee941:{DEPLOY_BRANCH}", "per_page": 20},
    ).json()
    for pr in prs:
        if isinstance(pr, dict) and DEPLOY_PR_TITLE in str(pr.get("title", "")):
            pr_number = pr["number"]
            response = mutation_patch(
                github_client,
                repo,
                f"{GITHUB_API_URL}/repos/{repo}/pulls/{pr_number}",
                json={"state": "closed"}
            )
            if response.status_code in {200, 201}:
                print(f"Closed stale deploy PR #{pr_number} in {repo}")
            elif response.status_code != 404:
                print(f"Warning: failed to close stale deploy PR #{pr_number} in {repo}: {response.status_code}")

    response = mutation_delete(
        github_client,
        repo,
        f"{GITHUB_API_URL}/repos/{repo}/git/refs/heads/{DEPLOY_BRANCH}",
    )
    if response.status_code in {404, 422}:
        return
    _raise_for_response(response, f"delete deploy branch {repo}:{DEPLOY_BRANCH}")


@pytest.mark.skipif(GO_MISSING, reason="go binary is not available on PATH")
def test_deploy_creates_pr_in_canary_repo(
    github_client: requests.Session,
    github_token: str,
    canary_public_repo: str,
) -> None:
    guard_mutation(canary_public_repo)
    pr_number: int | None = None

    try:
        _delete_deploy_branch(canary_public_repo, github_client)

        result = _run_deploy_to_repos(canary_public_repo, github_token)
        assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        assert _repo_name(canary_public_repo) in result.stdout
        assert "resume" not in result.stdout
        # If deploy skipped PR creation (no changes), skip the test
        if "skipping PR creation" in result.stdout:
            pytest.skip(f"{canary_public_repo}: deploy skipped PR creation — files already up to date")

        pr = _wait_for_deploy_pr(canary_public_repo, github_client)
        number = pr.get("number")
        assert isinstance(number, int), f"Malformed deploy PR payload without number: {pr!r}"
        pr_number = number

        changed_files = _pr_changed_files(canary_public_repo, pr_number, github_client)
        assert any(
            any(f.startswith(pattern) or f == pattern for pattern in EXPECTED_DEPLOYED_FILES)
            for f in changed_files
        ), (
            f"{canary_public_repo}#{pr_number}: no expected files in changed files "
            f"{sorted(changed_files)}"
        )
    finally:
        if pr_number is not None:
            _close_deploy_pr(canary_public_repo, pr_number, github_client)
        _delete_deploy_branch(canary_public_repo, github_client)
