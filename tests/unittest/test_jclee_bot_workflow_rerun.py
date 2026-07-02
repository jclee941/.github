from __future__ import annotations

from _pytest.monkeypatch import MonkeyPatch

from jclee_bot import app_automation, workflow_issue_automation, workflow_rerun
from jclee_bot.workflow_rerun import CiFailureIssue, IssueBodyPatch, RerunTarget


def test_transient_failure_reruns_failed_jobs_once(monkeypatch: MonkeyPatch) -> None:
    # Given
    run = workflow_issue_automation.WorkflowRun(
        name="Runtime Health Check",
        head_sha="abcdef1234567890abcdef1234567890abcdef12",
        run_id=123,
        conclusion="failure",
        pr_number=4,
        run_url="https://github.com/jclee941/jclee-bot/actions/runs/123",
    )
    reruns: list[int] = []
    issues: list[CiFailureIssue] = []

    def fake_find_issue(**_: object) -> CiFailureIssue | None:
        return issues[0] if issues else None

    def fake_rerun_failed_jobs(target: RerunTarget) -> None:
        assert target.token == "tok"
        assert target.repo_full_name == "jclee941/jclee-bot"
        reruns.append(target.run_id)

    def fake_create_issue(*, body: str, **_: object) -> int:
        issues.append(CiFailureIssue(number=9, body=body))
        return 9

    def fake_patch_issue_body(target: IssueBodyPatch) -> None:
        issues[0] = CiFailureIssue(number=target.issue_number, body=target.body)

    def noop_labels(**_: object) -> None:
        return None

    monkeypatch.setattr(workflow_rerun, "rerun_failed_jobs", fake_rerun_failed_jobs)
    monkeypatch.setattr(workflow_issue_automation, "_find_ci_failure_issue", fake_find_issue)
    monkeypatch.setattr(workflow_issue_automation, "_ensure_ci_labels", noop_labels)
    monkeypatch.setattr(workflow_issue_automation, "_create_issue", fake_create_issue)
    monkeypatch.setattr(workflow_rerun, "patch_issue_body", fake_patch_issue_body)

    # When
    first_actions = workflow_issue_automation.record_workflow_run(
        token="tok",
        repo_full_name="jclee941/jclee-bot",
        run=run,
        dry_run=False,
    )
    second_actions = workflow_issue_automation.record_workflow_run(
        token="tok",
        repo_full_name="jclee941/jclee-bot",
        run=run,
        dry_run=False,
    )

    # Then
    assert reruns == [123]
    assert "rerun-failed-jobs:123" in first_actions
    assert "skip-rerun-bounded:123" in second_actions


def test_malformed_or_neutral_workflow_run_never_reruns(monkeypatch: MonkeyPatch) -> None:
    # Given
    reruns: list[int] = []

    def fake_rerun_failed_jobs(target: RerunTarget) -> None:
        reruns.append(target.run_id)

    monkeypatch.setattr(workflow_rerun, "rerun_failed_jobs", fake_rerun_failed_jobs)
    malformed_payload = {
        "workflow_run": {
            "name": "Sanity",
            "head_sha": "abcdef1234567890abcdef1234567890abcdef12",
            "id": "not-a-number",
            "conclusion": "failure",
            "pr_number": 4,
            "run_url": "https://github.com/jclee941/jclee-bot/actions/runs/not-a-number",
        },
    }
    neutral_run = workflow_issue_automation.WorkflowRun(
        name="Sanity",
        head_sha="abcdef1234567890abcdef1234567890abcdef12",
        run_id=124,
        conclusion="cancelled",
        pr_number=4,
        run_url="https://github.com/jclee941/jclee-bot/actions/runs/124",
    )

    # When
    malformed_run = app_automation.workflow_run_from_payload(malformed_payload)
    neutral_actions = workflow_issue_automation.record_workflow_run(
        token="tok",
        repo_full_name="jclee941/jclee-bot",
        run=neutral_run,
        dry_run=False,
    )

    # Then
    assert malformed_run is None
    assert neutral_actions == ["ignore-neutral:Sanity"]
    assert reruns == []


