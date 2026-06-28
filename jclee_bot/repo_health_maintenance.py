from __future__ import annotations

from typing import Any

import requests

from jclee_bot import issue_management
from jclee_bot.github_api_client import GITHUB_API, headers

REPO_HEALTH_LABELS = {"documentation", "repo-health"}
REPO_HEALTH_FILES = ("README.md", "CONTRIBUTING.md", "LICENSE")
BOT_OWNED_LABELS = {"jclee-bot", "repo-health"}


def _repo_file_exists(*, token: str, repo_full_name: str, path: str) -> bool:
    resp = requests.get(
        f"{GITHUB_API}/repos/{repo_full_name}/contents/{path}",
        headers=headers(token),
        timeout=30,
    )
    if resp.status_code == 404:
        return False
    resp.raise_for_status()
    return True


def missing_repo_health_files(*, token: str, repo_full_name: str) -> list[str]:
    return [
        path
        for path in REPO_HEALTH_FILES
        if not _repo_file_exists(token=token, repo_full_name=repo_full_name, path=path)
    ]


def is_repo_health_issue(issue: dict[str, Any]) -> bool:
    labels = issue_management.label_names(issue.get("labels", []))
    title = str(issue.get("title") or "")
    return REPO_HEALTH_LABELS <= labels and "문서 누락" in title


def has_bot_owned_issue(issues: list[dict[str, Any]]) -> bool:
    return any(BOT_OWNED_LABELS & issue_management.label_names(issue.get("labels", [])) for issue in issues)
