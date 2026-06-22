from __future__ import annotations

from typing import Any

import requests

from jclee_bot import issue_maintenance

GITHUB_API = "https://api.github.com"
AUTOMATION_MARKER = "jclee-bot에의해자동화됨"
DEFAULT_LABEL_COLOR = "BFD4F2"


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}


def _label_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _open_issues(*, token: str, repo_full_name: str, labels: list[str] | None = None) -> list[dict[str, Any]]:
    params = {"state": "open"}
    if labels:
        params["labels"] = ",".join(labels)
    return issue_maintenance._paginate(token, f"/repos/{repo_full_name}/issues", params)  # noqa: SLF001


def _ensure_labels(*, token: str, repo_full_name: str, labels: list[str]) -> None:
    for label in labels:
        issue_maintenance.ensure_label(
            token=token,
            repo_full_name=repo_full_name,
            name=label,
            color=DEFAULT_LABEL_COLOR,
            description=AUTOMATION_MARKER,
        )


def _find_issue(
    *,
    token: str,
    repo_full_name: str,
    title: str,
    labels: list[str],
) -> int | None:
    for issue in _open_issues(token=token, repo_full_name=repo_full_name, labels=labels[:1]):
        if str(issue.get("title") or "") != title:
            continue
        number = int(issue.get("number", 0) or 0)
        return number if number > 0 else None
    return None


def _issue_numbers_matching(
    *,
    token: str,
    repo_full_name: str,
    labels: list[str],
    title_contains: str,
    created_before: str,
) -> list[int]:
    numbers: list[int] = []
    for issue in _open_issues(token=token, repo_full_name=repo_full_name, labels=labels[:1]):
        title = str(issue.get("title") or "")
        if title_contains and title_contains not in title:
            continue
        created_at = str(issue.get("created_at") or "")
        if created_before and (not created_at or created_at >= created_before):
            continue
        number = int(issue.get("number", 0) or 0)
        if number > 0:
            numbers.append(number)
    return numbers


