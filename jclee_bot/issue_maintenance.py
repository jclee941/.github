from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import quote

import requests

from jclee_bot import github_checks, issue_management, pr_maintenance
from jclee_bot.github_api_client import GITHUB_API, headers
from jclee_bot.github_app_inventory import app_installations, installation_repositories, managed_repo_names
from jclee_bot.issue_maintenance_rules import (
    issue_stats,
    should_close_duplicate_bot_review,
    should_close_empty_bot_review,
    should_close_stale,
    should_mark_stale,
)
from jclee_bot.repo_health_maintenance import (
    has_bot_owned_issue,
    is_repo_health_issue,
    missing_repo_health_files,
)

SUMMARY_LABELS = ["issue-summary", "bot"]
type MaintenanceMode = Literal["safe", "force"]

STALE_MESSAGE = (
    "이 이슈는 30일 이상 활동이 없어 `stale` 상태로 전환됩니다. "
    "추가 활동이 없으면 7일 후 자동으로 닫힙니다."
)
CLOSE_MESSAGE = "이슈가 7일 이상 활동이 없어 자동으로 닫혔습니다. 필요시 재오픈해주세요."
FORCE_ISSUE_CLEANUP_MESSAGE = (
    "jclee-bot repo-zero 유지보수: 관리 레포 표준화를 위해 열린 이슈를 자동 정리합니다.\n\n"
    "계속 추적해야 하는 항목이면 최신 상태로 다시 열어주세요."
)
DUPLICATE_REVIEW_CLOSE_MESSAGE = (
    "중복된 `jclee-bot` review-finding 이슈로 자동 정리합니다. "
    "원본 이슈 또는 PR에 남은 항목만 추적해주세요."
)
EMPTY_REVIEW_CLOSE_MESSAGE = (
    "`jclee-bot` review-finding 본문에 실제 조치 항목이 없어 자동 정리합니다. "
    "구체적인 finding이 있는 이슈만 추적합니다."
)
REPO_HEALTH_RECOVERED_MESSAGE = (
    "필수 문서 파일이 모두 확인되어 자동으로 닫습니다.\n\n"
    "_jclee-bot issue maintenance에 의해 자동화됨._"
)


@dataclass(frozen=True, slots=True)
class BranchState:
    name: str
    protected: bool
    merged_to_default: bool


@dataclass(frozen=True, slots=True)
class BranchCleanupPlan:
    name: str
    reason: str


