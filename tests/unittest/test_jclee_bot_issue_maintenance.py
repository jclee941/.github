from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jclee_bot import issue_maintenance


def _issue(
    *,
    number: int = 7,
    updated_days_ago: int = 31,
    labels: list[dict[str, str]] | None = None,
    state: str = "open",
) -> dict[str, object]:
    updated_at = datetime(2026, 6, 19, tzinfo=UTC) - timedelta(days=updated_days_ago)
    return {
        "number": number,
        "title": "Bug: stale issue",
        "body": "Needs triage",
        "state": state,
        "updated_at": updated_at.isoformat().replace("+00:00", "Z"),
        "created_at": updated_at.isoformat().replace("+00:00", "Z"),
        "labels": labels or [],
    }


class TestIssueMaintenanceDecisions:
    def test_marks_open_non_exempt_issue_after_thirty_days(self) -> None:
        # Given
        now = datetime(2026, 6, 19, tzinfo=UTC)

        assert issue_maintenance.should_mark_stale(_issue(updated_days_ago=30), now=now) is True
        assert issue_maintenance.should_mark_stale(_issue(labels=[{"name": "security"}]), now=now) is False
        assert issue_maintenance.should_mark_stale(_issue(labels=[{"name": "stale"}]), now=now) is False

    def test_closes_existing_stale_issue_after_seven_days_without_activity(self) -> None:
        # Given
        now = datetime(2026, 6, 19, tzinfo=UTC)

        assert issue_maintenance.should_close_stale(
            _issue(updated_days_ago=7, labels=[{"name": "stale"}]),
            now=now,
        ) is True
        assert issue_maintenance.should_close_stale(
            _issue(updated_days_ago=6, labels=[{"name": "stale"}]),
            now=now,
        ) is False

    def test_closes_duplicate_bot_review_findings(self) -> None:
        # Given
        issue = _issue(
            labels=[
                {"name": "duplicate"},
                {"name": "jclee-bot"},
                {"name": "review-finding"},
                {"name": "security"},
                {"name": "critical"},
            ],
        )

        # Then
        assert issue_maintenance.should_close_duplicate_bot_review(issue) is True
        assert issue_maintenance.should_close_duplicate_bot_review(_issue(labels=[{"name": "duplicate"}])) is False

    def test_closes_empty_bot_review_findings(self) -> None:
        # Given
        issue = _issue(
            labels=[
                {"name": "jclee-bot"},
                {"name": "review-finding"},
                {"name": "security"},
                {"name": "critical"},
            ],
        )
        issue["body"] = "\n".join(
            [
                "<!-- jclee-bot-review-finding: deadbeef -->",
                "",
                "## Automated Review Finding",
                "",
                "## Finding",
                "",
                "아니요",
                "",
                "## Suggested Action",
                "",
                "Review the PR finding.",
            ]
        )

        # Then
        assert issue_maintenance.should_close_empty_bot_review(issue) is True
        assert issue_maintenance.should_close_empty_bot_review(_issue(labels=[{"name": "jclee-bot"}])) is False

    def test_computes_issue_statistics_from_open_non_pr_issues(self) -> None:
        # Given
        now = datetime(2026, 6, 19, tzinfo=UTC)
        issues = [
            _issue(number=1, labels=[{"name": "bug"}]),
            _issue(number=2, labels=[{"name": "stale"}], updated_days_ago=5),
            _issue(number=3, updated_days_ago=2),
            {**_issue(number=4), "pull_request": {"url": "https://api.github.com/pulls/4"}},
        ]

        # When
        stats = issue_maintenance.issue_stats(issues, now=now)

        # Then
        assert stats["total"] == 3
        assert stats["bug"] == 1
        assert stats["stale"] == 1
        assert stats["no_labels"] == 1
        assert stats["old"] == 1
