from __future__ import annotations

from pathlib import Path
from typing import cast

import requests
from fastapi.testclient import TestClient
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
                "  - name: docs-only",
                "    default_branch: master",
                "    automation:",
                "      health_check: false",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_managed_repo_sweep_records_latest_failed_runs(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    # Given
    config_path = tmp_path / "repos.yaml"
    _inventory(config_path)
    recorded: list[tuple[str, str, bool]] = []
    run = workflow_issue_automation.WorkflowRun(
        name="CI",
        head_sha="abcdef1234567890abcdef1234567890abcdef12",
        run_id=42,
        conclusion="failure",
        pr_number=0,
        run_url="https://github.com/jclee941/tmux/actions/runs/42",
    )
    snapshot = WorkflowSnapshot(key="1", status="completed", run=run)
    seen: dict[str, object] = {}

    def token_for_repo(**_: object) -> str:
        return "tok"

    monkeypatch.setattr(workflow_issue_automation, "installation_token_for_repo", token_for_repo)

    def fake_snapshots(**kwargs: object) -> list[WorkflowSnapshot]:
        seen.update(kwargs)
        return [snapshot]

    monkeypatch.setattr(downstream_ci_sweep, "_workflow_snapshots", fake_snapshots)

    def fake_record(**kwargs: object) -> list[str]:
        run_arg = kwargs["run"]
        assert isinstance(run_arg, workflow_issue_automation.WorkflowRun)
        repo_full_name = kwargs["repo_full_name"]
        assert isinstance(repo_full_name, str)
        dry_run = kwargs["dry_run"]
        assert isinstance(dry_run, bool)
        recorded.append((repo_full_name, run_arg.name, dry_run))
        return ["create-ci-failure:[ci] CI failed at abcdef12"]

    monkeypatch.setattr(workflow_issue_automation, "record_workflow_run", fake_record)

    # When
    result = downstream_ci_sweep.run_downstream_ci_sweep(
        app_id="123",
        private_key="key",
        owner="jclee941",
        dry_run=True,
        repo_names=None,
        config_path=config_path,
    )

    # Then
    assert result["actions"] == ["tmux:create-ci-failure:[ci] CI failed at abcdef12"]
    assert result["summary"] == {"status": "ok", "checked": 1, "failed": 0}
    assert recorded == [("jclee941/tmux", "CI", True)]
    assert seen["branch"] == "master"


def test_successful_managed_sweep_skips_legacy_title_based_close(monkeypatch: MonkeyPatch) -> None:
    run = workflow_issue_automation.WorkflowRun(
        name="CI",
        head_sha="fedcba1234567890abcdef1234567890abcdef12",
        run_id=44,
        conclusion="success",
        pr_number=0,
        run_url="https://github.com/jclee941/tmux/actions/runs/44",
    )

    def list_open_issues(**_: object) -> list[dict[str, object]]:
        return []

    monkeypatch.setattr(issue_maintenance, "list_open_issues", list_open_issues)

    def fail_record(**_: object) -> list[str]:
        raise AssertionError("managed success sweep must not call legacy record_workflow_run close path")

    monkeypatch.setattr(workflow_issue_automation, "record_workflow_run", fail_record)

    def fake_snapshots(**_: object) -> list[WorkflowSnapshot]:
        return [WorkflowSnapshot("1", "completed", run)]

    monkeypatch.setattr(downstream_ci_sweep, "_workflow_snapshots", fake_snapshots)

    actions = downstream_ci_sweep.sweep_repo_ci(
        token="tok",
        repo_full_name="jclee941/tmux",
        default_branch="master",
        dry_run=False,
        run_limit=50,
    )

    assert actions == ["noop:no-current-ci-state-change"]


def test_managed_scope_payload_uses_inventory(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    # Given
    config_path = tmp_path / "repos.yaml"
    _inventory(config_path)
    monkeypatch.setattr(downstream_ci_sweep, "DEFAULT_CONFIG_PATH", config_path)

    def fake_sweep(**kwargs: object) -> dict[str, object]:
        return {
            "dry_run": kwargs["dry_run"],
            "owner": kwargs["owner"],
            "scope": "managed_repos",
            "actions": ["tmux:noop:no-workflow-runs"],
            "repositories": [],
            "summary": {"status": "ok", "checked": 1, "failed": 0},
        }

    monkeypatch.setattr(downstream_ci_sweep, "run_downstream_ci_sweep", fake_sweep)

    # When
    result = downstream_ci_sweep.run_app_ci_failure_issues(
        app_id="123",
        private_key="key",
        payload={"scope": "managed_repos", "owner": "jclee941", "dry_run": True},
        workflow_run=None,
    )

    # Then
    assert result["scope"] == "managed_repos"
    assert result["actions"] == ["tmux:noop:no-workflow-runs"]


def test_managed_repo_sweep_reports_token_lookup_error(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    # Given
    config_path = tmp_path / "repos.yaml"
    _inventory(config_path)

    def broken_token(**_: object) -> str:
        raise requests.Timeout("token lookup timed out")

    monkeypatch.setattr(workflow_issue_automation, "installation_token_for_repo", broken_token)

    # When
    result = downstream_ci_sweep.run_downstream_ci_sweep(
        app_id="123",
        private_key="key",
        owner="jclee941",
        dry_run=True,
        repo_names=None,
        config_path=config_path,
    )

    # Then
    assert result["summary"] == {"status": "failed", "checked": 1, "failed": 1}
    assert result["repositories"] == [
        {
            "repo": "tmux",
            "status": "failed",
            "actions": [],
            "error": "Timeout",
            "detail": "request failed while sweeping repository",
        }
    ]


def test_ci_failure_endpoint_runs_managed_repo_sweep(monkeypatch: MonkeyPatch) -> None:
    # Given
    from jclee_bot.app import app as fastapi_app

    run = workflow_issue_automation.WorkflowRun(
        name="CI",
        head_sha="abcdef1234567890abcdef1234567890abcdef12",
        run_id=42,
        conclusion="failure",
        pr_number=0,
        run_url="https://github.com/jclee941/tmux/actions/runs/42",
    )
    snapshot = WorkflowSnapshot(key="1", status="completed", run=run)

    monkeypatch.setenv("CI_FAILURE_ISSUES_TOKEN", "ci")
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "key")

    def token_for_repo(**_: object) -> str:
        return "tok"

    def fake_snapshots(**_: object) -> list[WorkflowSnapshot]:
        return [snapshot]

    def fake_record(**_: object) -> list[str]:
        return ["create-ci-failure:[ci] CI failed at abcdef12"]

    monkeypatch.setattr(workflow_issue_automation, "installation_token_for_repo", token_for_repo)
    monkeypatch.setattr(downstream_ci_sweep, "_workflow_snapshots", fake_snapshots)
    monkeypatch.setattr(workflow_issue_automation, "record_workflow_run", fake_record)

    # When
    response = TestClient(fastapi_app, raise_server_exceptions=False).post(
        "/api/v1/ci_failure_issues",
        json={"scope": "managed_repos", "repos": ["tmux"], "dry_run": True},
        headers={"Authorization": "Bearer ci"},
    )

    # Then
    assert response.status_code == 200
    response_payload_object = cast(object, response.json())
    assert isinstance(response_payload_object, dict)
    response_payload = cast(dict[str, object], response_payload_object)
    assert response_payload["actions"] == ["tmux:create-ci-failure:[ci] CI failed at abcdef12"]