def _create_issue(*, token: str, repo_full_name: str, title: str, body: str, labels: list[str]) -> int:
    resp = requests.post(
        f"{GITHUB_API}/repos/{repo_full_name}/issues",
        headers=_headers(token),
        json={"title": title, "body": body, "labels": labels},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return int(data.get("number", 0) or 0) if isinstance(data, dict) else 0


def _patch_issue(*, token: str, repo_full_name: str, issue_number: int, fields: dict[str, object]) -> None:
    resp = requests.patch(
        f"{GITHUB_API}/repos/{repo_full_name}/issues/{issue_number}",
        headers=_headers(token),
        json=fields,
        timeout=30,
    )
    resp.raise_for_status()


def _add_labels(*, token: str, repo_full_name: str, issue_number: int, labels: list[str]) -> None:
    resp = requests.post(
        f"{GITHUB_API}/repos/{repo_full_name}/issues/{issue_number}/labels",
        headers=_headers(token),
        json={"labels": labels},
        timeout=30,
    )
    resp.raise_for_status()


def _command_repo(payload: dict[str, Any], command: dict[str, Any]) -> str:
    return str(command.get("repo") or payload.get("repository") or "")


def _run_upsert_issue(*, token: str, payload: dict[str, Any], command: dict[str, Any], dry_run: bool) -> str:
    repo_full_name = _command_repo(payload, command)
    title = str(command.get("title") or "")
    body = str(command.get("body") or "")
    labels = _label_list(command.get("labels"))
    if not repo_full_name or not title:
        return "skip-upsert:missing-repo-or-title"

    existing = _find_issue(token=token, repo_full_name=repo_full_name, title=title, labels=labels)
    if existing is not None:
        if not dry_run:
            if command.get("update_body", False):
                _patch_issue(token=token, repo_full_name=repo_full_name, issue_number=existing, fields={"body": body})
            if command.get("comment_existing", True):
                issue_maintenance.comment_issue(
                    token=token,
                    repo_full_name=repo_full_name,
                    issue_number=existing,
                    body=body,
                )
        return f"upsert-comment:{repo_full_name}#{existing}"

    if not dry_run:
        _ensure_labels(token=token, repo_full_name=repo_full_name, labels=labels)
        created = _create_issue(token=token, repo_full_name=repo_full_name, title=title, body=body, labels=labels)
        return f"upsert-create:{repo_full_name}#{created}"
    return f"upsert-create:{repo_full_name}:{title}"


def _run_create_issue(*, token: str, payload: dict[str, Any], command: dict[str, Any], dry_run: bool) -> str:
    repo_full_name = _command_repo(payload, command)
    title = str(command.get("title") or "")
    body = str(command.get("body") or "")
    labels = _label_list(command.get("labels"))
    if not repo_full_name or not title:
        return "skip-create:missing-repo-or-title"
    if not dry_run:
        _ensure_labels(token=token, repo_full_name=repo_full_name, labels=labels)
        created = _create_issue(token=token, repo_full_name=repo_full_name, title=title, body=body, labels=labels)
        return f"create:{repo_full_name}#{created}"
    return f"create:{repo_full_name}:{title}"


def _run_close_matching(*, token: str, payload: dict[str, Any], command: dict[str, Any], dry_run: bool) -> list[str]:
    repo_full_name = _command_repo(payload, command)
    labels = _label_list(command.get("labels"))
    title_contains = str(command.get("title_contains") or "")
    created_before = str(command.get("created_before") or "")
    comment = str(command.get("comment") or "")
    if not repo_full_name:
        return ["skip-close-matching:missing-repo"]
    numbers = _issue_numbers_matching(
        token=token,
        repo_full_name=repo_full_name,
        labels=labels,
        title_contains=title_contains,
        created_before=created_before,
    )
    actions: list[str] = []
    for number in numbers:
        actions.append(f"close:{repo_full_name}#{number}")
        if not dry_run:
            if comment:
                issue_maintenance.comment_issue(
                    token=token,
                    repo_full_name=repo_full_name,
                    issue_number=number,
                    body=comment,
                )
            issue_maintenance.close_issue(token=token, repo_full_name=repo_full_name, issue_number=number)
    return actions or [f"close:none:{repo_full_name}"]


def _run_label_issue(*, token: str, payload: dict[str, Any], command: dict[str, Any], dry_run: bool) -> str:
    repo_full_name = _command_repo(payload, command)
    issue_number = int(command.get("number", 0) or 0)
    labels = _label_list(command.get("labels"))
    body = str(command.get("body") or "")
    if not repo_full_name or issue_number <= 0:
        return "skip-label:missing-repo-or-number"
    if not dry_run:
        _ensure_labels(token=token, repo_full_name=repo_full_name, labels=labels)
        if labels:
            _add_labels(token=token, repo_full_name=repo_full_name, issue_number=issue_number, labels=labels)
        if body:
            issue_maintenance.comment_issue(
                token=token,
                repo_full_name=repo_full_name,
                issue_number=issue_number,
                body=body,
            )
    return f"label:{repo_full_name}#{issue_number}"


def _run_close_issues(*, token: str, payload: dict[str, Any], command: dict[str, Any], dry_run: bool) -> list[str]:
    repo_full_name = _command_repo(payload, command)
    numbers = [int(item) for item in command.get("numbers", []) if int(item) > 0]
    comment = str(command.get("comment") or "")
    if not repo_full_name:
        return ["skip-close:missing-repo"]
    actions: list[str] = []
    for number in numbers:
        actions.append(f"close:{repo_full_name}#{number}")
        if not dry_run:
            if comment:
                issue_maintenance.comment_issue(
                    token=token,
                    repo_full_name=repo_full_name,
                    issue_number=number,
                    body=comment,
                )
            issue_maintenance.close_issue(token=token, repo_full_name=repo_full_name, issue_number=number)
    return actions or [f"close:none:{repo_full_name}"]


def run_issue_commands(*, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    dry_run = bool(payload.get("dry_run", False))
    commands = payload.get("commands")
    if not isinstance(commands, list):
        return {"dry_run": dry_run, "actions": [], "error": "commands must be an array"}

    actions: list[str] = []
    for item in commands:
        if not isinstance(item, dict):
            actions.append("skip-command:not-object")
            continue
        command_type = str(item.get("type") or "")
        match command_type:
            case "upsert_issue":
                actions.append(_run_upsert_issue(token=token, payload=payload, command=item, dry_run=dry_run))
            case "create_issue":
                actions.append(_run_create_issue(token=token, payload=payload, command=item, dry_run=dry_run))
            case "close_matching_issues":
                actions.extend(_run_close_matching(token=token, payload=payload, command=item, dry_run=dry_run))
            case "label_issue":
                actions.append(_run_label_issue(token=token, payload=payload, command=item, dry_run=dry_run))
            case "close_issues":
                actions.extend(_run_close_issues(token=token, payload=payload, command=item, dry_run=dry_run))
            case _:
                actions.append(f"skip-command:unknown:{command_type}")
    return {"dry_run": dry_run, "actions": actions}
