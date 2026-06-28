from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import requests

from jclee_bot.gitops_automation import GitHubGraphQLError, add_auto_merge_label, enable_auto_merge

DOCS_SYNC_TITLE = "docs: sync standard templates from jclee941/jclee-bot"
AUTOMATION_TITLE_PREFIXES = ("chore(deps", "build(deps", DOCS_SYNC_TITLE)
AUTOMATION_HEAD_PREFIXES = ("dependabot/", "renovate/", "bot/", "jclee-bot/", "docs-sync/")
AUTO_MERGE_ERRORS = (GitHubGraphQLError, requests.RequestException)


class CheckState(Protocol):
    failed: tuple[str, ...]
    pending: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PrAutoMergePlan:
    number: int
    pull_request_id: str


def nested_str(item: dict[str, Any], *keys: str) -> str:
    current: Any = item
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return str(current or "")


def is_automation_pr(pr: dict[str, Any]) -> bool:
    title = str(pr.get("title") or "")
    head_ref = nested_str(pr, "head", "ref")
    return title.startswith(AUTOMATION_TITLE_PREFIXES) or head_ref.startswith(AUTOMATION_HEAD_PREFIXES)


def plan_pr_auto_merge(pr: dict[str, Any], *, checks: CheckState) -> PrAutoMergePlan | None:
    number = int(pr.get("number", 0) or 0)
    pull_request_id = str(pr.get("node_id") or "")
    if number <= 0 or not pull_request_id:
        return None
    if pr.get("draft") or pr.get("auto_merge") is not None:
        return None
    if checks.failed or checks.pending or not is_automation_pr(pr):
        return None
    return PrAutoMergePlan(number=number, pull_request_id=pull_request_id)


def apply_pr_auto_merge(*, token: str, repo_full_name: str, plan: PrAutoMergePlan) -> None:
    add_auto_merge_label(token, repo_full_name, plan.number)
    enable_auto_merge(token, plan.pull_request_id)
