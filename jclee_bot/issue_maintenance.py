from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
import yaml

from jclee_bot import github_checks, issue_management

GITHUB_API = "https://api.github.com"
STALE_DAYS = 30
CLOSE_DAYS = 7
EXEMPT_LABELS = {"pinned", "security", "critical"}
SUMMARY_LABELS = ["issue-summary", "bot"]
STALE_MESSAGE = (
    "이 이슈는 30일 이상 활동이 없어 `stale` 상태로 전환됩니다. "
    "추가 활동이 없으면 7일 후 자동으로 닫힙니다."
)
CLOSE_MESSAGE = "이슈가 7일 이상 활동이 없어 자동으로 닫혔습니다. 필요시 재오픈해주세요."


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}


def parse_github_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _age_days(issue: dict[str, Any], now: datetime) -> int:
    updated_at = str(issue.get("updated_at") or issue.get("created_at") or "")
    if not updated_at:
        return 0
    return int((now - parse_github_time(updated_at)).total_seconds() // 86400)


def _is_issue(issue: dict[str, Any]) -> bool:
    return not issue.get("pull_request") and issue.get("state", "open") == "open"


def _labels(issue: dict[str, Any]) -> set[str]:
    return issue_management.label_names(issue.get("labels", []))


def should_mark_stale(issue: dict[str, Any], *, now: datetime) -> bool:
    labels = _labels(issue)
    if not _is_issue(issue) or "stale" in labels or labels & EXEMPT_LABELS:
        return False
    return _age_days(issue, now) >= STALE_DAYS


def should_close_stale(issue: dict[str, Any], *, now: datetime) -> bool:
    labels = _labels(issue)
    if not _is_issue(issue) or "stale" not in labels or labels & EXEMPT_LABELS:
        return False
    return _age_days(issue, now) >= CLOSE_DAYS


def issue_stats(issues: list[dict[str, Any]], *, now: datetime) -> dict[str, int]:
    open_issues = [issue for issue in issues if _is_issue(issue)]
    stats = {
        "total": len(open_issues),
        "no_labels": sum(not _labels(issue) for issue in open_issues),
        "old": sum(_age_days(issue, now) > STALE_DAYS for issue in open_issues),
    }
    for label in ("bug", "enhancement", "documentation", "security", "stale"):
        stats[label] = sum(label in _labels(issue) for issue in open_issues)
    return stats


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


def list_open_issues(*, token: str, repo_full_name: str) -> list[dict[str, Any]]:
    return _paginate(token, f"/repos/{repo_full_name}/issues", {"state": "open"})


def ensure_label(*, token: str, repo_full_name: str, name: str, color: str, description: str) -> None:
    resp = requests.get(f"{GITHUB_API}/repos/{repo_full_name}/labels/{name}", headers=_headers(token), timeout=30)
    if resp.status_code == 200:
        return
    if resp.status_code != 404:
        resp.raise_for_status()
    create = requests.post(
        f"{GITHUB_API}/repos/{repo_full_name}/labels",
        headers=_headers(token),
        json={"name": name, "color": color, "description": description},
        timeout=30,
    )
    if create.status_code != 422:
        create.raise_for_status()


def comment_issue(*, token: str, repo_full_name: str, issue_number: int, body: str) -> None:
    resp = requests.post(
        f"{GITHUB_API}/repos/{repo_full_name}/issues/{issue_number}/comments",
        headers=_headers(token),
        json={"body": body},
        timeout=30,
    )
    resp.raise_for_status()


def close_issue(*, token: str, repo_full_name: str, issue_number: int) -> None:
    resp = requests.patch(
        f"{GITHUB_API}/repos/{repo_full_name}/issues/{issue_number}",
        headers=_headers(token),
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
            headers=_headers(token),
            json={"body": body},
            timeout=30,
        )
        resp.raise_for_status()
        return f"update-summary:{number}"
    resp = requests.post(
        f"{GITHUB_API}/repos/{repo_full_name}/issues",
        headers=_headers(token),
        json={
            "title": f"[BOT] 주간 이슈 현황 ({now.date().isoformat()})",
            "body": body,
            "labels": SUMMARY_LABELS,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return "create-summary"


def maintain_repo(*, token: str, repo_full_name: str, dry_run: bool, now: datetime | None = None) -> dict[str, Any]:
    current_time = now or datetime.now(UTC)
    issues = list_open_issues(token=token, repo_full_name=repo_full_name)
    actions: list[str] = []

    for issue in issues:
        number = int(issue.get("number", 0) or 0)
        if number <= 0:
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
    summary_action = None if dry_run else upsert_summary_issue(
        token=token, repo_full_name=repo_full_name, stats=stats, now=current_time
    )
    if summary_action:
        actions.append(summary_action)
    return {"repo": repo_full_name, "actions": actions, "stats": stats}


def managed_repo_names(config_path: Path | None = None) -> set[str] | None:
    path = config_path or Path(__file__).resolve().parents[1] / "config" / "repos.yaml"
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    repos = data.get("repositories", []) if isinstance(data, dict) else []
    return {
        str(repo["name"])
        for repo in repos
        if isinstance(repo, dict) and repo.get("automation", {}).get("deploy_workflows") is True
    }


def app_installations(*, app_id: str, private_key: str) -> list[dict[str, Any]]:
    token_jwt = github_checks._app_jwt(app_id, private_key)  # noqa: SLF001 - shared App auth helper
    resp = requests.get(
        f"{GITHUB_API}/app/installations",
        headers={"Authorization": f"Bearer {token_jwt}", "Accept": "application/vnd.github+json"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def installation_repositories(*, token: str) -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    page = 1
    while True:
        resp = requests.get(
            f"{GITHUB_API}/installation/repositories",
            headers=_headers(token),
            params={"per_page": 100, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("repositories", []) if isinstance(data, dict) else []
        repos.extend(batch)
        if len(batch) < 100:
            return repos
        page += 1


def run_app_maintenance(*, app_id: str, private_key: str, owner: str, dry_run: bool) -> dict[str, Any]:
    allowed = managed_repo_names()
    results: list[dict[str, Any]] = []
    for installation in app_installations(app_id=app_id, private_key=private_key):
        installation_id = int(installation.get("id", 0) or 0)
        if installation_id <= 0:
            continue
        token = github_checks.installation_token(app_id, private_key, installation_id)
        for repo in installation_repositories(token=token):
            full_name = str(repo.get("full_name", ""))
            name = str(repo.get("name", ""))
            if full_name.startswith(f"{owner}/") and (allowed is None or name in allowed):
                results.append(maintain_repo(token=token, repo_full_name=full_name, dry_run=dry_run))
    return {"dry_run": dry_run, "repositories": results}
