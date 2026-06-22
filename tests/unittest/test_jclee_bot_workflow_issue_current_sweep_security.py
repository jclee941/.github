from __future__ import annotations

import requests
from _pytest.monkeypatch import MonkeyPatch

from jclee_bot import workflow_current_sweep, workflow_issue_automation, workflow_legacy_sweep

type FakePayload = dict[str, object] | list[dict[str, object]]


class FakeResponse:
    payload: FakePayload

    def __init__(self, payload: FakePayload) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> FakePayload:
        return self.payload


def _workflow_list_response() -> FakeResponse:
    return FakeResponse(
        {
            "workflows": [
                {
                    "name": "ELK Health Check",
                    "path": ".github/workflows/26_elk-health-check.yml",
                }
            ]
        }
    )


def _install_common_fakes(monkeypatch: MonkeyPatch) -> None:
    def no_legacy_issues(*, token: str, repo_full_name: str, title_substring: str) -> list[int]:
        del token, repo_full_name, title_substring
        return []

    def no_in_flight_run(*, token: str, repo_full_name: str, workflow_file: str, default_branch: str) -> bool:
        del token, repo_full_name, workflow_file, default_branch
        return False

    def success_get(url: str, **kwargs: object) -> FakeResponse:
        del kwargs
        if url.endswith("/actions/workflows?per_page=100"):
            return _workflow_list_response()
        return FakeResponse(
            {
                "workflow_runs": [
                    {
                        "head_branch": "master",
                        "conclusion": "success",
                        "head_sha": "abcdef1234567890abcdef1234567890abcdef12",
                    }
                ]
            }
        )

    monkeypatch.setattr(workflow_legacy_sweep, "_issue_numbers_with_title", no_legacy_issues)
    monkeypatch.setattr(workflow_legacy_sweep, "_newest_run_in_flight", no_in_flight_run)
    monkeypatch.setattr(requests, "get", success_get)


def _sweep() -> list[str]:
    return workflow_issue_automation.sweep_legacy_failure_issues(
        token="tok",
        repo_full_name="jclee941/.github",
        default_branch="master",
        dry_run=False,
    )


def test_sweep_preserves_github_pull_request_entries(monkeypatch: MonkeyPatch) -> None:
    # Given
    closed: list[int] = []
    issue_body = "\n".join(
        [
            "## CI Failure",
            "",
            "- **Workflow:** ELK Health Check",
            "- **Commit:** abcdef1234567890abcdef1234567890abcdef12",
            "- **Run:** https://github.com/jclee941/.github/actions/runs/100",
        ]
    )

    def open_pull_request_entry(*, token: str, repo_full_name: str) -> list[dict[str, object]]:
        del token, repo_full_name
        return [
            {
                "number": 700,
                "title": "[ci] ELK Health Check failed at abcdef12",
                "body": issue_body,
                "pull_request": {"url": "https://api.github.com/repos/jclee941/.github/pulls/700"},
            }
        ]

    _install_common_fakes(monkeypatch)
    monkeypatch.setattr(workflow_current_sweep, "_open_ci_failure_issues", open_pull_request_entry)

    def fake_close(*, token: str, repo_full_name: str, issue_number: int, body: str) -> None:
        del token, repo_full_name, body
        closed.append(issue_number)

    monkeypatch.setattr(workflow_issue_automation, "_close", fake_close)

    # When
    actions = _sweep()

    # Then
    assert actions == []
    assert closed == []


def test_sweep_preserves_current_issue_when_newest_completed_run_failed(monkeypatch: MonkeyPatch) -> None:
    # Given
    issue_body = "\n".join(
        [
            "## CI Failure",
            "",
            "- **Workflow:** ELK Health Check",
            "- **Commit:** abcdef1234567890abcdef1234567890abcdef12",
            "- **Run:** https://github.com/jclee941/.github/actions/runs/100",
        ]
    )

    def failed_then_success_get(url: str, **kwargs: object) -> FakeResponse:
        del kwargs
        if url.endswith("/actions/workflows?per_page=100"):
            return _workflow_list_response()
        return FakeResponse(
            {
                "workflow_runs": [
                    {
                        "head_branch": "master",
                        "conclusion": "failure",
                        "head_sha": "abcdef1234567890abcdef1234567890abcdef12",
                    },
                    {
                        "head_branch": "master",
                        "conclusion": "success",
                        "head_sha": "abcdef1234567890abcdef1234567890abcdef12",
                    },
                ]
            }
        )

    def open_current_issue(*, token: str, repo_full_name: str) -> list[dict[str, object]]:
        del token, repo_full_name
        return [{"number": 692, "title": "[ci] ELK Health Check failed at abcdef12", "body": issue_body}]

    _install_common_fakes(monkeypatch)
    monkeypatch.setattr(requests, "get", failed_then_success_get)
    monkeypatch.setattr(workflow_current_sweep, "_open_ci_failure_issues", open_current_issue)

    assert _sweep() == []


