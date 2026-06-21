from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import requests

GITHUB_API = "https://api.github.com"
DOCS_SYNC_TITLE = "docs: sync standard templates from jclee941/.github"
AUTOMATION_TITLE_PREFIXES = ("chore(deps", "build(deps", DOCS_SYNC_TITLE)
AUTOMATION_HEAD_PREFIXES = ("dependabot/", "renovate/", "bot/", "jclee-bot/", "docs-sync/")
FAILED_CHECK_CONCLUSIONS = frozenset({"failure", "timed_out", "startup_failure", "action_required"})
FAILED_STATUS_STATES = frozenset({"failure", "error"})
PENDING_CHECK_STATUSES = frozenset({"queued", "requested", "in_progress", "waiting", "pending"})
ACTIVE_RUN_STATUSES = ("queued", "in_progress", "requested", "waiting")
FAILED_PR_STALE_HOURS = 1
PENDING_PR_STALE_HOURS = 2
ACTIVE_RUN_STALE_MINUTES = 30
PROTECTED_BRANCHES = frozenset({"master"})
PR_CLEANUP_MESSAGE = (
    "jclee-bot 자동 유지보수: 오래된 자동화 PR이 실패/대기 상태로 남아 있어 닫습니다.\n\n"
    "필요한 변경이면 최신 기준에서 자동화가 다시 생성합니다."
)


@dataclass(frozen=True, slots=True)
class CheckSummary:
    failed: tuple[str, ...]
    pending: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PrCleanupPlan:
    number: int
    reason: str
    head_ref: str
    can_delete_branch: bool


@dataclass(frozen=True, slots=True)
class RunCleanupPlan:
    run_id: int
    status: str
    force: bool


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}


def parse_github_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _item_time(item: dict[str, Any]) -> datetime | None:
    value = str(item.get("updated_at") or item.get("created_at") or "")
    return parse_github_time(value) if value else None


def _age_hours(item: dict[str, Any], now: datetime) -> float:
    item_time = _item_time(item)
    if item_time is None:
        return 0.0
    return (now - item_time).total_seconds() / 3600


