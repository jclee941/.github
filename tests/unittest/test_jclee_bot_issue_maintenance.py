from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

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


class TestMaintainRepo:
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
        assert result["actions"] == ["mark-stale:1", "close-stale:2", "create-summary", "close-pr:9:failed-checks"]
        assert mutations == ["ensure", "add", "comment", "comment", "close"]


class TestRunAppMaintenance:
    def test_missing_repo_config_falls_back_to_owner_scoped_app_repos(self, monkeypatch) -> None:
        # Given
        monkeypatch.setattr(issue_maintenance, "managed_repo_names", lambda config_path=None: None)
        monkeypatch.setattr(issue_maintenance, "app_installations", lambda **kwargs: [{"id": 42}])
        monkeypatch.setattr(issue_maintenance.github_checks, "installation_token", lambda *args: "tok")
        monkeypatch.setattr(
            issue_maintenance,
            "installation_repositories",
            lambda **kwargs: [
                {"full_name": "jclee941/propose", "name": "propose"},
                {"full_name": "other/propose", "name": "propose"},
            ],
        )
        maintained: list[str] = []
        monkeypatch.setattr(
            issue_maintenance,
            "maintain_repo",
            lambda **kwargs: maintained.append(kwargs["repo_full_name"]) or {"repo": kwargs["repo_full_name"]},
        )

        # When
        result = issue_maintenance.run_app_maintenance(
            app_id="123",
            private_key="key",
            owner="jclee941",
            dry_run=True,
        )

        # Then
        assert maintained == ["jclee941/propose"]
        assert result == {"dry_run": True, "repositories": [{"repo": "jclee941/propose"}]}

    def test_managed_repo_names_returns_none_when_config_file_is_missing(self, tmp_path) -> None:
        assert issue_maintenance.managed_repo_names(tmp_path / "missing.yml") is None


class TestIssueMaintenanceEndpoint:
    def test_rejects_missing_maintenance_token(self, monkeypatch) -> None:
        # Given
        from jclee_bot import app as app_module

        monkeypatch.delenv("ISSUE_MAINTENANCE_TOKEN", raising=False)

        # When
        response = TestClient(app_module.app, raise_server_exceptions=False).post(
            "/api/v1/issue_maintenance",
            json={"dry_run": True},
        )

        # Then
        assert response.status_code == 401

    def test_runs_maintenance_when_bearer_token_matches(self, monkeypatch) -> None:
        # Given
        from jclee_bot import app as app_module

        calls: list[dict[str, object]] = []

        def fake_run_app_maintenance(**kwargs) -> dict[str, object]:
            calls.append(kwargs)
            return {"dry_run": True, "repositories": []}

        monkeypatch.setenv("ISSUE_MAINTENANCE_TOKEN", "maint")
        monkeypatch.setenv("GITHUB_APP_ID", "123")
        monkeypatch.setenv("GITHUB_PRIVATE_KEY", "key")
        monkeypatch.setattr(app_module.issue_maintenance, "run_app_maintenance", fake_run_app_maintenance)

        # When
        response = TestClient(app_module.app, raise_server_exceptions=False).post(
            "/api/v1/issue_maintenance",
            json={"dry_run": True, "background": False},
            headers={"Authorization": "Bearer maint"},
        )

        # Then
        assert response.status_code == 200
        assert response.json() == {"dry_run": True, "repositories": []}
        assert calls == [{"app_id": "123", "private_key": "key", "owner": "jclee941", "dry_run": True}]

    def test_defaults_to_background_ack_for_long_maintenance(self, monkeypatch) -> None:
        # Given
        from jclee_bot import app as app_module

        monkeypatch.setenv("ISSUE_MAINTENANCE_TOKEN", "maint")
        monkeypatch.setenv("GITHUB_APP_ID", "123")
        monkeypatch.setenv("GITHUB_PRIVATE_KEY", "key")
        monkeypatch.setattr(app_module, "_run_app_issue_maintenance", lambda **kwargs: {"repositories": []})

        # When
        response = TestClient(app_module.app, raise_server_exceptions=False).post(
            "/api/v1/issue_maintenance",
            json={"dry_run": True},
            headers={"Authorization": "Bearer maint"},
        )

        # Then
        assert response.status_code == 200
        assert response.json() == {"accepted": True, "dry_run": True, "owner": "jclee941"}
