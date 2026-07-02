from __future__ import annotations

from pathlib import Path
from typing import Final

import requests

from jclee_bot import issue_maintenance, workflow_issue_automation
from jclee_bot.downstream_ci_inventory import DEFAULT_CONFIG_PATH, ManagedRepo, load_health_repos
from jclee_bot.downstream_ci_issues import parsed_ci_failure_issues
from jclee_bot.downstream_ci_runs import latest_snapshots_by_workflow, workflow_snapshots
from jclee_bot.json_boundary import JsonObject, JsonValue
from jclee_bot.payload_parsing import default_branch_from_payload, repo_full_name_from_payload
from jclee_bot.repo_standardization import parse_repo_selection

OWNER: Final = "jclee941"
COMPLETED_STATUS: Final = "completed"
_workflow_snapshots = workflow_snapshots


def run_app_ci_failure_issues(
    *,
    app_id: str,
    private_key: str,
    payload: JsonObject,
    workflow_run: workflow_issue_automation.WorkflowRun | None,
) -> JsonObject:
    if payload.get("scope") == "managed_repos" or payload.get("all_repos") is True:
        return run_downstream_ci_sweep(
            app_id=app_id,
            private_key=private_key,
            owner=str(payload.get("owner") or OWNER),
            dry_run=bool(payload.get("dry_run", False)),
            repo_names=payload.get("repos"),
            config_path=DEFAULT_CONFIG_PATH,
        )
    return run_single_repo_ci_failure_issues(
        app_id=app_id,
        private_key=private_key,
        payload=payload,
        workflow_run=workflow_run,
    )


def run_single_repo_ci_failure_issues(
    *,
    app_id: str,
    private_key: str,
    payload: JsonObject,
    workflow_run: workflow_issue_automation.WorkflowRun | None,
) -> JsonObject:
    repo_full_name = repo_full_name_from_payload(payload)
    default_branch = default_branch_from_payload(payload)
    dry_run = bool(payload.get("dry_run", False))
    if not repo_full_name:
        return {"dry_run": dry_run, "actions": [], "error": "repository is required"}
    token = workflow_issue_automation.installation_token_for_repo(
        app_id=app_id,
        private_key=private_key,
        repo_full_name=repo_full_name,
    )
    if not token:
        return {"dry_run": dry_run, "actions": [], "error": "installation token unavailable"}
    if workflow_run is None:
        actions = workflow_issue_automation.sweep_legacy_failure_issues(
            token=token,
            repo_full_name=repo_full_name,
            default_branch=default_branch,
            dry_run=dry_run,
        )
    else:
        actions = workflow_issue_automation.record_workflow_run(
            token=token,
            repo_full_name=repo_full_name,
            run=workflow_run,
            default_branch=default_branch,
            dry_run=dry_run,
        )
    actions_json: list[JsonValue] = list(actions)
    return {"dry_run": dry_run, "repository": repo_full_name, "actions": actions_json}


def run_downstream_ci_sweep(
    *,
    app_id: str,
    private_key: str,
    owner: str,
    dry_run: bool,
    repo_names: JsonValue,
    config_path: Path = DEFAULT_CONFIG_PATH,
    run_limit: int = 50,
) -> JsonObject:
    if owner != OWNER:
        empty_actions: list[JsonValue] = []
        return {
            "dry_run": dry_run,
            "owner": owner,
            "scope": "managed_repos",
            "actions": empty_actions,
            "error": "owner must be jclee941",
        }
    repos = load_health_repos(config_path)
    selected = parse_repo_selection(repo_names, frozenset(repo.name for repo in repos))
    targets = tuple(repo for repo in repos if selected is None or repo.name in selected)
    repo_results: list[JsonValue] = []
    flat_actions: list[str] = []
    failures = 0
    for repo in targets:
        result = sweep_managed_repo(
            app_id=app_id,
            private_key=private_key,
            owner=owner,
            repo=repo,
            dry_run=dry_run,
            run_limit=run_limit,
        )
        repo_results.append(result)
        repo_actions = result.get("actions")
        if isinstance(repo_actions, list):
            flat_actions.extend(f"{repo.name}:{action}" for action in repo_actions if isinstance(action, str))
        if result.get("status") == "failed":
            failures += 1
    actions_json: list[JsonValue] = list(flat_actions)
    return {
        "dry_run": dry_run,
        "owner": owner,
        "scope": "managed_repos",
        "actions": actions_json,
        "repositories": repo_results,
        "summary": {"status": "failed" if failures else "ok", "checked": len(targets), "failed": failures},
    }