def test_sweep_preserves_current_issue_with_malformed_commit(monkeypatch: MonkeyPatch) -> None:
    # Given
    issue_body = "\n".join(
        [
            "## CI Failure",
            "",
            "- **Workflow:** ELK Health Check",
            "- **Commit:** abcdef12-not-a-full-sha",
            "- **Run:** https://github.com/jclee941/.github/actions/runs/100",
        ]
    )

    def open_malformed_issue(*, token: str, repo_full_name: str) -> list[dict[str, object]]:
        del token, repo_full_name
        return [{"number": 692, "title": "[ci] ELK Health Check failed at abcdef12", "body": issue_body}]

    _install_common_fakes(monkeypatch)
    monkeypatch.setattr(workflow_current_sweep, "_open_ci_failure_issues", open_malformed_issue)

    assert _sweep() == []


def test_sweep_defers_current_issue_when_matching_run_is_active(monkeypatch: MonkeyPatch) -> None:
    # Given
    closed: list[int] = []
    issue_body = "\n".join(
        [
            "## CI Failure",
            "",
            "- **Workflow:** ELK Health Check",
            "- **Commit:** abcdef1234567890abcdef1234567890abcdef12",
            "- **Run:** https://github.com/jclee941/.github/actions/runs/100",
        ]
    )

    def active_then_success_get(url: str, **kwargs: object) -> FakeResponse:
        del kwargs
        if url.endswith("/actions/workflows?per_page=100"):
            return _workflow_list_response()
        if "status=completed" in url:
            return FakeResponse(
                {
                    "workflow_runs": [
                        {
                            "head_branch": "master",
                            "status": "completed",
                            "conclusion": "success",
                            "head_sha": "abcdef1234567890abcdef1234567890abcdef12",
                        }
                    ]
                }
            )
        return FakeResponse(
            {
                "workflow_runs": [
                    {
                        "head_branch": "master",
                        "status": "in_progress",
                        "conclusion": None,
                        "head_sha": "abcdef1234567890abcdef1234567890abcdef12",
                    }
                ]
            }
        )

    def open_current_issue(*, token: str, repo_full_name: str) -> list[dict[str, object]]:
        del token, repo_full_name
        return [{"number": 692, "title": "[ci] ELK Health Check failed at abcdef12", "body": issue_body}]

    _install_common_fakes(monkeypatch)
    monkeypatch.setattr(requests, "get", active_then_success_get)
    monkeypatch.setattr(workflow_current_sweep, "_open_ci_failure_issues", open_current_issue)

    def fake_close(*, token: str, repo_full_name: str, issue_number: int, body: str) -> None:
        del token, repo_full_name, body
        closed.append(issue_number)

    monkeypatch.setattr(workflow_issue_automation, "_close", fake_close)

    # When
    actions = _sweep()

    # Then
    assert actions == ["defer-current:692:26_elk-health-check.yml:run-in-flight"]
    assert closed == []


def test_legacy_sweep_preserves_github_pull_request_entries(monkeypatch: MonkeyPatch) -> None:
    # Given
    closed: list[int] = []

    def legacy_pr_entry_get(url: str, **kwargs: object) -> FakeResponse:
        del kwargs
        if url.endswith("/issues"):
            return FakeResponse(
                [
                    {
                        "number": 77,
                        "title": "ELK Health Check Failed",
                        "pull_request": {"url": "https://api.github.com/repos/jclee941/.github/pulls/77"},
                    }
                ]
            )
        return FakeResponse(
            {
                "workflow_runs": [
                    {
                        "status": "completed",
                        "conclusion": "success",
                    }
                ]
            }
        )

    def no_current_sweep(
        *,
        token: str,
        repo_full_name: str,
        default_branch: str,
        dry_run: bool,
        close_issue: workflow_current_sweep.CloseIssue,
    ) -> list[str]:
        del token, repo_full_name, default_branch, dry_run, close_issue
        return []

    monkeypatch.setattr(requests, "get", legacy_pr_entry_get)
    monkeypatch.setattr(workflow_current_sweep, "sweep_current_failure_issues", no_current_sweep)

    def fake_close(*, token: str, repo_full_name: str, issue_number: int, body: str) -> None:
        del token, repo_full_name, body
        closed.append(issue_number)

    monkeypatch.setattr(workflow_issue_automation, "_close", fake_close)

    # When
    actions = _sweep()

    # Then
    assert actions == []
    assert closed == []
