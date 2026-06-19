from __future__ import annotations

from datetime import UTC, datetime, timedelta

import requests

from jclee_bot import pr_maintenance

NOW = datetime(2026, 6, 19, 12, tzinfo=UTC)


def _github_time(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _pr(
    *,
    number: int = 7,
    title: str = "chore(deps): bump urllib3",
    updated_hours_ago: int = 3,
    head_ref: str = "dependabot/pip/urllib3",
    repo_full_name: str = "jclee941/propose",
    head_sha: str = "abc123",
) -> dict[str, object]:
    updated_at = NOW - timedelta(hours=updated_hours_ago)
    return {
        "number": number,
        "title": title,
        "updated_at": _github_time(updated_at),
        "created_at": _github_time(updated_at),
        "head": {
            "ref": head_ref,
            "sha": head_sha,
            "repo": {"full_name": repo_full_name},
        },
        "base": {"repo": {"full_name": repo_full_name}},
    }


def _run(*, run_id: int = 42, status: str = "queued", created_minutes_ago: int = 45) -> dict[str, object]:
    created_at = NOW - timedelta(minutes=created_minutes_ago)
    return {
        "id": run_id,
        "name": "CI",
        "status": status,
        "created_at": _github_time(created_at),
    }


class TestPullRequestMaintenanceDecisions:
    def test_closes_downstream_docs_sync_pr_without_waiting_for_ci(self) -> None:
        # Given
        pr = _pr(
            number=17,
            title="docs: sync standard templates from jclee941/.github",
            updated_hours_ago=1,
            head_ref="bot/docs-sync",
        )

        # When
        plan = pr_maintenance.plan_pr_cleanup(
            pr,
            checks=pr_maintenance.CheckSummary(failed=(), pending=()),
            repo_full_name="jclee941/propose",
            now=NOW,
        )

        # Then
        assert plan is not None
        assert plan.number == 17
        assert plan.reason == "docs-sync"
        assert plan.can_delete_branch is True

    def test_closes_stale_failed_automation_pr(self) -> None:
        # Given
        pr = _pr(number=21, updated_hours_ago=2)

        # When
        plan = pr_maintenance.plan_pr_cleanup(
            pr,
            checks=pr_maintenance.CheckSummary(failed=("test",), pending=()),
            repo_full_name="jclee941/propose",
            now=NOW,
        )

        # Then
        assert plan is not None
        assert plan.reason == "failed-checks"

    def test_keeps_clean_or_human_prs_open(self) -> None:
        # Given
        automation_pr = _pr(updated_hours_ago=2)
        human_pr = _pr(title="feat: add profile page", head_ref="feature/profile", updated_hours_ago=6)

        # Then
        assert (
            pr_maintenance.plan_pr_cleanup(
                automation_pr,
                checks=pr_maintenance.CheckSummary(failed=(), pending=()),
                repo_full_name="jclee941/propose",
                now=NOW,
            )
            is None
        )
        assert (
            pr_maintenance.plan_pr_cleanup(
                human_pr,
                checks=pr_maintenance.CheckSummary(failed=("test",), pending=()),
                repo_full_name="jclee941/propose",
                now=NOW,
            )
            is None
        )

    def test_closes_old_pending_automation_pr_but_keeps_fresh_pending_pr(self) -> None:
        # Given
        old_pr = _pr(number=31, updated_hours_ago=3)
        fresh_pr = _pr(number=32, updated_hours_ago=1)
        checks = pr_maintenance.CheckSummary(failed=(), pending=("build",))

        # When
        old_plan = pr_maintenance.plan_pr_cleanup(old_pr, checks=checks, repo_full_name="jclee941/propose", now=NOW)
        fresh_plan = pr_maintenance.plan_pr_cleanup(fresh_pr, checks=checks, repo_full_name="jclee941/propose", now=NOW)

        # Then
        assert old_plan is not None
        assert old_plan.reason == "pending-checks"
        assert fresh_plan is None


class TestMaintainPullRequests:
    def test_dry_run_reports_pr_and_run_cleanup_without_mutating(self, monkeypatch) -> None:
        # Given
        pr = _pr(number=9, updated_hours_ago=2)
        run = _run(run_id=77, status="queued")
        mutations: list[str] = []

        monkeypatch.setattr(pr_maintenance, "list_open_pull_requests", lambda **kwargs: [pr])
        monkeypatch.setattr(
            pr_maintenance,
            "commit_check_summary",
            lambda **kwargs: pr_maintenance.CheckSummary(failed=("test",), pending=()),
        )
        monkeypatch.setattr(pr_maintenance, "list_active_workflow_runs", lambda **kwargs: [run])
        monkeypatch.setattr(pr_maintenance, "comment_pr", lambda **kwargs: mutations.append("comment"))
        monkeypatch.setattr(pr_maintenance, "close_pr", lambda **kwargs: mutations.append("close"))
        monkeypatch.setattr(pr_maintenance, "delete_head_branch", lambda **kwargs: mutations.append("delete"))
        monkeypatch.setattr(pr_maintenance, "cancel_workflow_run", lambda **kwargs: mutations.append("cancel"))

        # When
        actions = pr_maintenance.maintain_pull_requests(
            token="tok",
            repo_full_name="jclee941/propose",
            dry_run=True,
            now=NOW,
        )

        # Then
        assert actions == ["close-pr:9:failed-checks", "delete-pr-branch:9", "cancel-run:77:queued"]
        assert mutations == []

    def test_mutating_run_comments_closes_deletes_branch_and_cancels_runs(self, monkeypatch) -> None:
        # Given
        pr = _pr(number=9, updated_hours_ago=2)
        run = _run(run_id=77, status="in_progress")
        mutations: list[str] = []

        monkeypatch.setattr(pr_maintenance, "list_open_pull_requests", lambda **kwargs: [pr])
        monkeypatch.setattr(
            pr_maintenance,
            "commit_check_summary",
            lambda **kwargs: pr_maintenance.CheckSummary(failed=("test",), pending=()),
        )
        monkeypatch.setattr(pr_maintenance, "list_active_workflow_runs", lambda **kwargs: [run])
        monkeypatch.setattr(pr_maintenance, "comment_pr", lambda **kwargs: mutations.append("comment"))
        monkeypatch.setattr(pr_maintenance, "close_pr", lambda **kwargs: mutations.append("close"))
        monkeypatch.setattr(pr_maintenance, "delete_head_branch", lambda **kwargs: mutations.append("delete"))
        monkeypatch.setattr(pr_maintenance, "cancel_workflow_run", lambda **kwargs: mutations.append("cancel"))

        # When
        actions = pr_maintenance.maintain_pull_requests(
            token="tok",
            repo_full_name="jclee941/propose",
            dry_run=False,
            now=NOW,
        )

        # Then
        assert actions == ["close-pr:9:failed-checks", "delete-pr-branch:9", "force-cancel-run:77:in_progress"]
        assert mutations == ["comment", "close", "delete", "cancel"]

    def test_records_github_api_errors_without_aborting_maintenance(self, monkeypatch) -> None:
        # Given
        monkeypatch.setattr(
            pr_maintenance,
            "list_open_pull_requests",
            lambda **kwargs: (_ for _ in ()).throw(requests.ConnectionError("network down")),
        )
        monkeypatch.setattr(
            pr_maintenance,
            "list_active_workflow_runs",
            lambda **kwargs: (_ for _ in ()).throw(requests.Timeout("network slow")),
        )

        # When
        actions = pr_maintenance.maintain_pull_requests(
            token="tok",
            repo_full_name="jclee941/propose",
            dry_run=True,
            now=NOW,
        )

        # Then
        assert actions == ["pr-list-error:ConnectionError", "run-list-error:Timeout"]
