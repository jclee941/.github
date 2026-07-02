from __future__ import annotations

import fcntl
import logging
import os
from collections.abc import Callable
from typing import Any, Literal

import jclee_bot.downstream_ci_sweep as downstream_ci_sweep
from jclee_bot import (
    gitops_automation,
    issue_commands,
    issue_maintenance,
    issue_management,
    native_health,
    workflow_issue_automation,
)
from jclee_bot.payload_parsing import repo_full_name_from_payload

type MaintenanceMode = Literal["safe", "force"]
ISSUE_MAINTENANCE_EVENTS = frozenset({"issues", "pull_request", "create", "pull_request_review"})
CI_FAILURE_EVENTS = frozenset({"workflow_run"})
logger = logging.getLogger(__name__)


def int_or_zero(value: Any) -> int:
    if isinstance(value, bool | float):
        return 0
    try:
        return int(value or 0)
    except (OverflowError, TypeError, ValueError):
        return 0


def parse_maintenance_mode(value: Any) -> MaintenanceMode | None:
    if value is None or value == "":
        return "safe"
    if value == "safe" or value == "force":
        return value
    return None


def run_issue_management_for_payload(
    payload: dict[str, Any],
    event: str,
    *,
    installation_token_fn: Callable[[int], str | None],
) -> dict[str, Any]:
    installation_id = payload.get("installation", {}).get("id", 0)
    try:
        token = installation_token_fn(installation_id)
    except Exception:  # noqa: BLE001 - issue automation must not break webhooks
        token = None
    if not token:
        return {"actions": []}
    try:
        return issue_management.handle_issue_event(token=token, payload=payload, event=event)
    except Exception:  # noqa: BLE001 - one failed issue action must not break reviews/checks
        return {"actions": []}


def run_gitops_automation_for_payload(
    payload: dict[str, Any],
    event: str,
    *,
    installation_token_fn: Callable[[int], str | None],
) -> dict[str, Any]:
    installation_id = payload.get("installation", {}).get("id", 0)
    try:
        token = installation_token_fn(installation_id)
    except Exception:  # noqa: BLE001 - GitOps automation must not break webhooks
        token = None
    if not token:
        return {"actions": []}
    try:
        if event == "create":
            return gitops_automation.handle_create_event(token=token, payload=payload, event=event)
        if event in {"pull_request", "pull_request_review"}:
            return gitops_automation.handle_pull_request_auto_merge(token=token, payload=payload, event=event)
    except Exception:  # noqa: BLE001 - webhook ack must not depend on GitOps side effects
        return {"actions": []}
    return {"actions": []}


def run_app_issue_maintenance(
    *,
    app_id: str,
    private_key: str,
    owner: str,
    dry_run: bool,
    mode: MaintenanceMode,
) -> dict[str, Any]:
    try:
        return issue_maintenance.run_app_maintenance(
            app_id=app_id,
            private_key=private_key,
            owner=owner,
            dry_run=dry_run,
            mode=mode,
        )
    except Exception as exc:  # noqa: BLE001 - background maintenance must not crash the App worker
        logger.exception("App issue maintenance failed")
        return {
            "dry_run": dry_run,
            "mode": mode,
            "repositories": [],
            "error": "issue maintenance failed",
            "error_type": type(exc).__name__,
        }


def issue_maintenance_lock_path() -> str:
    return os.environ.get("JCLEE_BOT_ISSUE_MAINTENANCE_LOCK_PATH", "/tmp/jclee-bot-issue-maintenance.lock")


def acquire_issue_maintenance_lock() -> int | None:
    fd = os.open(issue_maintenance_lock_path(), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return fd


def release_issue_maintenance_lock(fd: int) -> None:
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)