def _paginate(token: str, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        resp = requests.get(
            f"{GITHUB_API}{path}",
            headers=_headers(token),
            params={**(params or {}), "per_page": 100, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not isinstance(batch, list) or not batch:
            return items
        items.extend(batch)
        if len(batch) < 100:
            return items
        page += 1


def _paginate_key(token: str, path: str, key: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        resp = requests.get(
            f"{GITHUB_API}{path}",
            headers=_headers(token),
            params={**(params or {}), "per_page": 100, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        batch = data.get(key, []) if isinstance(data, dict) else []
        if not isinstance(batch, list) or not batch:
            return items
        items.extend(batch)
        if len(batch) < 100:
            return items
        page += 1


def _nested_str(item: dict[str, Any], *keys: str) -> str:
    current: Any = item
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return str(current or "")


def _is_automation_pr(pr: dict[str, Any]) -> bool:
    title = str(pr.get("title") or "")
    head_ref = _nested_str(pr, "head", "ref")
    return title.startswith(AUTOMATION_TITLE_PREFIXES) or head_ref.startswith(AUTOMATION_HEAD_PREFIXES)


def _can_delete_head_branch(pr: dict[str, Any], repo_full_name: str) -> bool:
    head_ref = _nested_str(pr, "head", "ref")
    head_repo = _nested_str(pr, "head", "repo", "full_name")
    return bool(head_ref) and head_ref not in PROTECTED_BRANCHES and head_repo == repo_full_name


def plan_pr_cleanup(
    pr: dict[str, Any],
    *,
    checks: CheckSummary,
    repo_full_name: str,
    now: datetime,
) -> PrCleanupPlan | None:
    number = int(pr.get("number", 0) or 0)
    head_ref = _nested_str(pr, "head", "ref")
    if number <= 0:
        return None

    title = str(pr.get("title") or "")
    if title.startswith(DOCS_SYNC_TITLE):
        return PrCleanupPlan(number, "docs-sync", head_ref, _can_delete_head_branch(pr, repo_full_name))

    if not _is_automation_pr(pr):
        return None

    age_hours = _age_hours(pr, now)
    if checks.failed and age_hours >= FAILED_PR_STALE_HOURS:
        return PrCleanupPlan(number, "failed-checks", head_ref, _can_delete_head_branch(pr, repo_full_name))
    if checks.pending and age_hours >= PENDING_PR_STALE_HOURS:
        return PrCleanupPlan(number, "pending-checks", head_ref, _can_delete_head_branch(pr, repo_full_name))
    return None


def plan_run_cleanup(run: dict[str, Any], *, now: datetime) -> RunCleanupPlan | None:
    run_id = int(run.get("id", 0) or 0)
    status = str(run.get("status") or "")
    created_at = str(run.get("created_at") or "")
    if run_id <= 0 or status not in ACTIVE_RUN_STATUSES or not created_at:
        return None
    age_minutes = (now - parse_github_time(created_at)).total_seconds() / 60
    if age_minutes < ACTIVE_RUN_STALE_MINUTES:
        return None
    return RunCleanupPlan(run_id=run_id, status=status, force=status == "in_progress")


def list_open_pull_requests(*, token: str, repo_full_name: str) -> list[dict[str, Any]]:
    return _paginate(token, f"/repos/{repo_full_name}/pulls", {"state": "open"})


def commit_check_summary(*, token: str, repo_full_name: str, sha: str) -> CheckSummary:
    failed: set[str] = set()
    pending: set[str] = set()
    check_runs = _paginate_key(token, f"/repos/{repo_full_name}/commits/{sha}/check-runs", "check_runs")
    for run in check_runs:
        name = str(run.get("name") or run.get("external_id") or "check-run")
        status = str(run.get("status") or "")
        conclusion = str(run.get("conclusion") or "")
        if status != "completed" or status in PENDING_CHECK_STATUSES:
            pending.add(name)
        elif conclusion in FAILED_CHECK_CONCLUSIONS:
            failed.add(name)

    resp = requests.get(
        f"{GITHUB_API}/repos/{repo_full_name}/commits/{sha}/status",
        headers=_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    statuses = data.get("statuses", []) if isinstance(data, dict) else []
    for status_item in statuses:
        if not isinstance(status_item, dict):
            continue
        name = str(status_item.get("context") or "status")
        state = str(status_item.get("state") or "")
        if state in FAILED_STATUS_STATES:
            failed.add(name)
        elif state == "pending":
            pending.add(name)

    return CheckSummary(failed=tuple(sorted(failed)), pending=tuple(sorted(pending)))


def list_active_workflow_runs(*, token: str, repo_full_name: str) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    seen: set[int] = set()
    for status in ACTIVE_RUN_STATUSES:
        for run in _paginate_key(token, f"/repos/{repo_full_name}/actions/runs", "workflow_runs", {"status": status}):
            run_id = int(run.get("id", 0) or 0)
            if run_id > 0 and run_id not in seen:
                seen.add(run_id)
                runs.append(run)
    return runs


def comment_pr(*, token: str, repo_full_name: str, pr_number: int) -> None:
    resp = requests.post(
        f"{GITHUB_API}/repos/{repo_full_name}/issues/{pr_number}/comments",
        headers=_headers(token),
        json={"body": PR_CLEANUP_MESSAGE},
        timeout=30,
    )
    resp.raise_for_status()


def close_pr(*, token: str, repo_full_name: str, pr_number: int) -> None:
    resp = requests.patch(
        f"{GITHUB_API}/repos/{repo_full_name}/issues/{pr_number}",
        headers=_headers(token),
        json={"state": "closed"},
        timeout=30,
    )
    resp.raise_for_status()


def delete_head_branch(*, token: str, repo_full_name: str, head_ref: str) -> None:
    encoded_ref = quote(head_ref, safe="")
    resp = requests.delete(
        f"{GITHUB_API}/repos/{repo_full_name}/git/refs/heads/{encoded_ref}",
        headers=_headers(token),
        timeout=30,
    )
    if resp.status_code not in {204, 404, 422}:
        resp.raise_for_status()


def cancel_workflow_run(*, token: str, repo_full_name: str, run_id: int, force: bool) -> None:
    operation = "force-cancel" if force else "cancel"
    resp = requests.post(
        f"{GITHUB_API}/repos/{repo_full_name}/actions/runs/{run_id}/{operation}",
        headers=_headers(token),
        timeout=30,
    )
    if resp.status_code not in {202, 404, 409}:
        resp.raise_for_status()


def _head_sha(pr: dict[str, Any]) -> str:
    return _nested_str(pr, "head", "sha")


def maintain_pull_requests(*, token: str, repo_full_name: str, dry_run: bool, now: datetime | None = None) -> list[str]:
    current_time = now or datetime.now(UTC)
    actions: list[str] = []

    try:
        pull_requests = list_open_pull_requests(token=token, repo_full_name=repo_full_name)
    except requests.RequestException as exc:
        actions.append(f"pr-list-error:{type(exc).__name__}")
        pull_requests = []

    for pr in pull_requests:
        sha = _head_sha(pr)
        checks = CheckSummary((), ())
        plan = plan_pr_cleanup(pr, checks=checks, repo_full_name=repo_full_name, now=current_time)
        if plan is None and sha:
            try:
                checks = commit_check_summary(token=token, repo_full_name=repo_full_name, sha=sha)
            except requests.RequestException as exc:
                number = int(pr.get("number", 0) or 0)
                actions.append(f"pr-checks-error:{number}:{type(exc).__name__}")
                continue
        plan = plan_pr_cleanup(pr, checks=checks, repo_full_name=repo_full_name, now=current_time)
        if plan is None:
            continue
        actions.append(f"close-pr:{plan.number}:{plan.reason}")
        if plan.can_delete_branch:
            actions.append(f"delete-pr-branch:{plan.number}")
        if dry_run:
            continue
        comment_pr(token=token, repo_full_name=repo_full_name, pr_number=plan.number)
        close_pr(token=token, repo_full_name=repo_full_name, pr_number=plan.number)
        if plan.can_delete_branch:
            delete_head_branch(token=token, repo_full_name=repo_full_name, head_ref=plan.head_ref)

    try:
        workflow_runs = list_active_workflow_runs(token=token, repo_full_name=repo_full_name)
    except requests.RequestException as exc:
        actions.append(f"run-list-error:{type(exc).__name__}")
        workflow_runs = []

    for run in workflow_runs:
        plan = plan_run_cleanup(run, now=current_time)
        if plan is None:
            continue
        prefix = "force-cancel" if plan.force else "cancel"
        actions.append(f"{prefix}-run:{plan.run_id}:{plan.status}")
        if not dry_run:
            cancel_workflow_run(token=token, repo_full_name=repo_full_name, run_id=plan.run_id, force=plan.force)

    return actions