def _paginate(token: str, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        request_params: dict[str, Any] = {} if params is None else dict(params)
        request_params.update({"per_page": 100, "page": page})
        resp = requests.get(
            f"{GITHUB_API}{path}",
            headers=headers(token),
            params=request_params,
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


def list_open_issues(*, token: str, repo_full_name: str) -> list[dict[str, Any]]:
    return _paginate(token, f"/repos/{repo_full_name}/issues", {"state": "open"})


def branch_merged_to_default(*, token: str, repo_full_name: str, branch: str, default_branch: str) -> bool:
    encoded_default = quote(default_branch, safe="")
    encoded_branch = quote(branch, safe="")
    resp = requests.get(
        f"{GITHUB_API}/repos/{repo_full_name}/compare/{encoded_default}...{encoded_branch}",
        headers=headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    return int(payload.get("ahead_by", 0) or 0) == 0


def list_branch_states(*, token: str, repo_full_name: str, default_branch: str) -> list[BranchState]:
    branches = _paginate(token, f"/repos/{repo_full_name}/branches")
    states: list[BranchState] = []
    for branch in branches:
        name = str(branch.get("name") or "")
        if not name:
            continue
        merged = name == default_branch or branch_merged_to_default(
            token=token,
            repo_full_name=repo_full_name,
            branch=name,
            default_branch=default_branch,
        )
        states.append(
            BranchState(
                name=name,
                protected=bool(branch.get("protected", False)),
                merged_to_default=merged,
            )
        )
    return states


def open_pr_heads(*, token: str, repo_full_name: str) -> set[str]:
    heads: set[str] = set()
    for pr in pr_maintenance.list_open_pull_requests(token=token, repo_full_name=repo_full_name):
        head_ref = pr_maintenance.nested_str(pr, "head", "ref")
        head_repo = pr_maintenance.nested_str(pr, "head", "repo", "full_name")
        if head_ref and head_repo == repo_full_name:
            heads.add(head_ref)
    return heads


def plan_branch_cleanup(
    branches: list[BranchState],
    *,
    open_heads: set[str],
    default_branch: str,
    mode: MaintenanceMode,
) -> list[BranchCleanupPlan]:
    plans: list[BranchCleanupPlan] = []
    for branch in branches:
        if branch.protected or pr_maintenance.is_protected_branch(branch.name, default_branch):
            continue
        if branch.name in open_heads:
            continue
        if mode == "force":
            plans.append(BranchCleanupPlan(name=branch.name, reason="force-repo-zero"))
            continue
        if branch.merged_to_default:
            plans.append(BranchCleanupPlan(name=branch.name, reason="merged"))
    return plans


def ensure_label(*, token: str, repo_full_name: str, name: str, color: str, description: str) -> None:
    resp = requests.get(f"{GITHUB_API}/repos/{repo_full_name}/labels/{name}", headers=headers(token), timeout=30)
    if resp.status_code == 200:
        return
    if resp.status_code != 404:
        resp.raise_for_status()
    create = requests.post(
        f"{GITHUB_API}/repos/{repo_full_name}/labels",
        headers=headers(token),
        json={"name": name, "color": color, "description": description},
        timeout=30,
    )
    if create.status_code != 422:
        create.raise_for_status()


def comment_issue(*, token: str, repo_full_name: str, issue_number: int, body: str) -> None:
    resp = requests.post(
        f"{GITHUB_API}/repos/{repo_full_name}/issues/{issue_number}/comments",
        headers=headers(token),
        json={"body": body},
        timeout=30,
    )
    resp.raise_for_status()


def close_issue(*, token: str, repo_full_name: str, issue_number: int) -> None:
    resp = requests.patch(
        f"{GITHUB_API}/repos/{repo_full_name}/issues/{issue_number}",
        headers=headers(token),
        json={"state": "closed"},
        timeout=30,
    )
    resp.raise_for_status()


def _summary_body(stats: dict[str, int], *, now: datetime) -> str:
    today = now.date().isoformat()
    return "\n".join(
        [
            f"## 이슈 현황 요약 ({today})",
            "",
            f"- 총 오픈 이슈: {stats['total']}",
            f"- 30일 이상 미처리: {stats['old']}개",
            f"- 라벨 미부착: {stats['no_labels']}개",
            f"- stale: {stats['stale']}개",
            "",
            "_자동 생성됨 (jclee-bot App issue maintenance)._",
        ]
    )


def upsert_summary_issue(*, token: str, repo_full_name: str, stats: dict[str, int], now: datetime) -> str | None:
    if stats["old"] <= 0:
        return None
    for name in SUMMARY_LABELS:
        ensure_label(token=token, repo_full_name=repo_full_name, name=name, color="ededed", description="Bot issue")
    body = _summary_body(stats, now=now)
    existing = _paginate(token, f"/repos/{repo_full_name}/issues", {"state": "open", "labels": "issue-summary"})
    if existing:
        number = int(existing[0]["number"])
        resp = requests.patch(
            f"{GITHUB_API}/repos/{repo_full_name}/issues/{number}",
            headers=headers(token),
            json={"body": body},
            timeout=30,
        )
        resp.raise_for_status()
        return f"update-summary:{number}"
    resp = requests.post(
        f"{GITHUB_API}/repos/{repo_full_name}/issues",
        headers=headers(token),
        json={
            "title": f"[BOT] 주간 이슈 현황 ({now.date().isoformat()})",
            "body": body,
            "labels": SUMMARY_LABELS,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return "create-summary"


def maintain_branches(
    *,
    token: str,
    repo_full_name: str,
    dry_run: bool,
    default_branch: str,
    mode: MaintenanceMode,
) -> list[str]:
    actions: list[str] = []
    try:
        branches = list_branch_states(token=token, repo_full_name=repo_full_name, default_branch=default_branch)
    except requests.RequestException as exc:
        return [f"branch-list-error:{type(exc).__name__}"]

    try:
        heads = open_pr_heads(token=token, repo_full_name=repo_full_name)
    except requests.RequestException as exc:
        return [f"branch-open-pr-error:{type(exc).__name__}"]

    for plan in plan_branch_cleanup(branches, open_heads=heads, default_branch=default_branch, mode=mode):
        actions.append(f"delete-branch:{plan.name}:{plan.reason}")
        if not dry_run:
            pr_maintenance.delete_head_branch(token=token, repo_full_name=repo_full_name, head_ref=plan.name)
    return actions


def maintain_repo(
    *,
    token: str,
    repo_full_name: str,
    dry_run: bool,
    now: datetime | None = None,
    mode: MaintenanceMode = "safe",
    default_branch: str = "master",
    branch_cleanup: bool = False,
) -> dict[str, Any]:
    current_time = now or datetime.now(UTC)
    actions: list[str] = []
    try:
        issues = list_open_issues(token=token, repo_full_name=repo_full_name)
    except requests.RequestException as exc:
        issues = []
        actions.append(f"issue-list-error:{type(exc).__name__}")

    actions.extend(
        pr_maintenance.maintain_pull_requests(
            token=token,
            repo_full_name=repo_full_name,
            dry_run=dry_run,
            now=current_time,
            mode=mode,
        )
    )

    for issue in issues:
        number = int(issue.get("number", 0) or 0)
        if number <= 0:
            continue
        if issue.get("pull_request"):
            continue
        if mode == "force":
            actions.append(f"close-issue:{number}:force-repo-zero")
            if not dry_run:
                comment_issue(
                    token=token,
                    repo_full_name=repo_full_name,
                    issue_number=number,
                    body=FORCE_ISSUE_CLEANUP_MESSAGE,
                )
                close_issue(token=token, repo_full_name=repo_full_name, issue_number=number)
            continue
        if should_close_duplicate_bot_review(issue):
            actions.append(f"close-duplicate-review:{number}")
            if not dry_run:
                comment_issue(
                    token=token,
                    repo_full_name=repo_full_name,
                    issue_number=number,
                    body=DUPLICATE_REVIEW_CLOSE_MESSAGE,
                )
                close_issue(token=token, repo_full_name=repo_full_name, issue_number=number)
            continue
        if should_close_empty_bot_review(issue):
            actions.append(f"close-empty-review:{number}")
            if not dry_run:
                comment_issue(
                    token=token,
                    repo_full_name=repo_full_name,
                    issue_number=number,
                    body=EMPTY_REVIEW_CLOSE_MESSAGE,
                )
                close_issue(token=token, repo_full_name=repo_full_name, issue_number=number)
            continue
        if is_repo_health_issue(issue):
            missing_files = missing_repo_health_files(token=token, repo_full_name=repo_full_name)
            if not missing_files:
                actions.append(f"close-recovered-repo-health:{number}")
                if not dry_run:
                    comment_issue(
                        token=token,
                        repo_full_name=repo_full_name,
                        issue_number=number,
                        body=REPO_HEALTH_RECOVERED_MESSAGE,
                    )
                    close_issue(token=token, repo_full_name=repo_full_name, issue_number=number)
                continue
            actions.append(f"keep-repo-health:{number}:missing:{','.join(missing_files)}")
            continue
        if should_close_stale(issue, now=current_time):
            actions.append(f"close-stale:{number}")
            if not dry_run:
                comment_issue(token=token, repo_full_name=repo_full_name, issue_number=number, body=CLOSE_MESSAGE)
                close_issue(token=token, repo_full_name=repo_full_name, issue_number=number)
            continue
        if should_mark_stale(issue, now=current_time):
            actions.append(f"mark-stale:{number}")
            if not dry_run:
                ensure_label(
                    token=token,
                    repo_full_name=repo_full_name,
                    name="stale",
                    color="ededed",
                    description="No recent issue activity",
                )
                issue_management.add_labels(
                    token=token, repo_full_name=repo_full_name, issue_number=number, labels=["stale"]
                )
                comment_issue(token=token, repo_full_name=repo_full_name, issue_number=number, body=STALE_MESSAGE)

    stats = issue_stats(issues, now=current_time)
    if branch_cleanup:
        actions.extend(
            maintain_branches(
                token=token,
                repo_full_name=repo_full_name,
                dry_run=dry_run,
                default_branch=default_branch,
                mode=mode,
            )
        )

    summary_action = None if dry_run or mode == "force" else upsert_summary_issue(
        token=token, repo_full_name=repo_full_name, stats=stats, now=current_time
    )
    if summary_action:
        actions.append(summary_action)
    return {"repo": repo_full_name, "actions": actions, "stats": stats}


def run_app_maintenance(
    *,
    app_id: str,
    private_key: str,
    owner: str,
    dry_run: bool,
    mode: MaintenanceMode = "safe",
) -> dict[str, Any]:
    allowed = managed_repo_names()
    if mode == "force" and allowed is None:
        return {
            "dry_run": dry_run,
            "mode": mode,
            "repositories": [],
            "error": "managed repository inventory is required for force mode",
        }
    results: list[dict[str, Any]] = []
    for installation in app_installations(app_id=app_id, private_key=private_key):
        installation_id = int(installation.get("id", 0) or 0)
        if installation_id <= 0:
            continue
        token = github_checks.installation_token(app_id, private_key, installation_id)
        for repo in installation_repositories(token=token):
            full_name = str(repo.get("full_name", ""))
            name = str(repo.get("name", ""))
            default_branch = str(repo.get("default_branch") or "master")
            if not full_name.startswith(f"{owner}/"):
                continue
            if allowed is None or name in allowed:
                results.append(
                    maintain_repo(
                        token=token,
                        repo_full_name=full_name,
                        dry_run=dry_run,
                        mode=mode,
                        default_branch=default_branch,
                        branch_cleanup=mode == "force",
                    )
                )
                continue
            if mode == "force":
                continue
            try:
                issues = list_open_issues(token=token, repo_full_name=full_name)
            except requests.RequestException:
                continue
            if has_bot_owned_issue(issues):
                results.append(
                    maintain_repo(
                        token=token,
                        repo_full_name=full_name,
                        dry_run=dry_run,
                        mode=mode,
                        default_branch=default_branch,
                        branch_cleanup=False,
                    )
                )
    return {"dry_run": dry_run, "mode": mode, "repositories": results}