def sweep_managed_repo(
    *,
    app_id: str,
    private_key: str,
    owner: str,
    repo: ManagedRepo,
    dry_run: bool,
    run_limit: int,
) -> JsonObject:
    try:
        repo_full_name = repo.full_name(owner)
        token = workflow_issue_automation.installation_token_for_repo(
            app_id=app_id,
            private_key=private_key,
            repo_full_name=repo_full_name,
        )
        if not token:
            empty_actions: list[JsonValue] = []
            return {
                "repo": repo.name,
                "status": "failed",
                "actions": empty_actions,
                "error": "installation token unavailable",
            }
        actions = sweep_repo_ci(
            token=token,
            repo_full_name=repo_full_name,
            default_branch=repo.default_branch,
            dry_run=dry_run,
            run_limit=run_limit,
        )
    except requests.RequestException as exc:
        return {
            "repo": repo.name,
            "status": "failed",
            "actions": [],
            "error": type(exc).__name__,
            "detail": "request failed while sweeping repository",
        }
    actions_json: list[JsonValue] = list(actions)
    return {"repo": repo.name, "status": "ok", "default_branch": repo.default_branch, "actions": actions_json}


def sweep_repo_ci(
    *,
    token: str,
    repo_full_name: str,
    default_branch: str,
    dry_run: bool,
    run_limit: int,
) -> list[str]:
    actions: list[str] = []
    snapshots = latest_snapshots_by_workflow(
        _workflow_snapshots(token=token, repo_full_name=repo_full_name, run_limit=run_limit, branch=default_branch)
    )
    if not snapshots:
        return ["noop:no-workflow-runs"]
    for snapshot in snapshots:
        if snapshot.status != COMPLETED_STATUS:
            actions.append(f"defer-active:{snapshot.run.name}:{snapshot.status}")
            continue
        if workflow_issue_automation.normalize_conclusion(snapshot.run.conclusion) == "success":
            actions.extend(
                close_stale_ci_failures_for_workflow(
                    token=token,
                    repo_full_name=repo_full_name,
                    run=snapshot.run,
                    dry_run=dry_run,
                )
            )
            continue
        actions.extend(
            workflow_issue_automation.record_workflow_run(
                token=token,
                repo_full_name=repo_full_name,
                run=snapshot.run,
                default_branch=default_branch,
                dry_run=dry_run,
            )
        )
    return actions or ["noop:no-current-ci-state-change"]


def close_stale_ci_failures_for_workflow(
    *,
    token: str,
    repo_full_name: str,
    run: workflow_issue_automation.WorkflowRun,
    dry_run: bool,
) -> list[str]:
    actions: list[str] = []
    for issue in parsed_ci_failure_issues(token=token, repo_full_name=repo_full_name):
        if issue.workflow_name != run.name:
            continue
        actions.append(f"close-stale-ci-failure:{issue.number}:{run.name}")
        if dry_run:
            continue
        body = (
            f"Resolved: latest {run.name} run {run.run_id} concluded success on "
            f"{run.head_sha}.\n\n_jclee-bot에의해자동화됨._"
        )
        issue_maintenance.comment_issue(
            token=token,
            repo_full_name=repo_full_name,
            issue_number=issue.number,
            body=body,
        )
        issue_maintenance.close_issue(token=token, repo_full_name=repo_full_name, issue_number=issue.number)
    return actions
