from __future__ import annotations

from dataclasses import dataclass

import requests

GITHUB_API = "https://api.github.com"
RERUN_ELIGIBLE_WORKFLOWS = frozenset(
    {
        "Bot Health Monitor",
        "Downstream Health Check",
        "ELK Health Check",
        "ELK Setup",
        "Runtime Health Check",
    }
)


@dataclass(frozen=True, slots=True)
class CiFailureIssue:
    number: int
    body: str


@dataclass(frozen=True, slots=True)
class RerunTarget:
    token: str
    repo_full_name: str
    run_id: int


@dataclass(frozen=True, slots=True)
class IssueBodyPatch:
    token: str
    repo_full_name: str
    issue_number: int
    body: str


def rerun_marker(run_id: int) -> str:
    return f"<!-- jclee-bot:ci-failure-rerun-run-id={run_id} -->"


def body_with_rerun_marker(body: str, run_id: int) -> str:
    marker = rerun_marker(run_id)
    if marker in body:
        return body
    return f"{body.rstrip()}\n\n{marker}"


def rerun_allowed(workflow_name: str, run_id: int) -> bool:
    return workflow_name in RERUN_ELIGIBLE_WORKFLOWS and run_id > 0


def rerun_issue_actions(
    *, token: str, repo_full_name: str, workflow_name: str, run_id: int, issue: CiFailureIssue | None
) -> list[str]:
    if not rerun_allowed(workflow_name, run_id):
        return []
    marker = rerun_marker(run_id)
    if issue is not None and marker in issue.body:
        return [f"skip-rerun-bounded:{run_id}"]
    rerun_failed_jobs(RerunTarget(token=token, repo_full_name=repo_full_name, run_id=run_id))
    return [f"rerun-failed-jobs:{run_id}"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}


def rerun_failed_jobs(target: RerunTarget) -> None:
    resp = requests.post(
        f"{GITHUB_API}/repos/{target.repo_full_name}/actions/runs/{target.run_id}/rerun-failed-jobs",
        headers=_headers(target.token),
        timeout=30,
    )
    resp.raise_for_status()


def patch_issue_body(target: IssueBodyPatch) -> None:
    resp = requests.patch(
        f"{GITHUB_API}/repos/{target.repo_full_name}/issues/{target.issue_number}",
        headers=_headers(target.token),
        json={"body": target.body},
        timeout=30,
    )
    resp.raise_for_status()


def patch_issue_rerun_marker(*, token: str, repo_full_name: str, issue_number: int, body: str, run_id: int) -> None:
    patch_issue_body(
        IssueBodyPatch(
            token=token,
            repo_full_name=repo_full_name,
            issue_number=issue_number,
            body=body_with_rerun_marker(body, run_id),
        )
    )
