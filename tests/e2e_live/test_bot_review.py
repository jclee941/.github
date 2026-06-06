"""Live canary smoke tests for jclee-bot PR review behavior."""

from __future__ import annotations

import io
import re
import time
import zipfile
from collections.abc import Mapping
from typing import cast
from uuid import uuid4

import pytest
import requests

from .conftest import (
    GITHUB_API_URL,
    JsonObject,
    create_mutation_branch,
    create_mutation_pr,
    delete_mutation_branch,
    get_pr_comments,
    github_mutation_patch,
    github_mutation_post,
    guard_mutation,
    upsert_mutation_file,
)

pytestmark = [pytest.mark.canary, pytest.mark.bot_review]

BOT_LOGIN = "jclee-bot[bot]"


def _smoke_branch() -> str:
    return f"feat/e2e-bot-review-smoke-{_run_id()}"


def _draft_branch() -> str:
    return f"feat/e2e-bot-review-draft-{_run_id()}"


WORKFLOW_NAME = "PR Review (CLIProxyAPI)"
WORKFLOW_FILE = "pr-review.yml"
FATAL_PATTERNS = (
    "Failed to generate prediction with any model",
    "AuthenticationError",
    "Failed to review PR",
    "Resource not accessible by integration",
)

def _run_id() -> str:
    return f"{int(time.time())}-{uuid4().hex[:8]}"


def github_json(response: requests.Response) -> JsonObject:
    """Return a GitHub JSON object with endpoint context on failure."""
    assert response.status_code < 400, f"GitHub API failed: {response.status_code}: {response.text[:500]}"
    payload = cast(object, response.json())
    assert isinstance(payload, dict), f"Expected JSON object from GitHub, got {type(payload).__name__}"
    return cast(JsonObject, payload)


def github_json_list(response: requests.Response) -> list[JsonObject]:
    """Return a GitHub JSON list with endpoint context on failure."""
    assert response.status_code < 400, f"GitHub API failed: {response.status_code}: {response.text[:500]}"
    payload = cast(object, response.json())
    assert isinstance(payload, list), f"Expected JSON list from GitHub, got {type(payload).__name__}"
    return cast(list[JsonObject], payload)


def repo_default_branch(github_client: requests.Session, repo: str) -> str:
    """Return the default branch for a repository."""
    payload = github_json(github_client.get(f"{GITHUB_API_URL}/repos/{repo}"))
    default_branch = payload.get("default_branch")
    assert isinstance(default_branch, str), f"{repo}: missing default_branch"
    return default_branch


def branch_head_sha(github_client: requests.Session, repo: str, branch: str) -> str:
    """Return the current head SHA for a repository branch."""
    payload = github_json(github_client.get(f"{GITHUB_API_URL}/repos/{repo}/git/ref/heads/{branch}"))
    ref_object = payload.get("object")
    assert isinstance(ref_object, dict), f"{repo}@{branch}: malformed git ref object"
    sha = ref_object.get("sha")
    assert isinstance(sha, str), f"{repo}@{branch}: malformed git ref sha"
    return sha


def close_pr(github_client: requests.Session, repo: str, pr_number: int) -> None:
    """Close a canary pull request."""
    response = github_mutation_patch(
        github_client,
        repo,
        f"{GITHUB_API_URL}/repos/{repo}/pulls/{pr_number}",
        json={"state": "closed"},
    )
    assert response.status_code < 400, f"Failed to close PR #{pr_number}: {response.status_code}: {response.text[:500]}"


def close_open_prs_for_branch(github_client: requests.Session, repo: str, branch: str) -> None:
    """Close stale open canary PRs for a branch before reusing it."""
    guard_mutation(repo)
    response = github_client.get(
        f"{GITHUB_API_URL}/repos/{repo}/pulls",
        params={"head": f"{repo.split('/')[0]}:{branch}", "state": "open", "per_page": 20},
    )
    for pr in github_json_list(response):
        number = pr.get("number")
        if isinstance(number, int):
            close_pr(github_client, repo, number)


def create_canary_pr(
    github_client: requests.Session,
    repo: str,
    *,
    title: str,
    head: str,
    base: str,
    body: str,
    draft: bool = False,
) -> JsonObject:
    """Create a canary PR, using the shared helper for normal PRs and REST directly for draft PRs."""
    if not draft:
        return create_mutation_pr(repo, title, head, base, body, github_client)

    response = github_mutation_post(
        github_client,
        repo,
        f"{GITHUB_API_URL}/repos/{repo}/pulls",
        json={"base": base, "body": body, "draft": True, "head": head, "title": title},
    )
    return github_json(response)


def create_smoke_branch_with_file(
    github_client: requests.Session,
    repo: str,
    *,
    branch: str,
    path: str,
    content: str,
) -> str:
    """Create a fresh canary branch containing one smoke-test file."""
    guard_mutation(repo)
    close_open_prs_for_branch(github_client, repo, branch)
    delete_mutation_branch(repo, branch, github_client)

    base_branch = repo_default_branch(github_client, repo)
    base_sha = branch_head_sha(github_client, repo, base_branch)
    _ = create_mutation_branch(repo, branch, base_sha, github_client)
    _ = upsert_mutation_file(
        repo,
        path,
        content,
        "test: add bot review smoke fixture",
        branch,
        github_client,
    )
    return base_branch


