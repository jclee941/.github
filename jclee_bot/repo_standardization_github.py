from __future__ import annotations

from typing import Final, cast

import requests

from jclee_bot import workflow_issue_automation
from jclee_bot.github_api_client import GITHUB_API, headers
from jclee_bot.github_retry import (
    MAX_GITHUB_REQUEST_ATTEMPTS,
    github_request,
    is_retryable_request_exception,
    sleep_before_retry,
)
from jclee_bot.json_boundary import JsonObject, is_object_mapping, json_object, json_value, object_dict, object_list
from jclee_bot.repo_standardization_types import RepositoryAction, StandardizationStep, step_status

TARGET_BRANCH: Final = "master"
DEFAULT_RULESET_NAME: Final = "Default Branch Protection"
REQUIRED_CHECKS: Final = (
    "jclee-bot / pr-metadata",
    "jclee-bot / secret-scan",
    "jclee-bot / actionlint",
)


def branch_protection_step(
    *,
    app_id: str,
    private_key: str,
    owner: str,
    dry_run: bool,
    repo_names: tuple[str, ...],
) -> StandardizationStep:
    actions: list[RepositoryAction] = []
    for repo_name in repo_names:
        full_repo = f"{owner}/{repo_name}"
        token = workflow_issue_automation.installation_token_for_repo(
            app_id=app_id,
            private_key=private_key,
            repo_full_name=full_repo,
        )
        if not token:
            actions.append(RepositoryAction(repo=full_repo, action="failed", detail="installation token unavailable"))
            continue
        try:
            actions.append(apply_branch_protection(token=token, full_repo=full_repo, dry_run=dry_run))
        except requests.RequestException as exc:
            actions.append(RepositoryAction(repo=full_repo, action="failed", detail=str(exc)))
    return StandardizationStep(name="branch-protection", status=step_status(actions), repositories=tuple(actions))


def apply_branch_protection(*, token: str, full_repo: str, dry_run: bool) -> RepositoryAction:
    if dry_run:
        return RepositoryAction(repo=full_repo, action="would_apply")
    _ = github_patch(
        token=token,
        path=f"/repos/{full_repo}",
        payload={"allow_auto_merge": True, "delete_branch_on_merge": True},
    )
    _ = github_put(
        token=token,
        path=f"/repos/{full_repo}/branches/{TARGET_BRANCH}/protection",
        payload=branch_protection_payload(),
    )
    return RepositoryAction(repo=full_repo, action="applied")


def branch_protection_payload() -> JsonObject:
    return {
        "required_status_checks": {
            "strict": False,
            "contexts": list(REQUIRED_CHECKS),
        },
        "enforce_admins": False,
        "required_pull_request_reviews": None,
        "restrictions": None,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "block_creations": False,
        "required_linear_history": False,
        "required_conversation_resolution": False,
        "lock_branch": False,
        "allow_fork_syncing": True,
    }


def rulesets_step(
    *,
    app_id: str,
    private_key: str,
    owner: str,
    dry_run: bool,
    repo_names: tuple[str, ...],
) -> StandardizationStep:
    actions: list[RepositoryAction] = []
    for repo_name in repo_names:
        full_repo = f"{owner}/{repo_name}"
        token = workflow_issue_automation.installation_token_for_repo(
            app_id=app_id,
            private_key=private_key,
            repo_full_name=full_repo,
        )
        if not token:
            actions.append(RepositoryAction(repo=full_repo, action="failed", detail="installation token unavailable"))
            continue
        try:
            actions.append(upsert_ruleset(token=token, full_repo=full_repo, dry_run=dry_run))
        except requests.RequestException as exc:
            actions.append(RepositoryAction(repo=full_repo, action="failed", detail=str(exc)))
    return StandardizationStep(name="rulesets", status=step_status(actions), repositories=tuple(actions))


def upsert_ruleset(*, token: str, full_repo: str, dry_run: bool) -> RepositoryAction:
    existing_id = find_ruleset_id(token=token, full_repo=full_repo, ruleset_name=DEFAULT_RULESET_NAME)
    if dry_run:
        detail = "update existing ruleset" if existing_id else "create ruleset"
        return RepositoryAction(repo=full_repo, action="would_apply", detail=detail)
    if existing_id:
        _ = github_put(
            token=token,
            path=f"/repos/{full_repo}/rulesets/{existing_id}",
            payload=ruleset_payload(),
        )
    else:
        create_ruleset(token=token, full_repo=full_repo)
    return RepositoryAction(repo=full_repo, action="applied")


def create_ruleset(*, token: str, full_repo: str) -> None:
    for attempt in range(1, MAX_GITHUB_REQUEST_ATTEMPTS + 1):
        try:
            _ = github_post_once(token=token, path=f"/repos/{full_repo}/rulesets", payload=ruleset_payload())
            return
        except requests.RequestException as exc:
            if not is_retryable_request_exception(exc):
                raise
            created_id = find_ruleset_id(token=token, full_repo=full_repo, ruleset_name=DEFAULT_RULESET_NAME)
            if created_id is not None:
                return
            if attempt == MAX_GITHUB_REQUEST_ATTEMPTS:
                raise
            sleep_before_retry()
    raise RuntimeError("unreachable GitHub ruleset creation retry state")


def find_ruleset_id(*, token: str, full_repo: str, ruleset_name: str) -> int | None:
    response = github_request(
        lambda: requests.get(f"{GITHUB_API}/repos/{full_repo}/rulesets", headers=headers(token), timeout=30)
    )
    raw_rulesets = object_list(json_value(response_json(response)), "rulesets response must be a JSON array")
    for item in raw_rulesets:
        if not is_object_mapping(item):
            continue
        ruleset = object_dict(item)
        if ruleset.get("name") != ruleset_name:
            continue
        ruleset_id = ruleset.get("id")
        if isinstance(ruleset_id, int):
            return ruleset_id
    return None


def ruleset_payload() -> JsonObject:
    return {
        "name": DEFAULT_RULESET_NAME,
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}],
        "conditions": {"ref_name": {"include": [f"refs/heads/{TARGET_BRANCH}"], "exclude": []}},
        "rules": [
            {
                "type": "required_status_checks",
                "parameters": {
                    "required_status_checks": [{"context": context} for context in REQUIRED_CHECKS],
                    "strict_required_status_checks_policy": False,
                },
            },
            {"type": "deletion"},
            {"type": "non_fast_forward"},
        ],
    }


def github_patch(*, token: str, path: str, payload: JsonObject) -> JsonObject:
    response = github_request(
        lambda: requests.patch(f"{GITHUB_API}{path}", headers=headers(token), json=payload, timeout=30)
    )
    return json_object(json_value(response_json(response)), f"PATCH {path}")


def github_put(*, token: str, path: str, payload: JsonObject) -> JsonObject:
    response = github_request(
        lambda: requests.put(f"{GITHUB_API}{path}", headers=headers(token), json=payload, timeout=30)
    )
    raw = json_value(response_json(response)) if response.content else {}
    return json_object(raw, f"PUT {path}")


def github_post_once(*, token: str, path: str, payload: JsonObject) -> JsonObject:
    response = requests.post(f"{GITHUB_API}{path}", headers=headers(token), json=payload, timeout=30)
    response.raise_for_status()
    return json_object(json_value(response_json(response)), f"POST {path}")


def response_json(response: requests.Response) -> object:
    return cast(object, response.json())
