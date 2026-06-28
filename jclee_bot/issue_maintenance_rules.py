from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from jclee_bot import issue_management

STALE_DAYS = 30
CLOSE_DAYS = 7
EXEMPT_LABELS = {"pinned", "security", "critical"}
DUPLICATE_REVIEW_LABELS = {"duplicate", "jclee-bot", "review-finding"}
INVALID_REVIEW_FINDINGS = {"없음", "아니요", "아니오", "없습니다", "무", "no", "none", "n/a"}


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


def should_close_duplicate_bot_review(issue: dict[str, Any]) -> bool:
    return _is_issue(issue) and DUPLICATE_REVIEW_LABELS <= _labels(issue)


def _review_finding_text(issue: dict[str, Any]) -> str:
    body = str(issue.get("body") or "")
    marker = "## Finding"
    next_marker = "## Suggested Action"
    if marker not in body or next_marker not in body:
        return ""
    after_marker = body.split(marker, 1)[1]
    return after_marker.split(next_marker, 1)[0].strip()


def should_close_empty_bot_review(issue: dict[str, Any]) -> bool:
    labels = _labels(issue)
    if not _is_issue(issue) or not {"jclee-bot", "review-finding"} <= labels:
        return False
    normalized = "".join(_review_finding_text(issue).lower().split())
    return normalized in INVALID_REVIEW_FINDINGS


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
