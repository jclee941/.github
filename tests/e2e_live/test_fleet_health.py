"""Read-only live fleet health checks for managed jclee941 repositories."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
import requests

from .fleet_health_helpers import (
    BOT_LOGIN,
    JsonObject,
    content_sha,
    gh_get,
    gh_json_list,
    gh_json_object,
    nested_object,
    object_login,
    pr_number,
    repo_names,
)
from .repo_config import GITHUB_API_URL, GITHUB_OWNER, REQUIRED_CONTEXTS, REQUIRED_FILES, REQUIRED_WORKFLOWS, JsonValue

pytestmark = pytest.mark.readonly

SOURCE_REPO = f"{GITHUB_OWNER}/jclee-bot"
APP_SLUG = "jclee-bot"

DRIFT_FILES = tuple(f".github/workflows/{workflow}" for workflow in REQUIRED_WORKFLOWS) + tuple(REQUIRED_FILES)

def test_workflow_presence(github_client: requests.Session, repo_inventory: Mapping[str, JsonValue]) -> None:
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


def test_workflow_drift(github_client: requests.Session, repo_inventory: Mapping[str, JsonValue]) -> None:
    """Report workflow/config drift against jclee941/jclee-bot without failing."""
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
                check_obj = check if isinstance(check, dict) else {}
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


def test_app_pr_activity(github_client: requests.Session, repo_inventory: Mapping[str, JsonValue]) -> None:
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
            app_reviewed = any(object_login(review) == BOT_LOGIN for review in reviews)
            if bot_commented or app_reviewed:
                reviewed_prs.append(number)
            else:
                missing_prs.append(number)

        if not reviewed_prs:
            failures.append(f"{repo}: no bot activity in recent PRs {missing_prs}")

    if failures:
        pytest.fail("Missing bot review activity:\n" + "\n".join(failures))


def test_github_app_installation(github_client: requests.Session, repo_inventory: Mapping[str, JsonValue]) -> None:
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

        payload = response.json()
        assert isinstance(payload, dict), f"{repo}: malformed installation response"
        app = nested_object(payload, "app")
        if app.get("slug") != APP_SLUG:
            failures.append(f"{repo}: expected app slug {APP_SLUG}, got {app.get('slug')!r}")

    if failures:
        pytest.fail("GitHub App installation failures:\n" + "\n".join(failures))
