from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import requests

import jclee_bot.workflow_rerun as workflow_rerun
from jclee_bot import github_checks, issue_maintenance, workflow_legacy_sweep
from jclee_bot.github_app_inventory import app_installations, installation_repositories
from jclee_bot.workflow_recovery import RECOVERY_TITLE_MAP, recovered_ci_failure_title, short_sha

GITHUB_API = "https://api.github.com"

CI_FAILURE_LABELS = ("ci-failure", "automated")
CI_FAILURE_LABEL_DETAILS = {
    "ci-failure": ("B60205", "jclee-bot에의해자동화됨"),
    "automated": ("BFD4F2", "jclee-bot에의해자동화됨"),
}


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
    return (
        f"## CI Failure\n\n- **Workflow:** {run.name}\n- **Commit:** {run.head_sha}\n"
        f"{pr_line}- **Run:** {run.run_url}\n\n### Action Required\n"
        "Inspect the failed run and either fix the underlying problem "
        "or close this issue if the failure was transient.\n\n"
        "> jclee-bot에의해자동화됨."
    )


def _ci_failure_title(run: WorkflowRun) -> str:
    return f"[ci] {run.name} failed at {short_sha(run.head_sha)}"


def _int_value(value: object) -> int:
    return value if isinstance(value, int) else int(value) if isinstance(value, str) and value.isdecimal() else 0


def _open_issues(*, token: str, repo_full_name: str, labels: str | None = None) -> list[dict[str, object]]:
    issues = cast(
        list[dict[str, object]], issue_maintenance.list_open_issues(token=token, repo_full_name=repo_full_name)
    )
    if labels is None:
        return issues
    required = set(labels.split(","))
    return [issue for issue in issues if required <= _issue_label_names(issue)]


def _find_ci_failure_issue(
    *, token: str, repo_full_name: str, title: str, label: str
) -> workflow_rerun.CiFailureIssue | None:
    for issue in _open_issues(token=token, repo_full_name=repo_full_name, labels=label):
        if str(issue.get("title") or "") == title:
            number = _int_value(issue.get("number", 0))
            if number <= 0:
                return None
            return workflow_rerun.CiFailureIssue(number=number, body=str(issue.get("body") or ""))
    return None


def _issue_label_names(issue: dict[str, object]) -> set[str]:
    raw_labels = issue.get("labels")
    labels = cast(list[dict[str, object]], raw_labels) if isinstance(raw_labels, list) else []
    return {str(label.get("name") or "") for label in labels}


def _issue_is_pull_request_failure(issue: dict[str, object]) -> bool:
    if isinstance(issue.get("pull_request"), dict):
        return True
    body = str(issue.get("body") or "")
    return any(line.startswith("- **PR:**") for line in body.splitlines())


def _closeable_issue_numbers_with_title(*, token: str, repo_full_name: str, title_substring: str) -> list[int]:
    numbers: list[int] = []
    for issue in _open_issues(token=token, repo_full_name=repo_full_name):
        if _issue_is_pull_request_failure(issue):
            continue
        if title_substring not in str(issue.get("title") or ""):
            continue
        number = _int_value(issue.get("number", 0))
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
    raw_data = cast(object, resp.json())
    data = cast(dict[str, object], raw_data) if isinstance(raw_data, dict) else {}
    number = _int_value(data.get("number", 0))
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
        case "cancelled" | "skipped":
            return "neutral"
        case _:
            return "neutral"


def record_workflow_run(
    *,
    token: str,
    repo_full_name: str,
    run: WorkflowRun,
    dry_run: bool,
    default_branch: str = "master",
) -> list[str]:
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
                default_branch=default_branch,
                dry_run=dry_run,
            )
        )
        return actions

    title = _ci_failure_title(run)
    existing = _find_ci_failure_issue(token=token, repo_full_name=repo_full_name, title=title, label="ci-failure")
    if existing is not None:
        if not dry_run:
            rerun_actions = workflow_rerun.rerun_issue_actions(
                token=token, repo_full_name=repo_full_name, workflow_name=run.name, run_id=run.run_id, issue=existing
            )
            if rerun_actions and rerun_actions[0].startswith("skip-rerun-bounded:"):
                return rerun_actions
            if rerun_actions:
                workflow_rerun.patch_issue_rerun_marker(
                    token=token,
                    repo_full_name=repo_full_name,
                    issue_number=existing.number,
                    body=existing.body,
                    run_id=run.run_id,
                )
            _comment(
                token=token,
                repo_full_name=repo_full_name,
                issue_number=existing.number,
                body=f"Another failure for the same workflow+sha. Run: {run.run_url}\n\n_jclee-bot에의해자동화됨._",
            )
            return [f"comment-ci-failure:{existing.number}", *rerun_actions]
    if not dry_run:
        _ensure_ci_labels(token=token, repo_full_name=repo_full_name)
        issue_body = _issue_body(run)
        created = _create_issue(token=token, repo_full_name=repo_full_name, title=title, body=issue_body)
        rerun_actions = workflow_rerun.rerun_issue_actions(
            token=token, repo_full_name=repo_full_name, workflow_name=run.name, run_id=run.run_id, issue=None
        )
        if rerun_actions and created is not None:
            workflow_rerun.patch_issue_rerun_marker(
                token=token, repo_full_name=repo_full_name, issue_number=created, body=issue_body, run_id=run.run_id
        )
        return [f"create-ci-failure:{created or 0}", *rerun_actions]
    return [f"comment-ci-failure:{existing.number}"] if existing is not None else [f"create-ci-failure:{title}"]


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
    for number in _closeable_issue_numbers_with_title(
        token=token,
        repo_full_name=repo_full_name,
        title_substring=recovered_ci_failure_title(workflow_name=workflow_name, head_sha=head_sha),
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
            for number in _closeable_issue_numbers_with_title(
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


def sweep_legacy_failure_issues(*, token: str, repo_full_name: str, default_branch: str, dry_run: bool) -> list[str]:
    return workflow_legacy_sweep.sweep_failure_issues(
        token=token,
        repo_full_name=repo_full_name,
        default_branch=default_branch,
        dry_run=dry_run,
        close_issue=lambda issue_number, body: _close(
            token=token,
            repo_full_name=repo_full_name,
            issue_number=issue_number,
            body=body,
        ),
    )


def installation_token_for_repo(*, app_id: str, private_key: str, repo_full_name: str) -> str | None:
    for installation in app_installations(app_id=app_id, private_key=private_key):
        installation_id = int(installation.get("id", 0) or 0)
        if installation_id <= 0:
            continue
        token = github_checks.installation_token(app_id, private_key, installation_id)
        for repo in installation_repositories(token=token):
            if str(repo.get("full_name") or "") == repo_full_name:
                return token
    return None
