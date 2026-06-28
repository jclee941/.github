from __future__ import annotations

from datetime import UTC, datetime, timedelta

import requests

from jclee_bot import issue_maintenance

IssueValue = int | str | list[dict[str, str]]


def _issue(
    *,
    number: int = 7,
    updated_days_ago: int = 31,
    labels: list[dict[str, str]] | None = None,
    state: str = "open",
) -> dict[str, IssueValue]:
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


class TestMaintainRepo:
    def test_issue_list_error_is_reported_without_blocking_pr_maintenance(self, monkeypatch) -> None:
        # Given
        now = datetime(2026, 6, 19, tzinfo=UTC)
        monkeypatch.setattr(
            issue_maintenance,
            "list_open_issues",
            lambda **kwargs: (_ for _ in ()).throw(requests.ConnectionError("network down")),
        )
        monkeypatch.setattr(
            issue_maintenance.pr_maintenance,
            "maintain_pull_requests",
            lambda **kwargs: ["close-pr:9:failed-checks"],
        )

        # When
        result = issue_maintenance.maintain_repo(
            token="tok",
            repo_full_name="jclee941/propose",
            dry_run=True,
            now=now,
        )

        # Then
        assert result["actions"] == ["issue-list-error:ConnectionError", "close-pr:9:failed-checks"]
        assert result["stats"]["total"] == 0

    def test_dry_run_reports_mark_and_close_actions_without_mutating(self, monkeypatch) -> None:
        # Given
        now = datetime(2026, 6, 19, tzinfo=UTC)
        monkeypatch.setattr(
            issue_maintenance,
            "list_open_issues",
            lambda **kwargs: [
                _issue(number=1, updated_days_ago=31),
                _issue(number=2, updated_days_ago=8, labels=[{"name": "stale"}]),
            ],
        )
        mutations: list[str] = []
        monkeypatch.setattr(issue_maintenance, "comment_issue", lambda **kwargs: mutations.append("comment"))
        monkeypatch.setattr(issue_maintenance, "close_issue", lambda **kwargs: mutations.append("close"))
        monkeypatch.setattr(issue_maintenance.pr_maintenance, "maintain_pull_requests", lambda **kwargs: [])

        # When
        result = issue_maintenance.maintain_repo(
            token="tok",
            repo_full_name="jclee941/propose",
            dry_run=True,
            now=now,
        )

        # Then
        assert result["actions"] == ["mark-stale:1", "close-stale:2"]
        assert mutations == []

    def test_dry_run_reports_duplicate_bot_review_cleanup(self, monkeypatch) -> None:
        # Given
        now = datetime(2026, 6, 19, tzinfo=UTC)
        monkeypatch.setattr(
            issue_maintenance,
            "list_open_issues",
            lambda **kwargs: [
                _issue(
                    number=3,
                    updated_days_ago=1,
                    labels=[
                        {"name": "duplicate"},
                        {"name": "jclee-bot"},
                        {"name": "review-finding"},
                        {"name": "security"},
                        {"name": "critical"},
                    ],
                ),
            ],
        )
        mutations: list[str] = []
        monkeypatch.setattr(issue_maintenance, "comment_issue", lambda **kwargs: mutations.append("comment"))
        monkeypatch.setattr(issue_maintenance, "close_issue", lambda **kwargs: mutations.append("close"))
        monkeypatch.setattr(issue_maintenance.pr_maintenance, "maintain_pull_requests", lambda **kwargs: [])

        # When
        result = issue_maintenance.maintain_repo(
            token="tok",
            repo_full_name="jclee941/propose",
            dry_run=True,
            now=now,
        )

        # Then
        assert result["actions"] == ["close-duplicate-review:3"]
        assert mutations == []

    def test_dry_run_reports_empty_bot_review_cleanup(self, monkeypatch) -> None:
        # Given
        now = datetime(2026, 6, 19, tzinfo=UTC)
        empty_finding = _issue(
            number=4,
            updated_days_ago=1,
            labels=[
                {"name": "jclee-bot"},
                {"name": "review-finding"},
                {"name": "security"},
                {"name": "critical"},
            ],
        )
        empty_finding["body"] = "## Finding\n\n없음\n\n## Suggested Action\n\nReview."
        monkeypatch.setattr(issue_maintenance, "list_open_issues", lambda **kwargs: [empty_finding])
        mutations: list[str] = []
        monkeypatch.setattr(issue_maintenance, "comment_issue", lambda **kwargs: mutations.append("comment"))
        monkeypatch.setattr(issue_maintenance, "close_issue", lambda **kwargs: mutations.append("close"))
        monkeypatch.setattr(issue_maintenance.pr_maintenance, "maintain_pull_requests", lambda **kwargs: [])

        # When
        result = issue_maintenance.maintain_repo(
            token="tok",
            repo_full_name="jclee941/propose",
            dry_run=True,
            now=now,
        )

        # Then
        assert result["actions"] == ["close-empty-review:4"]
        assert mutations == []

    def test_dry_run_reports_recovered_repo_health_cleanup(self, monkeypatch) -> None:
        # Given
        now = datetime(2026, 6, 19, tzinfo=UTC)
        monkeypatch.setattr(
            issue_maintenance,
            "list_open_issues",
            lambda **kwargs: [
                _issue(
                    number=5,
                    updated_days_ago=1,
                    labels=[{"name": "documentation"}, {"name": "repo-health"}],
                )
                | {"title": "[BOT] 필수 문서 누락: CONTRIBUTING.md, LICENSE"},
            ],
        )
        monkeypatch.setattr(issue_maintenance, "missing_repo_health_files", lambda **kwargs: [])
        monkeypatch.setattr(issue_maintenance.pr_maintenance, "maintain_pull_requests", lambda **kwargs: [])

        # When
        result = issue_maintenance.maintain_repo(
            token="tok",
            repo_full_name="jclee941/bug",
            dry_run=True,
            now=now,
        )

        # Then
        assert result["actions"] == ["close-recovered-repo-health:5"]

    def test_dry_run_keeps_unrecovered_repo_health_issue(self, monkeypatch) -> None:
        # Given
        now = datetime(2026, 6, 19, tzinfo=UTC)
        monkeypatch.setattr(
            issue_maintenance,
            "list_open_issues",
            lambda **kwargs: [
                _issue(
                    number=6,
                    updated_days_ago=1,
                    labels=[{"name": "documentation"}, {"name": "repo-health"}],
                )
                | {"title": "[BOT] 필수 문서 누락: CONTRIBUTING.md, LICENSE"},
            ],
        )
        monkeypatch.setattr(
            issue_maintenance,
            "missing_repo_health_files",
            lambda **kwargs: ["CONTRIBUTING.md", "LICENSE"],
        )
        monkeypatch.setattr(issue_maintenance.pr_maintenance, "maintain_pull_requests", lambda **kwargs: [])

        # When
        result = issue_maintenance.maintain_repo(
            token="tok",
            repo_full_name="jclee941/bug",
            dry_run=True,
            now=now,
        )

        # Then
        assert result["actions"] == ["keep-repo-health:6:missing:CONTRIBUTING.md,LICENSE"]

    def test_mutating_run_marks_stale_closes_stale_and_updates_summary(self, monkeypatch) -> None:
        # Given
        now = datetime(2026, 6, 19, tzinfo=UTC)
        monkeypatch.setattr(
            issue_maintenance,
            "list_open_issues",
            lambda **kwargs: [
                _issue(number=1, updated_days_ago=31),
                _issue(number=2, updated_days_ago=8, labels=[{"name": "stale"}]),
            ],
        )
        mutations: list[str] = []
        monkeypatch.setattr(issue_maintenance, "ensure_label", lambda **kwargs: mutations.append("ensure"))
        monkeypatch.setattr(
            issue_maintenance.issue_management,
            "add_labels",
            lambda **kwargs: mutations.append("add"),
        )
        monkeypatch.setattr(issue_maintenance, "comment_issue", lambda **kwargs: mutations.append("comment"))
        monkeypatch.setattr(issue_maintenance, "close_issue", lambda **kwargs: mutations.append("close"))
        monkeypatch.setattr(
            issue_maintenance,
            "upsert_summary_issue",
            lambda **kwargs: "create-summary",
        )
        monkeypatch.setattr(
            issue_maintenance.pr_maintenance,
            "maintain_pull_requests",
            lambda **kwargs: ["close-pr:9:failed-checks"],
        )

        # When
        result = issue_maintenance.maintain_repo(
            token="tok",
            repo_full_name="jclee941/propose",
            dry_run=False,
            now=now,
        )

        # Then
        assert result["actions"] == ["close-pr:9:failed-checks", "mark-stale:1", "close-stale:2", "create-summary"]
        assert mutations == ["ensure", "add", "comment", "comment", "close"]
