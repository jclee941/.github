"""Read-only live fleet health checks for managed jclee941 repositories."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, cast

import pytest
import requests

from .conftest import (
    GITHUB_API_URL,
    GITHUB_OWNER,
    REQUIRED_CONTEXTS,
    REQUIRED_FILES,
    REQUIRED_WORKFLOWS,
    configured_repo_names,
)

pytestmark = pytest.mark.readonly

SOURCE_REPO = f"{GITHUB_OWNER}/.github"
BOT_LOGIN = "jclee-bot[bot]"
APP_SLUG = "jclee-bot"

DRIFT_FILES = tuple(f".github/workflows/{workflow}" for workflow in REQUIRED_WORKFLOWS) + tuple(REQUIRED_FILES)
# App-era: per-repo CI workflow files (pr-checks.yml, gitleaks.yml) are gone
# because the jclee-bot GitHub App posts Checks API runs centrally. Workflow
# health is monitored via the bot review smoke tests, not per-repo file
# presence, so the candidates list is empty until new per-repo workflows are
# reintroduced.
WORKFLOW_HEALTH_CANDIDATES: dict[str, tuple[str, ...]] = {}
SUCCESS_CONCLUSIONS = {"success", "skipped", "neutral"}

JsonObject = dict[str, object]


def repo_names(repo_inventory: Mapping[str, object], automation_flag: str) -> tuple[str, ...]:
    """Return configured repos for an automation flag, failing if fixture inventory forgot one."""
    configured = configured_repo_names(automation_flag)
    required_repos = set(configured)
    missing_from_inventory = sorted(required_repos.difference(repo_inventory.keys()))
    assert not missing_from_inventory, f"repo_inventory is missing {automation_flag} repos: " + ", ".join(
        missing_from_inventory
    )
    return tuple(configured)


def gh_get(github_client: requests.Session, url: str, **params: object) -> requests.Response:
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


def gh_json_object(github_client: requests.Session, url: str, **params: object) -> JsonObject:
    """Return an object JSON response with endpoint context in failures."""
    response = gh_get(github_client, url, **params)
    assert response.status_code == 200, f"GitHub API GET failed: {url} -> {response.status_code}: {response.text[:500]}"
    payload = cast(object, response.json())
    assert isinstance(payload, dict), f"GitHub API GET expected object: {url}"
    return cast(JsonObject, payload)


def gh_json_list(github_client: requests.Session, url: str, **params: object) -> list[JsonObject]:
    """Return a list JSON response with endpoint context in failures."""
    response = gh_get(github_client, url, **params)
    assert response.status_code == 200, f"GitHub API GET failed: {url} -> {response.status_code}: {response.text[:500]}"
    payload = cast(object, response.json())
    assert isinstance(payload, list), f"GitHub API GET expected list: {url}"
    return cast(list[JsonObject], payload)


def nested_object(payload: Mapping[str, object], key: str) -> JsonObject:
    """Return a nested object value, or an empty object when absent/malformed."""
    value = payload.get(key)
    return cast(JsonObject, value) if isinstance(value, dict) else {}


def content_sha(github_client: requests.Session, full_repo: str, path: str) -> str | None:
    """Return a repository content SHA, or None when the path is absent."""
    response = gh_get(github_client, f"{GITHUB_API_URL}/repos/{full_repo}/contents/{path}")
    if response.status_code == 404:
        return None
    assert response.status_code == 200, (
        f"{full_repo}: failed to read {path}: {response.status_code}: {response.text[:500]}"
    )
    payload = cast(object, response.json())
    assert isinstance(payload, dict), f"{full_repo}: unexpected content response for {path}"
    content_payload = cast(JsonObject, payload)
    sha = content_payload.get("sha")
    assert sha is None or isinstance(sha, str), f"{full_repo}: unexpected SHA value for {path}"
    return sha


def object_login(payload: Mapping[str, object], key: str = "user") -> str | None:
    """Return nested user/app login from a GitHub response object."""
    login = nested_object(payload, key).get("login")
    return login if isinstance(login, str) else None


def pr_number(payload: Mapping[str, object]) -> int:
    """Return a pull request number with a clear failure if GitHub returns malformed data."""
    number = payload.get("number")
    assert isinstance(number, int), f"Malformed pull request payload without integer number: {payload!r}"
    return number


def test_workflow_presence(github_client: requests.Session, repo_inventory: Mapping[str, object]) -> None:
    """Every managed repo has required automation workflows and config files."""
    failures: list[str] = []
    for repo in repo_names(repo_inventory, "deploy_workflows"):
        full_repo = f"{GITHUB_OWNER}/{repo}"
        for workflow in REQUIRED_WORKFLOWS:
            path = f".github/workflows/{workflow}"
            response = gh_get(github_client, f"{GITHUB_API_URL}/repos/{full_repo}/contents/{path}")
            if response.status_code != 200:
                failures.append(f"{repo}: missing {path} (status {response.status_code})")

        for path in REQUIRED_FILES:
            response = gh_get(github_client, f"{GITHUB_API_URL}/repos/{full_repo}/contents/{path}")
            if response.status_code != 200:
                failures.append(f"{repo}: missing {path} (status {response.status_code})")

    if failures:
        pytest.fail("Missing required fleet files:\n" + "\n".join(failures))


def test_workflow_drift(github_client: requests.Session, repo_inventory: Mapping[str, object]) -> None:
    """Report workflow/config drift against jclee941/.github without failing."""
    drift: list[str] = []
    source_shas = {path: content_sha(github_client, SOURCE_REPO, path) for path in DRIFT_FILES}

    for repo in repo_names(repo_inventory, "deploy_workflows"):
        full_repo = f"{GITHUB_OWNER}/{repo}"
        for path, source_sha in source_shas.items():
            target_sha = content_sha(github_client, full_repo, path)
            if source_sha != target_sha:
                drift.append(f"{repo}: {path} drift source={source_sha or 'missing'} target={target_sha or 'missing'}")

    if drift:
        pytest.xfail("Advisory workflow/config drift detected:\n" + "\n".join(drift))


def test_branch_protection(github_client: requests.Session, repo_inventory: Mapping[str, JsonObject]) -> None:
    """Managed repos enforce required branch-protection contexts and safe settings."""
    failures: list[str] = []
    for repo in repo_names(repo_inventory, "branch_protection"):
        full_repo = f"{GITHUB_OWNER}/{repo}"
        branch = repo_inventory.get(repo, {}).get("default_branch")
        assert isinstance(branch, str), f"{repo}: repo_inventory missing default_branch"
        response = gh_get(github_client, f"{GITHUB_API_URL}/repos/{full_repo}/branches/{branch}/protection")
        if response.status_code != 200:
            failures.append(f"{repo}: missing branch protection on {branch} (status {response.status_code})")
            continue

        protection = gh_json_object(github_client, f"{GITHUB_API_URL}/repos/{full_repo}/branches/{branch}/protection")
        checks = nested_object(protection, "required_status_checks")
        contexts_value = checks.get("contexts")
        contexts: set[str] = set()
        if isinstance(contexts_value, list):
            contexts.update(context for context in contexts_value if isinstance(context, str))
        app_checks = checks.get("checks")
        if isinstance(app_checks, list):
            for check in app_checks:
                check_obj = cast(dict[str, Any], check) if isinstance(check, dict) else {}
                if check_obj:
                    context = check_obj.get("context")
                    if isinstance(context, str):
                        contexts.add(context)
        missing_contexts = set(REQUIRED_CONTEXTS) - contexts
        if missing_contexts:
            failures.append(f"{repo}: missing required contexts on {branch}: {sorted(missing_contexts)}")

        if nested_object(protection, "allow_force_pushes").get("enabled") is not False:
            failures.append(f"{repo}: allow_force_pushes is not False on {branch}")
        if nested_object(protection, "allow_deletions").get("enabled") is not False:
            failures.append(f"{repo}: allow_deletions is not False on {branch}")

    if failures:
        pytest.fail("Branch protection failures:\n" + "\n".join(failures))


def test_recent_workflow_health(github_client: requests.Session, repo_inventory: Mapping[str, object]) -> None:
    """Latest required workflow runs should have successful conclusions."""
    failures: list[str] = []
    for repo in repo_names(repo_inventory, "health_check"):
        full_repo = f"{GITHUB_OWNER}/{repo}"
        for label, candidates in WORKFLOW_HEALTH_CANDIDATES.items():
            latest_run: JsonObject | None = None
            chosen_workflow = ""
            for workflow in candidates:
                response = gh_get(
                    github_client,
                    f"{GITHUB_API_URL}/repos/{full_repo}/actions/workflows/{workflow}/runs",
                    per_page=1,
                )
                if response.status_code == 404:
                    continue
                if response.status_code != 200:
                    failures.append(f"{repo}: cannot read {workflow} runs (status {response.status_code})")
                    continue

                payload = cast(object, response.json())
                assert isinstance(payload, dict), f"{repo}: malformed workflow runs response for {workflow}"
                runs = cast(JsonObject, payload).get("workflow_runs")
                if isinstance(runs, list) and runs and isinstance(runs[0], dict):
                    latest_run = cast(JsonObject, runs[0])
                    chosen_workflow = workflow
                    break

            if latest_run is None:
                failures.append(f"{repo}: no recent run found for {label} candidates={candidates}")
                continue

            conclusion = latest_run.get("conclusion")
            status = latest_run.get("status")
            if status != "completed" or conclusion not in SUCCESS_CONCLUSIONS:
                run_url = latest_run.get("html_url")
                failures.append(
                    f"{repo}: latest {label} ({chosen_workflow}) run {run_url} status={status} conclusion={conclusion}"
                )

    if failures:
        pytest.fail("Recent workflow health failures:\n" + "\n".join(failures))


def test_bot_review_activity(github_client: requests.Session, repo_inventory: Mapping[str, object]) -> None:
    """Recent human PRs should have bot comments or reviews."""
    failures: list[str] = []
    for repo in repo_names(repo_inventory, "health_check"):
        full_repo = f"{GITHUB_OWNER}/{repo}"
        pulls = gh_json_list(
            github_client,
            f"{GITHUB_API_URL}/repos/{full_repo}/pulls",
            state="all",
            sort="updated",
            direction="desc",
            per_page=30,
        )
        candidate_prs = [
            pr for pr in pulls if pr.get("draft") is not True and object_login(pr) != "dependabot[bot]"
        ][:10]
        if not candidate_prs:
            failures.append(f"{repo}: no recent non-draft, non-dependabot PRs to inspect")
            continue

        reviewed_prs: list[int] = []
        missing_prs: list[int] = []
        for pr in candidate_prs:
            number = pr_number(pr)
            comments = gh_json_list(
                github_client,
                f"{GITHUB_API_URL}/repos/{full_repo}/issues/{number}/comments",
                per_page=100,
            )
            reviews = gh_json_list(
                github_client,
                f"{GITHUB_API_URL}/repos/{full_repo}/pulls/{number}/reviews",
                per_page=100,
            )
            bot_commented = any(object_login(comment) == BOT_LOGIN for comment in comments)
            bot_reviewed = any(object_login(review) == BOT_LOGIN for review in reviews)
            if bot_commented or bot_reviewed:
                reviewed_prs.append(number)
            else:
                missing_prs.append(number)

        if not reviewed_prs:
            failures.append(f"{repo}: no bot activity in recent PRs {missing_prs}")

    if failures:
        pytest.fail("Missing bot review activity:\n" + "\n".join(failures))


def test_github_app_installation(github_client: requests.Session, repo_inventory: Mapping[str, object]) -> None:
    """The jclee-bot GitHub App should be installed on every managed repo."""
    failures: list[str] = []
    for repo in repo_names(repo_inventory, "health_check"):
        full_repo = f"{GITHUB_OWNER}/{repo}"
        response = gh_get(github_client, f"{GITHUB_API_URL}/repos/{full_repo}/installation")
        if response.status_code == 401:
            # OAuth/PAT tokens cannot access GitHub App installation endpoint
            pytest.skip("GitHub App installation API requires App JWT (OAuth/PAT gets 401)")
        if response.status_code != 200:
            failures.append(f"{repo}: missing GitHub App installation endpoint (status {response.status_code})")
            continue

        payload = cast(object, response.json())
        assert isinstance(payload, dict), f"{repo}: malformed installation response"
        app = nested_object(cast(JsonObject, payload), "app")
        if app.get("slug") != APP_SLUG:
            failures.append(f"{repo}: expected app slug {APP_SLUG}, got {app.get('slug')!r}")

    if failures:
        pytest.fail("GitHub App installation failures:\n" + "\n".join(failures))
