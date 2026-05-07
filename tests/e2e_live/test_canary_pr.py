"""Live canary PR lifecycle checks for the deployed PR automation workflows."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import cast
from uuid import uuid4

import pytest
import requests

from .conftest import (
    GITHUB_API_URL,
    create_mutation_branch,
    create_mutation_pr,
    delete_mutation_branch,
    github_mutation_patch,
    guard_mutation,
    upsert_mutation_file,
)

pytestmark = pytest.mark.canary

CHECK_PR_TITLE = "Check PR Title"
CHECK_BRANCH_NAME = "Check Branch Name"
CHECK_GITLEAKS = "Gitleaks / scan"
REQUIRED_PASSING_CHECKS = (CHECK_PR_TITLE, CHECK_BRANCH_NAME, CHECK_GITLEAKS)

JsonObject = dict[str, object]


def _raise_for_response(response: requests.Response, context: str) -> None:
    if response.status_code >= 400:
        raise AssertionError(f"{context} failed: {response.status_code}: {response.text[:500]}")


def _repo_or_skip(repo: str, github_client: requests.Session) -> JsonObject:
    response = github_client.get(f"{GITHUB_API_URL}/repos/{repo}")
    if response.status_code == 404:
        pytest.skip(f"Canary repo is unavailable: {repo}")
    _raise_for_response(response, f"read repo {repo}")
    payload = cast(object, response.json())
    assert isinstance(payload, dict), f"Malformed repository payload for {repo}: {payload!r}"
    return cast(JsonObject, payload)


def _default_branch_and_sha(repo: str, github_client: requests.Session) -> tuple[str, str]:
    repo_payload = _repo_or_skip(repo, github_client)
    default_branch = repo_payload.get("default_branch")
    assert isinstance(default_branch, str), f"{repo}: missing default_branch"

    response = github_client.get(f"{GITHUB_API_URL}/repos/{repo}/git/ref/heads/{default_branch}")
    _raise_for_response(response, f"read default branch ref for {repo}")
    ref_payload = cast(object, response.json())
    assert isinstance(ref_payload, dict), f"{repo}: malformed ref payload"
    ref_object = cast(Mapping[str, object], ref_payload)
    obj = ref_object.get("object")
    assert isinstance(obj, dict), f"{repo}: malformed ref object"
    object_payload = cast(Mapping[str, object], obj)
    sha = object_payload.get("sha")
    assert isinstance(sha, str), f"{repo}: missing default branch SHA"
    return default_branch, sha


def _run_id() -> str:
    return f"{int(time.time())}-{uuid4().hex[:8]}"


def _check_aliases(check_name: str) -> tuple[str, ...]:
    if check_name == CHECK_GITLEAKS:
        return (CHECK_GITLEAKS, "scan", "Gitleaks", "Gitleaks / Run gitleaks")
    return (check_name, f"pr-checks / {check_name}", f"PR Checks / {check_name}")


def _canonical_check_name(raw_name: object) -> str | None:
    if not isinstance(raw_name, str):
        return None
    for check_name in REQUIRED_PASSING_CHECKS:
        if raw_name in _check_aliases(check_name) or raw_name.endswith(f" / {check_name}"):
            return check_name
    return raw_name


def _check_conclusion(check: Mapping[str, object]) -> str | None:
    conclusion = check.get("conclusion")
    return conclusion if isinstance(conclusion, str) else None


def _check_status(check: Mapping[str, object]) -> str | None:
    status = check.get("status")
    return status if isinstance(status, str) else None


def _latest_pr_head_sha(repo: str, pr_number: int, github_client: requests.Session) -> str:
    response = github_client.get(f"{GITHUB_API_URL}/repos/{repo}/pulls/{pr_number}")
    _raise_for_response(response, f"read PR {repo}#{pr_number}")
    payload = cast(object, response.json())
    assert isinstance(payload, dict), f"{repo}#{pr_number}: malformed PR payload"
    pr_payload = cast(Mapping[str, object], payload)
    head = pr_payload.get("head")
    assert isinstance(head, dict), f"{repo}#{pr_number}: malformed PR head"
    head_payload = cast(Mapping[str, object], head)
    sha = head_payload.get("sha")
    assert isinstance(sha, str), f"{repo}#{pr_number}: missing head SHA"
    return sha


def _current_checks(repo: str, pr_number: int, github_client: requests.Session) -> dict[str, JsonObject]:
    sha = _latest_pr_head_sha(repo, pr_number, github_client)
    response = github_client.get(
        f"{GITHUB_API_URL}/repos/{repo}/commits/{sha}/check-runs",
        params={"per_page": 100},
    )
    _raise_for_response(response, f"read check runs for {repo}#{pr_number}")
    payload = cast(object, response.json())
    assert isinstance(payload, dict), f"{repo}#{pr_number}: malformed check-runs payload"
    checks_payload = cast(Mapping[str, object], payload)
    check_runs = checks_payload.get("check_runs")
    assert isinstance(check_runs, list), f"{repo}#{pr_number}: missing check_runs list"

    checks: dict[str, JsonObject] = {}
    for check_run in cast(list[object], check_runs):
        if not isinstance(check_run, dict):
            continue
        check_run_payload = cast(Mapping[str, object], check_run)
        canonical = _canonical_check_name(check_run_payload.get("name"))
        if canonical:
            checks[canonical] = cast(JsonObject, check_run_payload)
    return checks


def wait_for_checks(
    repo: str,
    pr_number: int,
    github_client: requests.Session,
    expected_checks: tuple[str, ...] = REQUIRED_PASSING_CHECKS,
    timeout: int = 120,
) -> dict[str, JsonObject]:
    """Poll PR check runs until expected checks complete or timeout."""
    deadline = time.time() + timeout
    last_checks: dict[str, JsonObject] = {}
    while time.time() < deadline:
        last_checks = _current_checks(repo, pr_number, github_client)
        if all(_check_status(last_checks.get(check, {})) == "completed" for check in expected_checks):
            return last_checks
        time.sleep(5)

    summary = {
        name: {"status": _check_status(check), "conclusion": _check_conclusion(check)}
        for name, check in last_checks.items()
    }
    raise TimeoutError(f"{repo}#{pr_number}: checks did not complete within {timeout}s: {summary}")


def _assert_check_conclusion(checks: Mapping[str, Mapping[str, object]], check_name: str, conclusion: str) -> None:
    check = checks.get(check_name)
    assert check is not None, f"Missing expected check: {check_name}. Got: {sorted(checks)}"
    assert _check_status(check) == "completed", f"{check_name} did not complete: {check}"
    assert _check_conclusion(check) == conclusion, f"{check_name} expected {conclusion}, got {check}"


def _issue_comments(repo: str, pr_number: int, github_client: requests.Session) -> list[JsonObject]:
    response = github_client.get(f"{GITHUB_API_URL}/repos/{repo}/issues/{pr_number}/comments", params={"per_page": 100})
    _raise_for_response(response, f"read comments for {repo}#{pr_number}")
    payload = cast(object, response.json())
    assert isinstance(payload, list), f"{repo}#{pr_number}: malformed comments payload"
    return cast(list[JsonObject], payload)


def _assert_comment_contains(
    repo: str,
    pr_number: int,
    github_client: requests.Session,
    *needles: str,
    timeout: int = 60,
) -> None:
    deadline = time.time() + timeout
    comments: list[JsonObject] = []
    while time.time() < deadline:
        comments = _issue_comments(repo, pr_number, github_client)
        bodies = [comment.get("body") for comment in comments]
        if any(isinstance(body, str) and all(needle in body for needle in needles) for body in bodies):
            return
        time.sleep(5)
    rendered = "\n---\n".join(str(comment.get("body", ""))[:500] for comment in comments)
    raise AssertionError(f"{repo}#{pr_number}: no comment contains {needles!r}. Comments:\n{rendered}")


def _close_mutation_pr(repo: str, pr_number: int, github_client: requests.Session) -> None:
    response = github_mutation_patch(
        github_client,
        repo,
        f"{GITHUB_API_URL}/repos/{repo}/pulls/{pr_number}",
        json={"state": "closed"},
    )
    if response.status_code == 404:
        return
    _raise_for_response(response, f"close PR {repo}#{pr_number}")


def _find_oversized_issue(repo: str, pr_number: int, github_client: requests.Session) -> JsonObject | None:
    response = github_client.get(
        f"{GITHUB_API_URL}/repos/{repo}/issues",
        params={"state": "open", "labels": "", "per_page": 100},
    )
    _raise_for_response(response, f"list issues for {repo}")
    payload = cast(object, response.json())
    assert isinstance(payload, list), f"{repo}: malformed issues payload"
    for issue in cast(list[object], payload):
        if not isinstance(issue, dict) or "pull_request" in issue:
            continue
        issue_payload = cast(Mapping[str, object], issue)
        title = issue_payload.get("title")
        if isinstance(title, str) and f"PR #{pr_number} exceeds 500 LOC" in title:
            return cast(JsonObject, issue_payload)
    return None


def _wait_for_oversized_issue(
    repo: str,
    pr_number: int,
    github_client: requests.Session,
    timeout: int = 60,
) -> JsonObject:
    deadline = time.time() + timeout
    while time.time() < deadline:
        issue = _find_oversized_issue(repo, pr_number, github_client)
        if issue:
            return issue
        time.sleep(5)
    raise AssertionError(f"{repo}#{pr_number}: oversized-PR issue was not created")


def _close_mutation_issue(repo: str, issue_number: int, github_client: requests.Session) -> None:
    response = github_mutation_patch(
        github_client,
        repo,
        f"{GITHUB_API_URL}/repos/{repo}/issues/{issue_number}",
        json={"state": "closed"},
    )
    if response.status_code == 404:
        return
    _raise_for_response(response, f"close issue {repo}#{issue_number}")


def _create_canary_pr(
    repo: str,
    branch: str,
    path: str,
    content: str,
    title: str,
    github_client: requests.Session,
) -> tuple[str, int]:
    guard_mutation(repo)
    default_branch, sha = _default_branch_and_sha(repo, github_client)
    _ = create_mutation_branch(repo, branch, sha, github_client)
    _ = upsert_mutation_file(
        repo,
        path,
        content,
        f"test: add canary fixture for {branch}",
        branch,
        github_client,
    )
    pr = create_mutation_pr(
        repo,
        title,
        branch,
        default_branch,
        "## Changes\n\nLive canary PR generated by the e2e test suite.",
        github_client,
    )
    number = pr.get("number")
    assert isinstance(number, int), f"Malformed PR payload without number: {pr!r}"
    return default_branch, number


def test_valid_pr_passes_checks(github_client: requests.Session, canary_public_repo: str) -> None:
    run_id = _run_id()
    branch = f"feat/e2e-valid-pr-{run_id}"
    pr_number: int | None = None
    try:
        _, pr_number = _create_canary_pr(
            canary_public_repo,
            branch,
            f"e2e/valid-{run_id}.txt",
            f"valid canary change {run_id}\n",
            "test: e2e valid pr checks",
            github_client,
        )
        checks = wait_for_checks(canary_public_repo, pr_number, github_client)
        for check_name in REQUIRED_PASSING_CHECKS:
            _assert_check_conclusion(checks, check_name, "success")
    finally:
        if pr_number is not None:
            _close_mutation_pr(canary_public_repo, pr_number, github_client)
        delete_mutation_branch(canary_public_repo, branch, github_client)


def test_invalid_title_fails(github_client: requests.Session, canary_public_repo: str) -> None:
    run_id = _run_id()
    branch = f"fix/e2e-invalid-title-{run_id}"
    pr_number: int | None = None
    try:
        _, pr_number = _create_canary_pr(
            canary_public_repo,
            branch,
            f"e2e/invalid-title-{run_id}.txt",
            f"invalid title canary change {run_id}\n",
            "bad title here",
            github_client,
        )
        checks = wait_for_checks(
            canary_public_repo,
            pr_number,
            github_client,
            expected_checks=(CHECK_PR_TITLE, CHECK_BRANCH_NAME, CHECK_GITLEAKS),
        )
        _assert_check_conclusion(checks, CHECK_PR_TITLE, "failure")
        _assert_check_conclusion(checks, CHECK_BRANCH_NAME, "success")
        _assert_comment_contains(canary_public_repo, pr_number, github_client, "Conventional Commits")
    finally:
        if pr_number is not None:
            _close_mutation_pr(canary_public_repo, pr_number, github_client)
        delete_mutation_branch(canary_public_repo, branch, github_client)


def test_invalid_branch_fails(github_client: requests.Session, canary_public_repo: str) -> None:
    run_id = _run_id()
    branch = f"bad_branch_name_{run_id}"
    pr_number: int | None = None
    try:
        _, pr_number = _create_canary_pr(
            canary_public_repo,
            branch,
            f"e2e/invalid-branch-{run_id}.txt",
            f"invalid branch canary change {run_id}\n",
            "test: e2e invalid branch checks",
            github_client,
        )
        checks = wait_for_checks(
            canary_public_repo,
            pr_number,
            github_client,
            expected_checks=(CHECK_PR_TITLE, CHECK_BRANCH_NAME, CHECK_GITLEAKS),
        )
        _assert_check_conclusion(checks, CHECK_PR_TITLE, "success")
        _assert_check_conclusion(checks, CHECK_BRANCH_NAME, "failure")
    finally:
        if pr_number is not None:
            _close_mutation_pr(canary_public_repo, pr_number, github_client)
        delete_mutation_branch(canary_public_repo, branch, github_client)


def test_large_pr_warning(github_client: requests.Session, canary_public_repo: str) -> None:
    run_id = _run_id()
    branch = f"feat/e2e-large-pr-{run_id}"
    pr_number: int | None = None
    oversized_issue_number: int | None = None
    large_content = "".join(f"harmless canary line {line} for {run_id}\n" for line in range(650))
    try:
        _, pr_number = _create_canary_pr(
            canary_public_repo,
            branch,
            f"e2e/large-pr-{run_id}.txt",
            large_content,
            "test: e2e large pr warning",
            github_client,
        )
        checks = wait_for_checks(canary_public_repo, pr_number, github_client)
        for check_name in REQUIRED_PASSING_CHECKS:
            _assert_check_conclusion(checks, check_name, "success")

        oversized_issue = _wait_for_oversized_issue(canary_public_repo, pr_number, github_client)
        oversized_issue_number_value = oversized_issue.get("number")
        assert isinstance(oversized_issue_number_value, int), f"Malformed oversized issue: {oversized_issue!r}"
        oversized_issue_number = oversized_issue_number_value
        assert "exceeds 500 LOC" in str(oversized_issue.get("title", ""))
    finally:
        if oversized_issue_number is not None:
            _close_mutation_issue(canary_public_repo, oversized_issue_number, github_client)
        if pr_number is not None:
            _close_mutation_pr(canary_public_repo, pr_number, github_client)
        delete_mutation_branch(canary_public_repo, branch, github_client)


def test_sensitive_file_warning(github_client: requests.Session, canary_public_repo: str) -> None:
    run_id = _run_id()
    branch = f"docs/e2e-sensitive-file-{run_id}"
    pr_number: int | None = None
    try:
        _, pr_number = _create_canary_pr(
            canary_public_repo,
            branch,
            f"e2e/.env.example-{run_id}",
            "# Harmless canary example file; no real secrets.\nEXAMPLE_VALUE=placeholder\n",
            "docs: e2e sensitive file warning",
            github_client,
        )
        checks = wait_for_checks(canary_public_repo, pr_number, github_client)
        for check_name in REQUIRED_PASSING_CHECKS:
            _assert_check_conclusion(checks, check_name, "success")
        _assert_comment_contains(canary_public_repo, pr_number, github_client, "민감 파일 변경 감지")
    finally:
        if pr_number is not None:
            _close_mutation_pr(canary_public_repo, pr_number, github_client)
        delete_mutation_branch(canary_public_repo, branch, github_client)