def test_existing_unmarked_issue_records_rerun_marker(monkeypatch: MonkeyPatch) -> None:
    # Given
    run = workflow_issue_automation.WorkflowRun(
        name="Runtime Health Check",
        head_sha="abcdef1234567890abcdef1234567890abcdef12",
        run_id=123,
        conclusion="failure",
        pr_number=4,
        run_url="https://github.com/jclee941/jclee-bot/actions/runs/123",
    )
    patched_bodies: list[str] = []
    reruns: list[int] = []

    def fake_find_issue(**_: object) -> CiFailureIssue:
        return CiFailureIssue(number=9, body="## CI Failure\n\nexisting body")

    def fake_patch_issue_body(target: IssueBodyPatch) -> None:
        assert target.issue_number == 9
        patched_bodies.append(target.body)

    def fake_rerun_failed_jobs(target: RerunTarget) -> None:
        reruns.append(target.run_id)

    def noop_comment(**_: object) -> None:
        return None

    monkeypatch.setattr(workflow_issue_automation, "_find_ci_failure_issue", fake_find_issue)
    monkeypatch.setattr(workflow_rerun, "patch_issue_body", fake_patch_issue_body)
    monkeypatch.setattr(workflow_rerun, "rerun_failed_jobs", fake_rerun_failed_jobs)
    monkeypatch.setattr(workflow_issue_automation, "_comment", noop_comment)

    # When
    actions = workflow_issue_automation.record_workflow_run(
        token="tok",
        repo_full_name="jclee941/jclee-bot",
        run=run,
        dry_run=False,
    )

    # Then
    assert actions == ["comment-ci-failure:9", "rerun-failed-jobs:123"]
    assert reruns == [123]
    assert patched_bodies == ["## CI Failure\n\nexisting body\n\n<!-- jclee-bot:ci-failure-rerun-run-id=123 -->"]


def test_new_issue_does_not_record_marker_when_rerun_request_fails(monkeypatch: MonkeyPatch) -> None:
    # Given
    run = workflow_issue_automation.WorkflowRun(
        name="Runtime Health Check",
        head_sha="abcdef1234567890abcdef1234567890abcdef12",
        run_id=123,
        conclusion="failure",
        pr_number=4,
        run_url="https://github.com/jclee941/jclee-bot/actions/runs/123",
    )
    created_bodies: list[str] = []
    patched_bodies: list[str] = []

    def fake_create_issue(*, body: str, **_: object) -> int:
        created_bodies.append(body)
        return 9

    def fail_rerun_failed_jobs(target: RerunTarget) -> None:
        raise RuntimeError(f"rerun failed for {target.run_id}")

    def fake_patch_issue_body(target: IssueBodyPatch) -> None:
        patched_bodies.append(target.body)

    def no_existing_issue(**_: object) -> None:
        return None

    def noop_labels(**_: object) -> None:
        return None

    monkeypatch.setattr(workflow_issue_automation, "_find_ci_failure_issue", no_existing_issue)
    monkeypatch.setattr(workflow_issue_automation, "_ensure_ci_labels", noop_labels)
    monkeypatch.setattr(workflow_issue_automation, "_create_issue", fake_create_issue)
    monkeypatch.setattr(workflow_rerun, "rerun_failed_jobs", fail_rerun_failed_jobs)
    monkeypatch.setattr(workflow_rerun, "patch_issue_body", fake_patch_issue_body)

    try:
        _ = workflow_issue_automation.record_workflow_run(
            token="tok",
            repo_full_name="jclee941/jclee-bot",
            run=run,
            dry_run=False,
        )
    except RuntimeError as exc:
        assert str(exc) == "rerun failed for 123"
    else:
        raise AssertionError("rerun failure must propagate")
    assert workflow_rerun.rerun_marker(123) not in created_bodies[0]
    assert patched_bodies == []
