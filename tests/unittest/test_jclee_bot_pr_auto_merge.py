from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jclee_bot import pr_auto_merge, pr_maintenance

NOW = datetime(2026, 6, 19, 12, tzinfo=UTC)


def _github_time(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _pr(
    *,
    number: int = 7,
    title: str = "chore(deps): bump urllib3",
    updated_hours_ago: int = 1,
    head_ref: str = "dependabot/pip/urllib3",
    head_sha: str = "abc123",
    node_id: str = "PR_kwDOExample",
    auto_merge: dict[str, object] | None = None,
    draft: bool = False,
) -> dict[str, object]:
    updated_at = NOW - timedelta(hours=updated_hours_ago)
    return {
        "number": number,
        "node_id": node_id,
        "title": title,
        "updated_at": _github_time(updated_at),
        "created_at": _github_time(updated_at),
        "auto_merge": auto_merge,
        "draft": draft,
        "head": {
            "ref": head_ref,
            "sha": head_sha,
            "repo": {"full_name": "jclee941/propose"},
        },
    }


class TestPullRequestAutoMergeDecisions:
    def test_enables_auto_merge_for_clean_existing_automation_pr(self) -> None:
        # Given
        pr = _pr(number=37)

        # When
        plan = pr_auto_merge.plan_pr_auto_merge(
            pr,
            checks=pr_maintenance.CheckSummary(failed=(), pending=()),
        )

        # Then
        assert plan is not None
        assert plan.number == 37
        assert plan.pull_request_id == "PR_kwDOExample"

    def test_skips_auto_merge_for_pending_checks(self) -> None:
        # Given
        pr = _pr(number=38)
        checks = pr_maintenance.CheckSummary(failed=(), pending=("build",))

        # When
        plan = pr_auto_merge.plan_pr_auto_merge(pr, checks=checks)

        # Then
        assert plan is None

    def test_skips_auto_merge_for_failed_draft_human_or_already_enabled_prs(self) -> None:
        # Given
        checks = pr_maintenance.CheckSummary(failed=(), pending=())
        failed_checks = pr_maintenance.CheckSummary(failed=("test",), pending=())

        # Then
        assert pr_auto_merge.plan_pr_auto_merge(_pr(), checks=failed_checks) is None
        assert pr_auto_merge.plan_pr_auto_merge(_pr(draft=True), checks=checks) is None
        assert (
            pr_auto_merge.plan_pr_auto_merge(
                _pr(title="feat: add profile page", head_ref="feature/profile"),
                checks=checks,
            )
            is None
        )
        assert pr_auto_merge.plan_pr_auto_merge(_pr(auto_merge={"enabled_by": {}}), checks=checks) is None
