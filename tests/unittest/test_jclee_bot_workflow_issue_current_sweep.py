from __future__ import annotations

import requests
from _pytest.monkeypatch import MonkeyPatch

from jclee_bot import workflow_current_sweep, workflow_issue_automation, workflow_legacy_sweep


class FakeResponse:
    payload: dict[str, object]

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.payload


def _workflow_list_response() -> FakeResponse:
    return FakeResponse(
        {
            "workflows": [
                {
                    "name": "Live E2E Tests",
                    "path": ".github/workflows/39_e2e-live.yml",
                },
                {
                    "name": "ELK Health Check",
                    "path": ".github/workflows/26_elk-health-check.yml",
                },
            ]
        }
    )


def _success_runs_response() -> FakeResponse:
    return FakeResponse(
        {
            "workflow_runs": [
                {
                    "head_branch": "master",
                    "status": "completed",
                    "conclusion": "skipped",
                    "head_sha": "abcdef1234567890abcdef1234567890abcdef12",
                },
                {
                    "head_branch": "master",
                    "status": "completed",
                    "conclusion": "success",
                    "head_sha": "abcdef1234567890abcdef1234567890abcdef12",
                }
            ]
        }
    )


def _install_common_sweep_fakes(monkeypatch: MonkeyPatch) -> None:
    def no_legacy_issues(*, token: str, repo_full_name: str, title_substring: str) -> list[int]:
        del token, repo_full_name, title_substring
        return []

    def no_in_flight_run(*, token: str, repo_full_name: str, workflow_file: str, default_branch: str) -> bool:
        del token, repo_full_name, workflow_file, default_branch
        return False

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        del kwargs
        if url.endswith("/actions/workflows?per_page=100"):
            return _workflow_list_response()
        return _success_runs_response()

    monkeypatch.setattr(workflow_legacy_sweep, "_issue_numbers_with_title", no_legacy_issues)
    monkeypatch.setattr(workflow_legacy_sweep, "_newest_run_in_flight", no_in_flight_run)
    monkeypatch.setattr(requests, "get", fake_get)


def test_sweep_closes_current_default_branch_ci_failure_after_matching_success(
    monkeypatch: MonkeyPatch,
) -> None:
    # Given
    closed: list[tuple[int, str]] = []
    issue_body = "\n".join(
        [
            "## CI Failure",
            "",
            "- **Workflow:** Live E2E Tests",
            "- **Commit:** abcdef1234567890abcdef1234567890abcdef12",
            "- **Run:** https://github.com/jclee941/jclee-bot/actions/runs/100",
        ]
    )

    def open_current_issue(*, token: str, repo_full_name: str, labels: str | None = None) -> list[dict[str, object]]:
        del token, repo_full_name, labels
        return [
            {
                "number": 692,
                "title": "[ci] Live E2E Tests failed at abcdef12",
                "body": issue_body,
            }
        ]

    def fake_close(*, token: str, repo_full_name: str, issue_number: int, body: str) -> None:
        del token, repo_full_name
        closed.append((issue_number, body))

    _install_common_sweep_fakes(monkeypatch)
    monkeypatch.setattr(workflow_current_sweep, "_open_ci_failure_issues", open_current_issue)
    monkeypatch.setattr(workflow_issue_automation, "_close", fake_close)

    # When
    actions = workflow_issue_automation.sweep_legacy_failure_issues(
        token="tok",
        repo_full_name="jclee941/jclee-bot",
        default_branch="master",
        dry_run=False,
    )

    # Then
    assert actions == ["close-current:692:39_e2e-live.yml"]
    assert closed == [
        (
            692,
            (
                "39_e2e-live.yml completed successfully on master "
                "for abcdef1234567890abcdef1234567890abcdef12.\n\n_jclee-bot에의해자동화됨._"
            ),
        )
    ]


def test_sweep_preserves_current_ci_failure_when_body_references_pr(monkeypatch: MonkeyPatch) -> None:
    # Given
    closed: list[int] = []
    issue_body = "\n".join(
        [
            "## CI Failure",
            "",
            "- **Workflow:** ELK Health Check",
            "- **Commit:** abcdef1234567890abcdef1234567890abcdef12",
            "- **PR:** #686",
            "- **Run:** https://github.com/jclee941/jclee-bot/actions/runs/100",
        ]
    )

    def open_pr_issue(*, token: str, repo_full_name: str, labels: str | None = None) -> list[dict[str, object]]:
        del token, repo_full_name, labels
        return [
            {
                "number": 693,
                "title": "[ci] ELK Health Check failed at abcdef12",
                "body": issue_body,
            }
        ]

    def fake_close(*, token: str, repo_full_name: str, issue_number: int, body: str) -> None:
        del token, repo_full_name, body
        closed.append(issue_number)

    _install_common_sweep_fakes(monkeypatch)
    monkeypatch.setattr(workflow_current_sweep, "_open_ci_failure_issues", open_pr_issue)
    monkeypatch.setattr(workflow_issue_automation, "_close", fake_close)

    # When
    actions = workflow_issue_automation.sweep_legacy_failure_issues(
        token="tok",
        repo_full_name="jclee941/jclee-bot",
        default_branch="master",
        dry_run=False,
    )

    # Then
    assert actions == []
    assert closed == []
