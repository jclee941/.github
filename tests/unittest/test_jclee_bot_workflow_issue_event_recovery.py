from __future__ import annotations

from _pytest.monkeypatch import MonkeyPatch

from jclee_bot import workflow_issue_automation


def test_success_event_preserves_current_ci_failure_when_body_references_pr(monkeypatch: MonkeyPatch) -> None:
    # Given
    closed: list[int] = []
    issue_body = "\n".join(
        [
            "## CI Failure",
            "",
            "- **Workflow:** Sanity",
            "- **Commit:** abcdef1234567890abcdef1234567890abcdef12",
            "- **PR:** #686",
            "- **Run:** https://github.com/jclee941/.github/actions/runs/100",
        ]
    )

    def open_pr_failure_issue(*, token: str, repo_full_name: str, labels: str | None = None) -> list[dict[str, object]]:
        del token, repo_full_name, labels
        return [
            {
                "number": 694,
                "title": "[ci] Sanity failed at abcdef12",
                "body": issue_body,
            }
        ]

    def fake_close(*, token: str, repo_full_name: str, issue_number: int, body: str) -> None:
        del token, repo_full_name, body
        closed.append(issue_number)

    def no_legacy_sweep(*, token: str, repo_full_name: str, default_branch: str, dry_run: bool) -> list[str]:
        del token, repo_full_name, default_branch, dry_run
        return []

    monkeypatch.setattr(workflow_issue_automation, "_open_issues", open_pr_failure_issue)
    monkeypatch.setattr(workflow_issue_automation, "_close", fake_close)
    monkeypatch.setattr(workflow_issue_automation, "sweep_legacy_failure_issues", no_legacy_sweep)

    # When
    actions = workflow_issue_automation.record_workflow_run(
        token="tok",
        repo_full_name="jclee941/.github",
        run=workflow_issue_automation.WorkflowRun(
            name="Sanity",
            head_sha="abcdef1234567890abcdef1234567890abcdef12",
            run_id=123,
            conclusion="success",
            pr_number=0,
            run_url="https://github.com/jclee941/.github/actions/runs/123",
        ),
        dry_run=False,
    )

    # Then
    assert actions == []
    assert closed == []
