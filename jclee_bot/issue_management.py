from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

import requests

GITHUB_API = "https://api.github.com"
DEFAULT_BRANCH = "master"

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
_BRANCH_TYPES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("fix", ("bug", "fix")),
    ("feat", ("enhancement", "feature", "feat")),
    ("docs", ("docs", "documentation")),
    ("security", ("security",)),
    ("perf", ("performance", "perf")),
    ("refactor", ("refactor",)),
    ("test", ("tests", "test")),
    ("chore", ("dependencies",)),
)
_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


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


def branch_type_for_labels(labels: Iterable[Any]) -> str:
    names = label_names(labels)
    for branch_type, matching_labels in _BRANCH_TYPES:
        if names.intersection(matching_labels):
            return branch_type
    return "chore"


def slug_for_branch(title: str) -> str:
    slug = _SLUG_PATTERN.sub("-", title.lower()).strip("-")
    slug = slug[:40].rstrip("-")
    return slug or "untitled"


def issue_branch_name(*, issue_number: int, title: str, labels: Iterable[Any]) -> str:
    branch_type = branch_type_for_labels(labels)
    slug = slug_for_branch(title)
    return f"{branch_type}/issue-{issue_number}-{slug}"


def should_remove_stale(payload: dict[str, Any], event: str) -> bool:
    action = payload.get("action")
    if event == "issue_comment" and action == "created":
        issue = payload.get("issue") or {}
    elif event == "issues" and action in {"edited", "reopened"}:
        issue = payload.get("issue") or {}
    else:
        return False
    return "stale" in label_names(issue.get("labels", []))


def should_create_branch(payload: dict[str, Any], event: str) -> bool:
    if event != "issues":
        return False
    issue = payload.get("issue") or {}
    if issue.get("state", "open") != "open":
        return False

    action = payload.get("action")
    if action == "opened":
        return True
    if action == "labeled":
        label = payload.get("label") or {}
        return isinstance(label, Mapping) and label.get("name") == "in-progress"
    if action == "assigned":
        assignee = payload.get("assignee") or {}
        return not (isinstance(assignee, Mapping) and assignee.get("login") == "jclee-bot")
    return False


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


def _issue_labels(issue: Mapping[str, Any]) -> list[Any]:
    labels = issue.get("labels", [])
    if isinstance(labels, Iterable) and not isinstance(labels, str | bytes):
        return list(labels)
    return []


def _default_branch_sha(*, token: str, repo_full_name: str) -> str:
    resp = requests.get(
        f"{GITHUB_API}/repos/{repo_full_name}/git/ref/heads/{DEFAULT_BRANCH}",
        headers=_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    sha = payload.get("object", {}).get("sha")
    if not isinstance(sha, str) or not sha:
        raise ValueError(f"missing {DEFAULT_BRANCH} sha for {repo_full_name}")
    return sha


def _branch_exists(*, token: str, repo_full_name: str, branch: str) -> bool:
    resp = requests.get(
        f"{GITHUB_API}/repos/{repo_full_name}/git/ref/heads/{branch}",
        headers=_headers(token),
        timeout=30,
    )
    if resp.status_code == 404:
        return False
    if resp.status_code == 200:
        return True
    resp.raise_for_status()
    return False


def _comment_on_issue(*, token: str, repo_full_name: str, issue_number: int, branch: str) -> None:
    resp = requests.post(
        f"{GITHUB_API}/repos/{repo_full_name}/issues/{issue_number}/comments",
        headers=_headers(token),
        json={
            "body": f"Branch `{branch}` created. Push commits to that branch and a draft PR will open automatically."
        },
        timeout=30,
    )
    resp.raise_for_status()


def create_issue_branch(
    *,
    token: str,
    repo_full_name: str,
    issue_number: int,
    title: str,
    labels: Iterable[Any],
) -> str | None:
    branch = issue_branch_name(issue_number=issue_number, title=title, labels=labels)
    if _branch_exists(token=token, repo_full_name=repo_full_name, branch=branch):
        return None

    sha = _default_branch_sha(token=token, repo_full_name=repo_full_name)
    resp = requests.post(
        f"{GITHUB_API}/repos/{repo_full_name}/git/refs",
        headers=_headers(token),
        json={"ref": f"refs/heads/{branch}", "sha": sha},
        timeout=30,
    )
    if resp.status_code == 422:
        return None
    resp.raise_for_status()

    try:
        _comment_on_issue(token=token, repo_full_name=repo_full_name, issue_number=issue_number, branch=branch)
    except requests.RequestException:
        pass
    return branch


def handle_issue_event(*, token: str, payload: dict[str, Any], event: str) -> dict[str, Any]:
    issue = payload.get("issue") or {}
    repo_full_name = payload.get("repository", {}).get("full_name", "")
    issue_number = int(issue.get("number", 0) or 0)
    if not token or not repo_full_name or issue_number <= 0 or issue.get("pull_request"):
        return {"actions": []}

    actions: list[str] = []
    labels: list[str] = []
    if event == "issues" and payload.get("action") == "opened":
        labels = labels_for_issue(title=issue.get("title", ""), body=issue.get("body"))
        add_labels(token=token, repo_full_name=repo_full_name, issue_number=issue_number, labels=labels)
        if labels:
            actions.append("add-labels:" + ",".join(labels))

    if should_create_branch(payload, event):
        branch = create_issue_branch(
            token=token,
            repo_full_name=repo_full_name,
            issue_number=issue_number,
            title=str(issue.get("title", "")),
            labels=[*_issue_labels(issue), *labels],
        )
        if branch:
            actions.append(f"create-branch:{branch}")

    if should_remove_stale(payload, event):
        remove_label(token=token, repo_full_name=repo_full_name, issue_number=issue_number, label="stale")
        actions.append("remove-label:stale")

    return {"actions": actions}
