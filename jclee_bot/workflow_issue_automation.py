from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from jclee_bot import github_checks, issue_maintenance

GITHUB_API = "https://api.github.com"

CI_FAILURE_LABELS = ("ci-failure", "automated")
CI_FAILURE_LABEL_DETAILS = {
    "ci-failure": ("B60205", "jclee-bot에의해자동화됨"),
    "automated": ("BFD4F2", "jclee-bot에의해자동화됨"),
}
RECOVERY_TITLE_MAP = (
    ("ELK Health Check", ("ELK Health Check Failed",)),
    ("ELK Setup", ("ELK Setup Failed",)),
    (
        "Runtime Health Check",
        (
            "Bot webhook endpoint unreachable",
            "CLIProxyAPI unreachable",
            "jclee-bot not responding",
            "Runtime Health Check failed",
        ),
    ),
    ("Downstream Health Check", ("Downstream workflow failures detected", "Downstream Health Check failed")),
    ("Bot Health Monitor", ("bot-health", "Bot Health Monitor failed")),
)
LEGACY_SWEEP_MAP = (
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


@dataclass(frozen=True, slots=True)
class WorkflowRun:
    name: str
    head_sha: str
    run_id: int
    conclusion: str
    pr_number: int
    run_url: str


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}


def _issue_body(run: WorkflowRun) -> str:
    pr_line = f"- **PR:** #{run.pr_number}\n" if run.pr_number > 0 else ""
    return "\n".join(
        [
            "## CI Failure",
            "",
            f"- **Workflow:** {run.name}",
            f"- **Commit:** {run.head_sha}",
            f"{pr_line}- **Run:** {run.run_url}",
            "",
            "### Action Required",
            (
                "Inspect the failed run and either fix the underlying problem "
                "or close this issue if the failure was transient."
            ),
            "",
            "> jclee-bot에의해자동화됨.",
        ]
    )


def _short_sha(sha: str) -> str:
    return sha[:8] if len(sha) >= 8 else sha


def _ci_failure_title(run: WorkflowRun) -> str:
    return f"[ci] {run.name} failed at {_short_sha(run.head_sha)}"


def _recovered_ci_failure_title(*, workflow_name: str, head_sha: str) -> str:
    return f"[ci] {workflow_name} failed at {_short_sha(head_sha)}"


def _open_issues(*, token: str, repo_full_name: str, labels: str | None = None) -> list[dict[str, Any]]:
    params = {"state": "open"}
    if labels:
        params["labels"] = labels
    return issue_maintenance._paginate(token, f"/repos/{repo_full_name}/issues", params)  # noqa: SLF001


def _find_issue_by_title(*, token: str, repo_full_name: str, title: str, label: str) -> int | None:
    for issue in _open_issues(token=token, repo_full_name=repo_full_name, labels=label):
        if str(issue.get("title") or "") == title:
            number = int(issue.get("number", 0) or 0)
            return number if number > 0 else None
    return None


def _issue_numbers_with_title(*, token: str, repo_full_name: str, title_substring: str) -> list[int]:
    numbers: list[int] = []
    for issue in _open_issues(token=token, repo_full_name=repo_full_name):
        if title_substring not in str(issue.get("title") or ""):
            continue
        number = int(issue.get("number", 0) or 0)
        if number > 0:
            numbers.append(number)
    return numbers


