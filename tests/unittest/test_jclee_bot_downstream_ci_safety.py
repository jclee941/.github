from __future__ import annotations

from pathlib import Path
from typing import cast

import requests
from pytest import MonkeyPatch

from jclee_bot import downstream_ci_sweep, issue_maintenance, workflow_issue_automation
from jclee_bot.downstream_ci_runs import WorkflowSnapshot


def _inventory(path: Path) -> None:
    _ = path.write_text(
        "\n".join(
            [
                "repositories:",
                "  - name: tmux",
                "    default_branch: master",
                "    automation:",
                "      health_check: true",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_successful_latest_run_preserves_malformed_ci_failure_issue(monkeypatch: MonkeyPatch) -> None:
    # Given
    closed: list[int] = []
    issue: dict[str, object] = {
        "number": 7,
        "title": "[ci] CI failed at abcdef12",
        "body": "manual issue without bot-created workflow and commit fields",
        "labels": [{"name": "ci-failure"}],
    }
    run = workflow_issue_automation.WorkflowRun(
        name="CI",
        head_sha="fedcba1234567890abcdef1234567890abcdef12",
        run_id=44,
        conclusion="success",
        pr_number=0,
        run_url="https://github.com/jclee941/tmux/actions/runs/44",
    )

    def list_open_issues(**_: object) -> list[dict[str, object]]:
        return [issue]

    def track_comment_or_close(**kwargs: object) -> None:
        issue_number = kwargs["issue_number"]
        assert isinstance(issue_number, int)
        closed.append(issue_number)

    monkeypatch.setattr(issue_maintenance, "list_open_issues", list_open_issues)
    monkeypatch.setattr(issue_maintenance, "comment_issue", track_comment_or_close)
    monkeypatch.setattr(issue_maintenance, "close_issue", track_comment_or_close)

    # When
    actions = downstream_ci_sweep.close_stale_ci_failures_for_workflow(
        token="tok",
        repo_full_name="jclee941/tmux",
        run=run,
        dry_run=False,
    )

    # Then
    assert actions == []
    assert closed == []


def test_successful_latest_run_preserves_manual_ci_failure_issue(monkeypatch: MonkeyPatch) -> None:
    # Given
    closed: list[int] = []
    issue: dict[str, object] = {
        "number": 7,
        "title": "[ci] CI failed at abcdef12",
        "body": "\n".join(
            [
                "## CI Failure",
                "",
                "- **Workflow:** CI",
                "- **Commit:** abcdef1234567890abcdef1234567890abcdef12",
                "- **Run:** https://github.com/jclee941/tmux/actions/runs/42",
                "",
                "> jclee-bot에의해자동화됨.",
            ]
        ),
        "labels": [{"name": "ci-failure"}],
    }
    run = workflow_issue_automation.WorkflowRun(
        name="CI",
        head_sha="fedcba1234567890abcdef1234567890abcdef12",
        run_id=44,
        conclusion="success",
        pr_number=0,
        run_url="https://github.com/jclee941/tmux/actions/runs/44",
    )

    def list_open_issues(**_: object) -> list[dict[str, object]]:
        return [issue]

    def track_comment_or_close(**kwargs: object) -> None:
        issue_number = kwargs["issue_number"]
        assert isinstance(issue_number, int)
        closed.append(issue_number)

    monkeypatch.setattr(issue_maintenance, "list_open_issues", list_open_issues)
    monkeypatch.setattr(issue_maintenance, "comment_issue", track_comment_or_close)
    monkeypatch.setattr(issue_maintenance, "close_issue", track_comment_or_close)

    # When
    actions = downstream_ci_sweep.close_stale_ci_failures_for_workflow(
        token="tok",
        repo_full_name="jclee941/tmux",
        run=run,
        dry_run=False,
    )

    # Then
    assert actions == []
    assert closed == []


def test_managed_repo_sweep_redacts_request_exception_detail(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    config_path = tmp_path / "repos.yaml"
    _inventory(config_path)

    def token_for_repo(**_: object) -> str:
        return "ghs_SECRET_TOKEN"

    monkeypatch.setattr(workflow_issue_automation, "installation_token_for_repo", token_for_repo)

    def broken_snapshots(**_: object) -> list[WorkflowSnapshot]:
        raise requests.HTTPError("request failed with Authorization: token ghs_SECRET_TOKEN")

    monkeypatch.setattr(downstream_ci_sweep, "_workflow_snapshots", broken_snapshots)

    result = downstream_ci_sweep.run_downstream_ci_sweep(
        app_id="123",
        private_key="key",
        owner="jclee941",
        dry_run=True,
        repo_names=None,
        config_path=config_path,
    )

    repositories = result["repositories"]
    assert isinstance(repositories, list)
    repository = repositories[0]
    assert isinstance(repository, dict)
    repository = cast(dict[str, object], repository)
    assert repository["error"] == "HTTPError"
    assert repository["detail"] == "request failed while sweeping repository"