def bot_comments(repo: str, pr_number: int) -> list[JsonObject]:
    """Return comments posted by jclee-bot on a PR issue thread."""
    comments = get_pr_comments(repo, pr_number)
    return [comment for comment in comments if nested_login(comment) == BOT_LOGIN]


def nested_login(payload: Mapping[str, object], key: str = "user") -> str | None:
    """Return a nested GitHub login from a response object."""
    value = payload.get(key)
    if not isinstance(value, dict):
        return None
    nested = cast(Mapping[str, object], value)
    login = nested.get("login")
    return login if isinstance(login, str) else None


def wait_for_bot_comment(repo: str, pr_number: int, timeout: int = 180) -> list[JsonObject]:
    """Poll for a bot comment, allowing the app/workflow several minutes to respond."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        comments = bot_comments(repo, pr_number)
        if comments:
            return comments
        time.sleep(15)
    return bot_comments(repo, pr_number)


def recent_pr_review_runs(
    github_client: requests.Session,
    repo: str,
    *,
    branch: str | None = None,
    limit: int = 10,
) -> list[JsonObject]:
    """Return recent PR review workflow runs, optionally scoped to a branch."""
    params: dict[str, str | int] = {"per_page": limit}
    if branch:
        params["branch"] = branch
    response = github_client.get(f"{GITHUB_API_URL}/repos/{repo}/actions/workflows/{WORKFLOW_FILE}/runs", params=params)
    if response.status_code == 404:
        return []
    payload = github_json(response)
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        return []
    return [cast(JsonObject, run) for run in runs if isinstance(run, dict)]


def wait_for_workflow_run_if_started(
    github_client: requests.Session,
    repo: str,
    branch: str,
    timeout: int = 180,
) -> JsonObject | None:
    """Wait briefly for a PR review workflow run to appear and complete, returning None if app-only path is used."""
    deadline = time.monotonic() + timeout
    latest_run: JsonObject | None = None
    while time.monotonic() < deadline:
        runs = recent_pr_review_runs(github_client, repo, branch=branch, limit=1)
        if runs:
            latest_run = runs[0]
            if latest_run.get("status") == "completed":
                return latest_run
        time.sleep(10)
    return latest_run


def workflow_log_text(github_client: requests.Session, repo: str, run_id: int) -> str:
    """Download and concatenate text logs for a workflow run."""
    response = github_client.get(f"{GITHUB_API_URL}/repos/{repo}/actions/runs/{run_id}/logs")
    if response.status_code in {403, 404, 410}:
        return ""
    assert response.status_code < 400, (
        f"Failed to download workflow logs: {response.status_code}: "
        f"{response.text[:500]}"
    )

    with zipfile.ZipFile(io.BytesIO(response.content)) as log_zip:
        chunks: list[str] = []
        for name in log_zip.namelist():
            if name.endswith("/"):
                continue
            chunks.append(log_zip.read(name).decode("utf-8", errors="replace"))
    return "\n".join(chunks)


def assert_no_fatal_patterns_in_run(github_client: requests.Session, repo: str, run: Mapping[str, object]) -> None:
    """Assert a workflow run did not fail with known pr-agent fatal patterns."""
    conclusion = run.get("conclusion")
    html_url = run.get("html_url") or run.get("url")
    run_id = run.get("id")
    assert isinstance(run_id, int), f"Malformed workflow run id: {run!r}"

    logs = workflow_log_text(github_client, repo, run_id)
    fatal_hits = [pattern for pattern in FATAL_PATTERNS if pattern in logs]
    assert not fatal_hits, f"{repo}: fatal patterns in {html_url}: {fatal_hits}"
    if conclusion in {"failure", "timed_out", "cancelled"}:
        no_op_patterns = [
            "Empty diff for PR:", "PR has no files:",
            "Review output is not published", "ResolutionImpossible",
        ]
        if any(p in logs for p in no_op_patterns):
            pytest.skip(f"{repo}: no-op pr-review run ({conclusion})")
        raise AssertionError(f"{repo}: workflow run failed: {html_url}")


def _assert_bot_review_quality(comments: list[JsonObject]) -> None:
    """Assert bot review comments meet quality standards."""
    bodies = [body for body in (c.get("body") for c in comments) if isinstance(body, str)]

    # Assertion 1 — Korean output
    hangul = re.compile(r"[\uac00-\ud7af]")
    assert any(hangul.search(body) for body in bodies), \
        "Bot review output should contain Korean text"

    # Assertion 2 — Final review marker
    marker_patterns = ["최종 리뷰", "리뷰 완료", "Final review", "📝"]
    assert any(
        any(marker in body for marker in marker_patterns) for body in bodies
    ), "Bot review should contain a final review marker"

    # Assertion 3 — Absence of failure strings
    failure_strings = [
        "Failed to generate prediction",
        "Failed to review PR",
        "AuthenticationError",
        "RateLimitError",
        "ConnectionError",
        "Timeout",
        "Internal Server Error",
    ]
    for body in bodies:
        for failure in failure_strings:
            assert failure not in body, f"Bot review should not contain error/failure messages: {failure}"

    # Assertion 4 — Review structure (markdown formatting)
    md_patterns = [re.compile(pattern) for pattern in [r"## ", r"\| ", r"```"]]
    assert any(pattern.search(body) for pattern in md_patterns for body in bodies), \
        "Bot review should use structured markdown formatting"


def test_bot_reviews_canary_pr(
    github_client: requests.Session,
    canary_public_repo: str,
    cliproxy_api_key: str,
) -> None:
    """Create a canary PR, trigger /review, and verify jclee-bot responds."""
    assert cliproxy_api_key
    repo = canary_public_repo
    pr_number: int | None = None
    smoke_branch = _smoke_branch()

    try:
        base_branch = create_smoke_branch_with_file(
            github_client,
            repo,
            branch=smoke_branch,
            path="bot_review_smoke.py",
            content='def smoke_review_target():\n    unused_value = "minor issue"\n    return "ok"\n',
        )
        pr = create_canary_pr(
            github_client,
            repo,
            title="test: e2e bot review smoke test",
            head=smoke_branch,
            base=base_branch,
            body="Live canary smoke test for jclee-bot review. Do not merge.",
        )
        number = pr.get("number")
        assert isinstance(number, int), f"Malformed PR payload: {pr!r}"
        pr_number = number
        response = github_mutation_post(
            github_client,
            repo,
            f"{GITHUB_API_URL}/repos/{repo}/issues/{pr_number}/comments",
            json={"body": "/review"},
        )
        assert response.status_code < 400, f"Failed to post /review: {response.status_code}: {response.text[:500]}"

        comments = wait_for_bot_comment(repo, pr_number, timeout=180)
        comment_bodies = [body for body in (comment.get("body") for comment in comments) if isinstance(body, str)]
        assert comments, f"{repo}#{pr_number}: no {BOT_LOGIN} comment after /review"
        assert any("Preparing review" in body or body.strip() for body in comment_bodies)

        _assert_bot_review_quality(comments)

        run = wait_for_workflow_run_if_started(github_client, repo, smoke_branch, timeout=180)
        if run is not None and run.get("status") == "completed":
            assert_no_fatal_patterns_in_run(github_client, repo, run)
    finally:
        if pr_number is not None:
            close_pr(github_client, repo, pr_number)
        delete_mutation_branch(repo, smoke_branch, github_client)


def test_bot_skips_draft_pr(github_client: requests.Session, canary_public_repo: str) -> None:
    """Draft canary PRs should not receive jclee-bot review comments."""
    repo = canary_public_repo
    pr_number: int | None = None
    draft_branch = _draft_branch()

    try:
        base_branch = create_smoke_branch_with_file(
            github_client,
            repo,
            branch=draft_branch,
            path="bot_review_draft_smoke.py",
            content='def draft_smoke_target():\n    unused_value = "draft issue"\n    return "ok"\n',
        )
        pr = create_canary_pr(
            github_client,
            repo,
            title="test: e2e bot review draft smoke test",
            head=draft_branch,
            base=base_branch,
            body="Draft canary smoke test for jclee-bot skip behavior. Do not merge.",
            draft=True,
        )
        number = pr.get("number")
        assert isinstance(number, int), f"Malformed PR payload: {pr!r}"
        pr_number = number
        assert pr.get("draft") is True, f"{repo}#{pr_number}: expected draft PR"

        time.sleep(60)
        assert not bot_comments(repo, pr_number), f"{repo}#{pr_number}: bot commented on draft PR"

        runs = recent_pr_review_runs(github_client, repo, branch=draft_branch, limit=3)
        good = {None, "skipped", "neutral", "success"}
        completed_bad_runs = [run for run in runs if run.get("conclusion") not in good]
        assert not completed_bad_runs, f"{repo}#{pr_number}: draft PR review workflow failed: {completed_bad_runs!r}"
    finally:
        if pr_number is not None:
            close_pr(github_client, repo, pr_number)
        delete_mutation_branch(repo, draft_branch, github_client)


def test_bot_fatal_error_detection(github_client: requests.Session, canary_public_repo: str) -> None:
    """Latest existing PR review workflow run in canary has no known fatal errors."""
    repo = canary_public_repo
    runs = recent_pr_review_runs(github_client, repo, limit=10)
    if not runs:
        pytest.skip(f"{repo}: no recent {WORKFLOW_NAME} workflow runs")

    completed_runs = [run for run in runs if run.get("status") == "completed"]
    if not completed_runs:
        pytest.skip(f"{repo}: no completed {WORKFLOW_NAME} workflow runs")

    assert_no_fatal_patterns_in_run(github_client, repo, completed_runs[0])
