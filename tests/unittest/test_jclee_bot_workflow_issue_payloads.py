from __future__ import annotations

from jclee_bot import workflow_issue_automation


def test_cancelled_workflow_run_is_not_recorded_as_failure() -> None:
    run = workflow_issue_automation.WorkflowRun(
        name="Runtime Health Check",
        head_sha="abcdef1234567890abcdef1234567890abcdef12",
        run_id=123,
        conclusion="cancelled",
        pr_number=0,
        run_url="https://github.com/jclee941/jclee-bot/actions/runs/123",
    )

    actions = workflow_issue_automation.record_workflow_run(
        token="tok",
        repo_full_name="jclee941/jclee-bot",
        run=run,
        dry_run=True,
    )

    assert actions == ["ignore-neutral:Runtime Health Check"]


def test_success_sweeps_legacy_on_payload_default_branch(monkeypatch) -> None:
    run = workflow_issue_automation.WorkflowRun(
        name="Runtime Health Check",
        head_sha="abcdef1234567890abcdef1234567890abcdef12",
        run_id=123,
        conclusion="success",
        pr_number=0,
        run_url="https://github.com/jclee941/jclee-bot/actions/runs/123",
    )
    seen: dict[str, str] = {}

    monkeypatch.setattr(
        workflow_issue_automation,
        "close_recovered_workflow_issues",
        lambda **kwargs: [],
    )

    def fake_sweep(**kwargs) -> list[str]:
        seen["default_branch"] = kwargs["default_branch"]
        return []

    monkeypatch.setattr(workflow_issue_automation, "sweep_legacy_failure_issues", fake_sweep)

    actions = workflow_issue_automation.record_workflow_run(
        token="tok",
        repo_full_name="jclee941/jclee-bot",
        run=run,
        default_branch="master",
        dry_run=False,
    )

    assert actions == []
    assert seen == {"default_branch": "master"}


def test_ci_failure_endpoint_uses_repository_object_full_name(monkeypatch) -> None:
    from jclee_bot import app as app_module

    seen: dict[str, str] = {}

    def fake_installation_token_for_repo(**kwargs) -> str | None:
        seen["repo_full_name"] = kwargs["repo_full_name"]
        return None

    monkeypatch.setattr(workflow_issue_automation, "installation_token_for_repo", fake_installation_token_for_repo)

    result = app_module._run_app_ci_failure_issues(
        app_id="123",
        private_key="key",
        payload={"repository": {"full_name": "jclee941/jclee-bot"}, "dry_run": True},
    )

    assert result == {"dry_run": True, "actions": [], "error": "installation token unavailable"}
    assert seen == {"repo_full_name": "jclee941/jclee-bot"}