def run_event_issue_maintenance_once(
    event: str,
    *,
    run_app_issue_maintenance_fn: Callable[..., dict[str, Any]] = run_app_issue_maintenance,
) -> dict[str, Any]:
    if event not in ISSUE_MAINTENANCE_EVENTS:
        return {"skipped": "event does not require issue maintenance", "event": event}
    app_id = os.environ.get("GITHUB_APP_ID", "")
    private_key = os.environ.get("GITHUB_PRIVATE_KEY", "")
    if not app_id or not private_key:
        return {"skipped": "github app credentials unavailable", "event": event}
    fd = acquire_issue_maintenance_lock()
    if fd is None:
        return {"skipped": "issue maintenance already running", "event": event}
    try:
        result = run_app_issue_maintenance_fn(
            app_id=app_id,
            private_key=private_key,
            owner=os.environ.get("JCLEE_BOT_ISSUE_MAINTENANCE_OWNER", "jclee941"),
            dry_run=False,
            mode="force",
        )
        if result.get("error"):
            logger.error("Event issue maintenance failed after %s webhook: %s", event, result)
        else:
            logger.info("Event issue maintenance completed after %s webhook", event)
        return result
    finally:
        release_issue_maintenance_lock(fd)


def workflow_run_from_payload(payload: dict[str, Any]) -> workflow_issue_automation.WorkflowRun | None:
    run = payload.get("workflow_run")
    if not isinstance(run, dict):
        return None
    run_id = int_or_zero(run.get("id"))
    if run_id <= 0:
        return None
    pull_requests = run.get("pull_requests")
    pr_number = run.get("pr_number")
    if isinstance(pull_requests, list) and pull_requests:
        first_pr = pull_requests[0]
        if isinstance(first_pr, dict):
            pr_number = first_pr.get("number")
    return workflow_issue_automation.WorkflowRun(
        name=str(run.get("name") or ""),
        head_sha=str(run.get("head_sha") or ""),
        run_id=run_id,
        conclusion=str(run.get("conclusion") or ""),
        pr_number=int_or_zero(pr_number),
        run_url=str(run.get("run_url") or run.get("html_url") or ""),
    )


def run_app_ci_failure_issues(*, app_id: str, private_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    return downstream_ci_sweep.run_app_ci_failure_issues(
        app_id=app_id,
        private_key=private_key,
        payload=payload,
        workflow_run=workflow_run_from_payload(payload),
    )


def run_event_ci_failure_issues(
    payload: dict[str, Any],
    event: str,
    *,
    run_app_ci_failure_issues_fn: Callable[..., dict[str, Any]] = run_app_ci_failure_issues,
) -> dict[str, Any]:
    if event not in CI_FAILURE_EVENTS:
        return {"skipped": "event does not require ci failure maintenance", "event": event}
    if payload.get("action") not in {None, "completed"}:
        return {"skipped": "workflow_run is not completed", "event": event}
    app_id = os.environ.get("GITHUB_APP_ID", "")
    private_key = os.environ.get("GITHUB_PRIVATE_KEY", "")
    if not app_id or not private_key:
        return {"skipped": "github app credentials unavailable", "event": event}
    try:
        managed_payload = dict(payload)
        managed_payload["scope"] = "managed_repos"
        result = run_app_ci_failure_issues_fn(app_id=app_id, private_key=private_key, payload=managed_payload)
        logger.info("Event CI-failure maintenance completed after %s webhook", event)
        return result
    except Exception as exc:  # noqa: BLE001 - webhook ack must not depend on CI-failure side effects
        logger.exception("Event CI-failure maintenance failed after %s webhook", event)
        return {
            "event": event,
            "actions": [],
            "error": "ci failure maintenance failed",
            "error_type": type(exc).__name__,
        }


def run_app_issue_commands(*, app_id: str, private_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    repo_full_name = repo_full_name_from_payload(payload)
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
    result = issue_commands.run_issue_commands(token=token, payload=payload)
    result["repository"] = repo_full_name
    return result


def run_app_native_health(*, app_id: str, private_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    repo_full_name = repo_full_name_from_payload(payload)
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
    return native_health.run_native_health(token=token, payload=payload)
