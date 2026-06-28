from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Final

import requests
from pydantic import TypeAdapter

from jclee_bot import workflow_current_sweep

GITHUB_API = "https://api.github.com"

LEGACY_SWEEP_MAP = (
    ("[ci-fail] Release Drafter @", "23_release-drafter.yml"),
    ("[ci] Sanity failed at", "90_sanity.yml"),
    ("[ci-fail] Sanity @", "90_sanity.yml"),
    ("ELK Health Check Failed", "26_elk-health-check.yml"),
    ("ELK Setup Failed", "27_elk-setup.yml"),
    ("Bot webhook endpoint unreachable", "30_runtime-health-check.yml"),
    ("CLIProxyAPI unreachable", "30_runtime-health-check.yml"),
    ("jclee-bot not responding", "30_runtime-health-check.yml"),
    ("Runtime Health Check failed", "30_runtime-health-check.yml"),
    ("Downstream workflow failures detected", "29_downstream-health-check.yml"),
    ("Downstream Health Check failed", "29_downstream-health-check.yml"),
    ("bot-health", "28_bot-health-monitor.yml"),
    ("Bot Health Monitor failed", "28_bot-health-monitor.yml"),
    ("Repository Health Check", "31_repo-health.yml"),
)
ACTIVE_RUN_STATUSES = {"queued", "in_progress", "waiting", "pending", "requested"}
PR_REVIEW_FAILURE_TITLE_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:Security )?PR Review failed for PR #(?P<number>[1-9][0-9]*)$"
)
type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
type CloseIssue = Callable[[int, str], None]

JSON_VALUE_ADAPTER: Final[TypeAdapter[JsonValue]] = TypeAdapter(JsonValue)


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}


def _response_json(resp: requests.Response) -> JsonValue:
    return JSON_VALUE_ADAPTER.validate_python(resp.json())


