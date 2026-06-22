from __future__ import annotations

import re
from typing import Any

import requests

GITHUB_API = "https://api.github.com"
AUTO_MERGE_LABEL = "auto-merge"
BRANCH_PREFIXES = (
    "feat/",
    "fix/",
    "hotfix/",
    "docs/",
    "refactor/",
    "perf/",
    "test/",
    "chore/",
    "ci/",
    "security/",
    "build/",
    "style/",
    "revert/",
)
SKIP_SENDERS = frozenset({"jclee-bot", "github-actions[bot]"})
ISSUE_BRANCH_RE = re.compile(r"^[^/]+/issue-([0-9]+)-")


class GitHubGraphQLError(RuntimeError):
    def __init__(self, messages: list[str]) -> None:
        self.messages = tuple(messages)
        super().__init__("; ".join(self.messages) or "GitHub GraphQL request failed")


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}


def _graphql_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"bearer {token}", "Accept": "application/vnd.github+json"}


def branch_is_gitops_candidate(branch: str) -> bool:
    return branch.startswith(BRANCH_PREFIXES)


def should_open_pull_request(payload: dict[str, Any], event: str) -> bool:
    if event != "create" or payload.get("ref_type") != "branch":
        return False
    branch = str(payload.get("ref") or "")
    sender = str((payload.get("sender") or {}).get("login") or "")
    return bool(branch) and branch_is_gitops_candidate(branch) and sender not in SKIP_SENDERS


def _repo_full_name(payload: dict[str, Any]) -> str:
    return str((payload.get("repository") or {}).get("full_name") or "")


def _default_branch(payload: dict[str, Any]) -> str:
    return str((payload.get("repository") or {}).get("default_branch") or "master")


def _issue_number(branch: str) -> str:
    match = ISSUE_BRANCH_RE.match(branch)
    return match.group(1) if match else ""


def _existing_pull_request(token: str, repo_full_name: str, branch: str, base: str) -> int | None:
    owner = repo_full_name.split("/", 1)[0]
    resp = requests.get(
        f"{GITHUB_API}/repos/{repo_full_name}/pulls",
        headers=_headers(token),
        params={"state": "open", "head": f"{owner}:{branch}", "base": base, "per_page": 1},
        timeout=30,
    )
    resp.raise_for_status()
    pulls = resp.json()
    if isinstance(pulls, list) and pulls:
        number = pulls[0].get("number")
        return int(number) if isinstance(number, int) else None
    return None


def _commit_title(token: str, repo_full_name: str, branch: str) -> str:
    resp = requests.get(
        f"{GITHUB_API}/repos/{repo_full_name}/commits/{branch}",
        headers=_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    message = str(((resp.json().get("commit") or {}).get("message") or "").split("\n", 1)[0])
    return message or f"chore: open {branch}"


def _pull_request_body(branch: str) -> str:
    body = "## 변경사항\n\n<!-- 자동으로 생성된 PR입니다. 마크다운으로 변경 내용을 설명해주세요. -->\n\n"
    issue_number = _issue_number(branch)
    if issue_number:
        body += f"Closes #{issue_number}\n\n"
    return body + "> Automated by jclee-bot GitHub App"


def _create_pull_request(token: str, repo_full_name: str, branch: str, base: str, title: str) -> dict[str, Any]:
    resp = requests.post(
        f"{GITHUB_API}/repos/{repo_full_name}/pulls",
        headers=_headers(token),
        json={"head": branch, "base": base, "title": title, "body": _pull_request_body(branch)},
        timeout=30,
    )
    if resp.status_code == 422:
        return {}
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, dict) else {}


def add_auto_merge_label(token: str, repo_full_name: str, pr_number: int) -> None:
    resp = requests.post(
        f"{GITHUB_API}/repos/{repo_full_name}/issues/{pr_number}/labels",
        headers=_headers(token),
        json={"labels": [AUTO_MERGE_LABEL]},
        timeout=30,
    )
    resp.raise_for_status()


def _graphql_error_messages(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return []
    errors = data.get("errors")
    if not isinstance(errors, list):
        return []
    messages: list[str] = []
    for error in errors:
        if not isinstance(error, dict):
            continue
        message = error.get("message")
        if isinstance(message, str) and message:
            messages.append(message)
    return messages or ["GitHub GraphQL request failed"]


def enable_auto_merge(token: str, pull_request_id: str) -> None:
    if not pull_request_id:
        return
    resp = requests.post(
        f"{GITHUB_API}/graphql",
        headers=_graphql_headers(token),
        json={
            "query": (
                "mutation($id:ID!){enablePullRequestAutoMerge(input:"
                "{pullRequestId:$id,mergeMethod:SQUASH}){pullRequest{number}}}"
            ),
            "variables": {"id": pull_request_id},
        },
        timeout=30,
    )
    resp.raise_for_status()
    messages = _graphql_error_messages(resp.json())
    if messages:
        raise GitHubGraphQLError(messages)


def handle_create_event(*, token: str, payload: dict[str, Any], event: str) -> dict[str, list[str]]:
    if not token or not should_open_pull_request(payload, event):
        return {"actions": []}
    repo_full_name = _repo_full_name(payload)
    branch = str(payload.get("ref") or "")
    base = _default_branch(payload)
    if not repo_full_name or not branch:
        return {"actions": []}
    if _existing_pull_request(token, repo_full_name, branch, base) is not None:
        return {"actions": ["skip-existing-pr"]}

    title = _commit_title(token, repo_full_name, branch)
    pull_request = _create_pull_request(token, repo_full_name, branch, base, title)
    pr_number = pull_request.get("number")
    node_id = str(pull_request.get("node_id") or "")
    if not isinstance(pr_number, int):
        return {"actions": []}

    actions = [f"create-pr:{pr_number}"]
    add_auto_merge_label(token, repo_full_name, pr_number)
    actions.append(f"add-label:{AUTO_MERGE_LABEL}")
    enable_auto_merge(token, node_id)
    actions.append("enable-auto-merge")
    return {"actions": actions}


def should_enable_auto_merge_for_pull_request(payload: dict[str, Any], event: str) -> bool:
    pr = payload.get("pull_request") or {}
    if event == "pull_request_review":
        review = payload.get("review") or {}
        author = str((pr.get("user") or {}).get("login") or "")
        return review.get("state") == "approved" and not pr.get("draft") and not author.endswith("[bot]")
    if event == "pull_request" and payload.get("action") == "labeled":
        label = payload.get("label") or {}
        return label.get("name") == AUTO_MERGE_LABEL and not pr.get("draft")
    return False


def handle_pull_request_auto_merge(*, token: str, payload: dict[str, Any], event: str) -> dict[str, list[str]]:
    if not token or not should_enable_auto_merge_for_pull_request(payload, event):
        return {"actions": []}
    pr = payload.get("pull_request") or {}
    node_id = str(pr.get("node_id") or "")
    if not node_id:
        return {"actions": []}
    enable_auto_merge(token, node_id)
    number = int(pr.get("number", 0) or 0)
    action = f"enable-auto-merge:{number}" if number > 0 else "enable-auto-merge"
    return {"actions": [action]}
