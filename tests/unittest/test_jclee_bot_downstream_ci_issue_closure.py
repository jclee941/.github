from __future__ import annotations

from pytest import MonkeyPatch

from jclee_bot import downstream_ci_sweep, issue_maintenance, workflow_issue_automation


def test_successful_latest_run_closes_stale_ci_failures(monkeypatch: MonkeyPatch) -> None:
    closed: list[tuple[int, str]] = []
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
        "labels": [{"name": "ci-failure"}, {"name": "automated"}],
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

    def comment_issue(**kwargs: object) -> None:
        issue_number = kwargs["issue_number"]
        body = kwargs["body"]
        assert isinstance(issue_number, int)
        assert isinstance(body, str)
        closed.append((issue_number, body))

    def close_issue(**_: object) -> None:
        return None

    monkeypatch.setattr(issue_maintenance, "list_open_issues", list_open_issues)
    monkeypatch.setattr(issue_maintenance, "comment_issue", comment_issue)
    monkeypatch.setattr(issue_maintenance, "close_issue", close_issue)

    actions = downstream_ci_sweep.close_stale_ci_failures_for_workflow(
        token="tok",
        repo_full_name="jclee941/tmux",
        run=run,
        dry_run=False,
    )

    assert actions == ["close-stale-ci-failure:7:CI"]
    assert closed == [
        (
            7,
            (
                "Resolved: latest CI run 44 concluded success on "
                "fedcba1234567890abcdef1234567890abcdef12.\n\n_jclee-bot에의해자동화됨._"
            ),
        )
    ]
