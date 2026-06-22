from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

import requests
from pydantic import TypeAdapter

GITHUB_API = "https://api.github.com"
CURRENT_CI_FAILURE_TITLE_RE = re.compile(r"^\[ci\] (?P<workflow>.+) failed at (?P<short_sha>[0-9a-fA-F]{7,40})$")
FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
ACTIVE_RUN_STATUSES = {"queued", "in_progress", "waiting", "pending", "requested"}

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
type CloseIssue = Callable[[int, str], None]

JSON_VALUE_ADAPTER: Final[TypeAdapter[JsonValue]] = TypeAdapter(JsonValue)


@dataclass(frozen=True, slots=True)
class CurrentFailureIssue:
    number: int
    workflow_name: str
    head_sha: str


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}


def _response_json(resp: requests.Response) -> JsonValue:
    return JSON_VALUE_ADAPTER.validate_python(resp.json())


def _open_ci_failure_issues(*, token: str, repo_full_name: str) -> list[Mapping[str, JsonValue]]:
    issues: list[Mapping[str, JsonValue]] = []
    page = 1
    while True:
        resp = requests.get(
            f"{GITHUB_API}/repos/{repo_full_name}/issues",
            headers=_headers(token),
            params={"state": "open", "labels": "ci-failure", "per_page": 100, "page": page},
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
    raw_body = issue.get("body")
    raw_pull_request = issue.get("pull_request")
    if isinstance(raw_number, int) and not isinstance(raw_number, bool):
        typed_issue["number"] = raw_number
    if isinstance(raw_title, str):
        typed_issue["title"] = raw_title
    if isinstance(raw_body, str):
        typed_issue["body"] = raw_body
    if isinstance(raw_pull_request, dict):
        typed_issue["pull_request"] = {}
    return typed_issue


def _body_field(body: str, field_name: str) -> str | None:
    prefix = f"- **{field_name}:** "
    for line in body.splitlines():
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip()
    return None


def _body_has_pr_line(body: str) -> bool:
    return any(line.startswith("- **PR:**") for line in body.splitlines())


def _current_failure_issue(issue: Mapping[str, JsonValue]) -> CurrentFailureIssue | None:
    if isinstance(issue.get("pull_request"), dict):
        return None
    raw_title = issue.get("title")
    title = raw_title if isinstance(raw_title, str) else ""
    match = CURRENT_CI_FAILURE_TITLE_RE.match(title)
    if match is None:
        return None
    raw_body = issue.get("body")
    body = raw_body if isinstance(raw_body, str) else ""
    if _body_has_pr_line(body):
        return None
    workflow_name = _body_field(body, "Workflow")
    head_sha = _body_field(body, "Commit")
    if workflow_name is None or head_sha is None:
        return None
    if FULL_SHA_RE.fullmatch(head_sha) is None:
        return None
    if workflow_name != match.group("workflow") or not head_sha.startswith(match.group("short_sha")):
        return None
    raw_number = issue.get("number")
    if not isinstance(raw_number, int) or isinstance(raw_number, bool) or raw_number <= 0:
        return None
    return CurrentFailureIssue(number=raw_number, workflow_name=workflow_name, head_sha=head_sha)


def _workflow_files_by_name(*, token: str, repo_full_name: str) -> dict[str, str]:
    resp = requests.get(
        f"{GITHUB_API}/repos/{repo_full_name}/actions/workflows?per_page=100",
        headers=_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    raw_data = _response_json(resp)
    if not isinstance(raw_data, dict):
        return {}
    workflows = raw_data.get("workflows")
    if not isinstance(workflows, list):
        return {}
    files_by_name: dict[str, str] = {}
    for workflow in workflows:
        if not isinstance(workflow, dict):
            continue
        name = workflow.get("name")
        path = workflow.get("path")
        if isinstance(name, str) and isinstance(path, str) and name and path:
            files_by_name[name] = path.removeprefix(".github/workflows/")
    return files_by_name


def _workflow_has_completed_success_for_sha(
    *,
    token: str,
    repo_full_name: str,
    workflow_file: str,
    default_branch: str,
    head_sha: str,
) -> bool:
    runs_url = (
        f"{GITHUB_API}/repos/{repo_full_name}/actions/workflows/{workflow_file}/runs"
        f"?head_sha={head_sha}&status=completed&per_page=20"
    )
    resp = requests.get(
        runs_url,
        headers=_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    raw_data = _response_json(resp)
    if not isinstance(raw_data, dict):
        return False
    runs = raw_data.get("workflow_runs")
    if not isinstance(runs, list):
        return False
    for run in runs:
        if not isinstance(run, dict):
            continue
        if run.get("head_sha") != head_sha or run.get("head_branch", default_branch) != default_branch:
            continue
        conclusion = run.get("conclusion")
        if conclusion == "skipped":
            continue
        return conclusion == "success"
    return False


def _workflow_has_active_run_for_sha(
    *,
    token: str,
    repo_full_name: str,
    workflow_file: str,
    default_branch: str,
    head_sha: str,
) -> bool:
    runs_url = (
        f"{GITHUB_API}/repos/{repo_full_name}/actions/workflows/{workflow_file}/runs"
        f"?head_sha={head_sha}&per_page=20"
    )
    resp = requests.get(
        runs_url,
        headers=_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    raw_data = _response_json(resp)
    if not isinstance(raw_data, dict):
        return False
    runs = raw_data.get("workflow_runs")
    if not isinstance(runs, list):
        return False
    for run in runs:
        if not isinstance(run, dict):
            continue
        if run.get("head_sha") != head_sha or run.get("head_branch", default_branch) != default_branch:
            continue
        if run.get("status") in ACTIVE_RUN_STATUSES:
            return True
    return False


def sweep_current_failure_issues(
    *,
    token: str,
    repo_full_name: str,
    default_branch: str,
    dry_run: bool,
    close_issue: CloseIssue,
) -> list[str]:
    actions: list[str] = []
    workflow_files = _workflow_files_by_name(token=token, repo_full_name=repo_full_name)
    for issue in _open_ci_failure_issues(token=token, repo_full_name=repo_full_name):
        current_issue = _current_failure_issue(issue)
        if current_issue is None:
            continue
        workflow_file = workflow_files.get(current_issue.workflow_name)
        if workflow_file is None:
            actions.append(f"keep-current:{current_issue.number}:workflow-not-found")
            continue
        if _workflow_has_active_run_for_sha(
            token=token,
            repo_full_name=repo_full_name,
            workflow_file=workflow_file,
            default_branch=default_branch,
            head_sha=current_issue.head_sha,
        ):
            actions.append(f"defer-current:{current_issue.number}:{workflow_file}:run-in-flight")
            continue
        if not _workflow_has_completed_success_for_sha(
            token=token,
            repo_full_name=repo_full_name,
            workflow_file=workflow_file,
            default_branch=default_branch,
            head_sha=current_issue.head_sha,
        ):
            continue
        actions.append(f"close-current:{current_issue.number}:{workflow_file}")
        if not dry_run:
            close_issue(
                current_issue.number,
                (
                    f"{workflow_file} completed successfully on {default_branch} "
                    f"for {current_issue.head_sha}.\n\n_jclee-bot에의해자동화됨._"
                ),
            )
    return actions