def _open_issues(*, token: str, repo_full_name: str, labels: str | None = None) -> list[Mapping[str, JsonValue]]:
    issues: list[Mapping[str, JsonValue]] = []
    page = 1
    while True:
        params = {"state": "open", "per_page": 100, "page": page}
        if labels:
            params["labels"] = labels
        resp = requests.get(
            f"{GITHUB_API}/repos/{repo_full_name}/issues",
            headers=_headers(token),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        raw_batch = _response_json(resp)
        if not isinstance(raw_batch, list) or not raw_batch:
            return issues
        for raw_issue in raw_batch:
            if isinstance(raw_issue, dict):
                issues.append(_typed_issue(raw_issue))
        if len(raw_batch) < 100:
            return issues
        page += 1


def _typed_issue(issue: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
    typed_issue: dict[str, JsonValue] = {}
    raw_number = issue.get("number")
    raw_title = issue.get("title")
    raw_pull_request = issue.get("pull_request")
    if isinstance(raw_number, int) and not isinstance(raw_number, bool):
        typed_issue["number"] = raw_number
    if isinstance(raw_title, str):
        typed_issue["title"] = raw_title
    if isinstance(raw_pull_request, dict):
        typed_issue["pull_request"] = {}
    return typed_issue


def _issue_numbers_with_title(*, token: str, repo_full_name: str, title_substring: str) -> list[int]:
    numbers: list[int] = []
    for issue in _open_issues(token=token, repo_full_name=repo_full_name):
        if isinstance(issue.get("pull_request"), dict):
            continue
        if title_substring not in str(issue.get("title") or ""):
            continue
        raw_number = issue.get("number")
        if isinstance(raw_number, int) and raw_number > 0:
            numbers.append(raw_number)
    return numbers


def _pull_request_state(*, token: str, repo_full_name: str, pr_number: int) -> str:
    resp = requests.get(
        f"{GITHUB_API}/repos/{repo_full_name}/pulls/{pr_number}",
        headers=_headers(token),
        timeout=30,
    )
    if resp.status_code == 404:
        return "missing"
    resp.raise_for_status()
    raw_data = _response_json(resp)
    if not isinstance(raw_data, dict):
        return "unknown"
    state = raw_data.get("state")
    return state if isinstance(state, str) else "unknown"


def _close_legacy_pr_review_failures(
    *,
    token: str,
    repo_full_name: str,
    dry_run: bool,
    close_issue: CloseIssue,
) -> list[str]:
    actions: list[str] = []
    for issue in _open_issues(token=token, repo_full_name=repo_full_name, labels="ci-failure"):
        if isinstance(issue.get("pull_request"), dict):
            continue
        raw_title = issue.get("title")
        title = raw_title if isinstance(raw_title, str) else ""
        match = PR_REVIEW_FAILURE_TITLE_RE.fullmatch(title)
        if match is None:
            continue
        raw_number = issue.get("number")
        if not isinstance(raw_number, int) or raw_number <= 0:
            continue
        pr_number = int(match.group("number"))
        state = _pull_request_state(token=token, repo_full_name=repo_full_name, pr_number=pr_number)
        if state != "closed":
            actions.append(f"keep-pr-review:{raw_number}:{pr_number}:{state}")
            continue
        actions.append(f"close-pr-review:{raw_number}:{pr_number}")
        if not dry_run:
            close_issue(
                raw_number,
                f"PR #{pr_number} is closed; closing legacy PR review failure issue.\n\n_jclee-bot에의해자동화됨._",
            )
    return actions


def _workflow_run_status(
    *,
    token: str,
    repo_full_name: str,
    workflow_file: str,
    default_branch: str,
    completed_only: bool,
) -> tuple[str, str]:
    status_query = "&status=completed" if completed_only else ""
    runs_url = (
        f"{GITHUB_API}/repos/{repo_full_name}/actions/workflows/{workflow_file}/runs"
        f"?branch={default_branch}{status_query}&per_page=1"
    )
    resp = requests.get(
        runs_url,
        headers=_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    raw_data = _response_json(resp)
    if not isinstance(raw_data, dict):
        return ("none", "none")
    runs = raw_data.get("workflow_runs")
    if not isinstance(runs, list) or not runs:
        return ("none", "none")
    first = runs[0]
    if not isinstance(first, dict):
        return ("none", "none")
    return (str(first.get("status") or "none"), str(first.get("conclusion") or "none"))


def _newest_run_in_flight(*, token: str, repo_full_name: str, workflow_file: str, default_branch: str) -> bool:
    status, _ = _workflow_run_status(
        token=token,
        repo_full_name=repo_full_name,
        workflow_file=workflow_file,
        default_branch=default_branch,
        completed_only=False,
    )
    return status in ACTIVE_RUN_STATUSES


def sweep_failure_issues(
    *,
    token: str,
    repo_full_name: str,
    default_branch: str,
    dry_run: bool,
    close_issue: CloseIssue,
) -> list[str]:
    actions: list[str] = []
    for title_substring, workflow_file in LEGACY_SWEEP_MAP:
        numbers = _issue_numbers_with_title(token=token, repo_full_name=repo_full_name, title_substring=title_substring)
        if not numbers:
            continue
        if _newest_run_in_flight(
            token=token,
            repo_full_name=repo_full_name,
            workflow_file=workflow_file,
            default_branch=default_branch,
        ):
            actions.append(f"defer-sweep:{workflow_file}:run-in-flight")
            continue
        _, conclusion = _workflow_run_status(
            token=token,
            repo_full_name=repo_full_name,
            workflow_file=workflow_file,
            default_branch=default_branch,
            completed_only=True,
        )
        if conclusion != "success":
            actions.append(f"keep-sweep:{workflow_file}:{conclusion}")
            continue
        for number in numbers:
            actions.append(f"close-legacy:{number}:{workflow_file}")
            if not dry_run:
                close_issue(
                    number,
                    f"{workflow_file} latest run on {default_branch} concluded success.\n\n_jclee-bot에의해자동화됨._",
                )
    actions.extend(
        _close_legacy_pr_review_failures(
            token=token,
            repo_full_name=repo_full_name,
            dry_run=dry_run,
            close_issue=close_issue,
        )
    )
    actions.extend(
        workflow_current_sweep.sweep_current_failure_issues(
            token=token,
            repo_full_name=repo_full_name,
            default_branch=default_branch,
            dry_run=dry_run,
            close_issue=close_issue,
        )
    )
    return actions
