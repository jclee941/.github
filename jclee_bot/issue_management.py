from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import requests

GITHUB_API = "https://api.github.com"

_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("bug", ("bug", "fix", "error", "crash")),
    ("enhancement", ("feature", "enhance", "add", "support")),
    ("documentation", ("doc", "readme", "documentation", "wiki")),
    ("security", ("security", "vuln", "cve", "exploit")),
    ("tests", ("test", "testing", "coverage")),
    ("performance", ("perf", "slow", "memory", "optimize")),
    ("refactor", ("refactor", "clean", "debt")),
    ("dependencies", ("deps", "dependency", "upgrade", "bump")),
)


def labels_for_issue(*, title: str, body: str | None) -> list[str]:
    text = f"{title} {body or ''}".lower()
    labels: list[str] = []
    for label, terms in _KEYWORDS:
        if any(term in text for term in terms):
            labels.append(label)
    return labels


def label_names(labels: Iterable[Any]) -> set[str]:
    names: set[str] = set()
    for label in labels:
        if isinstance(label, Mapping):
            name = label.get("name")
        else:
            name = getattr(label, "name", None)
        if isinstance(name, str):
            names.add(name)
    return names


def should_remove_stale(payload: dict[str, Any], event: str) -> bool:
    action = payload.get("action")
    if event == "issue_comment" and action == "created":
        issue = payload.get("issue") or {}
    elif event == "issues" and action in {"edited", "reopened"}:
        issue = payload.get("issue") or {}
    else:
        return False
    return "stale" in label_names(issue.get("labels", []))


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}


def add_labels(*, token: str, repo_full_name: str, issue_number: int, labels: list[str]) -> None:
    if not labels:
        return
    resp = requests.post(
        f"{GITHUB_API}/repos/{repo_full_name}/issues/{issue_number}/labels",
        headers=_headers(token),
        json={"labels": labels},
        timeout=30,
    )
    resp.raise_for_status()


def remove_label(*, token: str, repo_full_name: str, issue_number: int, label: str) -> None:
    resp = requests.delete(
        f"{GITHUB_API}/repos/{repo_full_name}/issues/{issue_number}/labels/{label}",
        headers=_headers(token),
        timeout=30,
    )
    if resp.status_code != 404:
        resp.raise_for_status()


def handle_issue_event(*, token: str, payload: dict[str, Any], event: str) -> dict[str, Any]:
    issue = payload.get("issue") or {}
    repo_full_name = payload.get("repository", {}).get("full_name", "")
    issue_number = int(issue.get("number", 0) or 0)
    if not token or not repo_full_name or issue_number <= 0 or issue.get("pull_request"):
        return {"actions": []}

    actions: list[str] = []
    if event == "issues" and payload.get("action") == "opened":
        labels = labels_for_issue(title=issue.get("title", ""), body=issue.get("body"))
        add_labels(token=token, repo_full_name=repo_full_name, issue_number=issue_number, labels=labels)
        if labels:
            actions.append("add-labels:" + ",".join(labels))

    if should_remove_stale(payload, event):
        remove_label(token=token, repo_full_name=repo_full_name, issue_number=issue_number, label="stale")
        actions.append("remove-label:stale")

    return {"actions": actions}