def _create_issue(*, token: str, repo_full_name: str, title: str, body: str) -> int | None:
    resp = requests.post(
        f"{GITHUB_API}/repos/{repo_full_name}/issues",
        headers=_headers(token),
        json={"title": title, "body": body, "labels": list(CI_FAILURE_LABELS)},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    number = int(data.get("number", 0) or 0) if isinstance(data, dict) else 0
    return number if number > 0 else None


def _ensure_ci_labels(*, token: str, repo_full_name: str) -> None:
    for name, (color, description) in CI_FAILURE_LABEL_DETAILS.items():
        issue_maintenance.ensure_label(
            token=token,
            repo_full_name=repo_full_name,
            name=name,
            color=color,
            description=description,
        )


def _comment(*, token: str, repo_full_name: str, issue_number: int, body: str) -> None:
    issue_maintenance.comment_issue(token=token, repo_full_name=repo_full_name, issue_number=issue_number, body=body)


def _close(*, token: str, repo_full_name: str, issue_number: int, body: str) -> None:
    _comment(token=token, repo_full_name=repo_full_name, issue_number=issue_number, body=body)
    issue_maintenance.close_issue(token=token, repo_full_name=repo_full_name, issue_number=issue_number)


def normalize_conclusion(conclusion: str) -> str:
    match conclusion:
        case "success" | "failure":
            return conclusion
        case "cancelled":
            return "failure"
        case "skipped":
            return "neutral"
        case _:
            return "neutral"


def record_workflow_run(*, token: str, repo_full_name: str, run: WorkflowRun, dry_run: bool) -> list[str]:
    conclusion = normalize_conclusion(run.conclusion)
    if conclusion == "neutral":
        return [f"ignore-neutral:{run.name}"]
    if conclusion == "success":
        actions = close_recovered_workflow_issues(
            token=token,
            repo_full_name=repo_full_name,
            workflow_name=run.name,
            head_sha=run.head_sha,
            dry_run=dry_run,
        )
        actions.extend(
            sweep_legacy_failure_issues(
                token=token,
                repo_full_name=repo_full_name,
                default_branch="master",
                dry_run=dry_run,
            )
        )
        return actions

    title = _ci_failure_title(run)
    existing = _find_issue_by_title(token=token, repo_full_name=repo_full_name, title=title, label="ci-failure")
    if existing is not None:
        if not dry_run:
            _comment(
                token=token,
                repo_full_name=repo_full_name,
                issue_number=existing,
                body=f"Another failure for the same workflow+sha. Run: {run.run_url}\n\n_jclee-bot에의해자동화됨._",
            )
        return [f"comment-ci-failure:{existing}"]
    if not dry_run:
        _ensure_ci_labels(token=token, repo_full_name=repo_full_name)
        created = _create_issue(token=token, repo_full_name=repo_full_name, title=title, body=_issue_body(run))
        return [f"create-ci-failure:{created or 0}"]
    return [f"create-ci-failure:{title}"]


def close_recovered_workflow_issues(
    *,
    token: str,
    repo_full_name: str,
    workflow_name: str,
    head_sha: str,
    dry_run: bool,
) -> list[str]:
    actions: list[str] = []
    closed_numbers: set[int] = set()
    for number in _issue_numbers_with_title(
        token=token,
        repo_full_name=repo_full_name,
        title_substring=_recovered_ci_failure_title(workflow_name=workflow_name, head_sha=head_sha),
    ):
        if number in closed_numbers:
            continue
        closed_numbers.add(number)
        actions.append(f"close-recovered:{number}:{workflow_name}")
        if not dry_run:
            _close(
                token=token,
                repo_full_name=repo_full_name,
                issue_number=number,
                body=(
                    f"Resolved: {workflow_name} concluded success on "
                    f"{head_sha}.\n\n_jclee-bot에의해자동화됨._"
                ),
            )
    for name, title_substrings in RECOVERY_TITLE_MAP:
        if name != workflow_name:
            continue
        for title_substring in title_substrings:
            for number in _issue_numbers_with_title(
                token=token,
                repo_full_name=repo_full_name,
                title_substring=title_substring,
            ):
                if number in closed_numbers:
                    continue
                closed_numbers.add(number)
                actions.append(f"close-recovered:{number}:{workflow_name}")
                if not dry_run:
                    _close(
                        token=token,
                        repo_full_name=repo_full_name,
                        issue_number=number,
                        body=(
                            f"Resolved: {workflow_name} concluded success on "
                            f"{head_sha}.\n\n_jclee-bot에의해자동화됨._"
                        ),
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
    resp = requests.get(
        f"{GITHUB_API}/repos/{repo_full_name}/actions/workflows/{workflow_file}/runs?branch={default_branch}{status_query}&per_page=1",
        headers=_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    runs = data.get("workflow_runs", []) if isinstance(data, dict) else []
    first = runs[0] if runs else {}
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


def sweep_legacy_failure_issues(*, token: str, repo_full_name: str, default_branch: str, dry_run: bool) -> list[str]:
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
                _close(
                    token=token,
                    repo_full_name=repo_full_name,
                    issue_number=number,
                    body=(
                        f"{workflow_file} latest run on {default_branch} "
                        "concluded success.\n\n_jclee-bot에의해자동화됨._"
                    ),
                )
    return actions


def installation_token_for_repo(*, app_id: str, private_key: str, repo_full_name: str) -> str | None:
    for installation in issue_maintenance.app_installations(app_id=app_id, private_key=private_key):
        installation_id = int(installation.get("id", 0) or 0)
        if installation_id <= 0:
            continue
        token = github_checks.installation_token(app_id, private_key, installation_id)
        for repo in issue_maintenance.installation_repositories(token=token):
            if str(repo.get("full_name") or "") == repo_full_name:
                return token
    return None
