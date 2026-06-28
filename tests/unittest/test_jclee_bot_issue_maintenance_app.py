from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from jclee_bot import issue_maintenance


def _repo_health_issue() -> dict[str, str | list[dict[str, str]]]:
    return {"title": "repo health", "state": "open", "labels": [{"name": "repo-health"}]}


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
        maintained: list[tuple[str, bool]] = []
        monkeypatch.setattr(
            issue_maintenance,
            "maintain_repo",
            lambda **kwargs: maintained.append((kwargs["repo_full_name"], kwargs["branch_cleanup"]))
            or {"repo": kwargs["repo_full_name"]},
        )

        # When
        result = issue_maintenance.run_app_maintenance(
            app_id="123",
            private_key="key",
            owner="jclee941",
            dry_run=True,
        )

        # Then
        assert maintained == [("jclee941/propose", False)]
        assert result == {"dry_run": True, "mode": "safe", "repositories": [{"repo": "jclee941/propose"}]}

    def test_owner_scoped_non_managed_repo_runs_when_bot_owned_issue_exists(self, monkeypatch) -> None:
        # Given
        monkeypatch.setattr(issue_maintenance, "managed_repo_names", lambda config_path=None: {"bug"})
        monkeypatch.setattr(issue_maintenance, "app_installations", lambda **kwargs: [{"id": 42}])
        monkeypatch.setattr(issue_maintenance.github_checks, "installation_token", lambda *args: "tok")
        monkeypatch.setattr(
            issue_maintenance,
            "installation_repositories",
            lambda **kwargs: [
                {"full_name": "jclee941/ai-dacon", "name": "ai-dacon"},
                {"full_name": "jclee941/untracked", "name": "untracked"},
            ],
        )

        def open_issues(*, token: str, repo_full_name: str) -> list[dict[str, str | list[dict[str, str]]]]:
            del token
            if repo_full_name == "jclee941/ai-dacon":
                return [_repo_health_issue()]
            return []

        maintained: list[tuple[str, bool]] = []
        monkeypatch.setattr(issue_maintenance, "list_open_issues", open_issues)
        monkeypatch.setattr(
            issue_maintenance,
            "maintain_repo",
            lambda **kwargs: maintained.append((kwargs["repo_full_name"], kwargs["branch_cleanup"]))
            or {"repo": kwargs["repo_full_name"]},
        )

        # When
        result = issue_maintenance.run_app_maintenance(
            app_id="123",
            private_key="key",
            owner="jclee941",
            dry_run=True,
        )

        # Then
        assert maintained == [("jclee941/ai-dacon", False)]
        assert result == {"dry_run": True, "mode": "safe", "repositories": [{"repo": "jclee941/ai-dacon"}]}

    def test_force_mode_requires_managed_repo_inventory(self, monkeypatch) -> None:
        # Given
        monkeypatch.setattr(issue_maintenance, "managed_repo_names", lambda config_path=None: None)
        monkeypatch.setattr(issue_maintenance, "app_installations", lambda **kwargs: [{"id": 42}])

        # When
        result = issue_maintenance.run_app_maintenance(
            app_id="123",
            private_key="key",
            owner="jclee941",
            dry_run=True,
            mode="force",
        )

        # Then
        assert result == {
            "dry_run": True,
            "mode": "force",
            "repositories": [],
            "error": "managed repository inventory is required for force mode",
        }

    def test_force_mode_skips_non_managed_bot_owned_issue_fallback(self, monkeypatch) -> None:
        # Given
        monkeypatch.setattr(issue_maintenance, "managed_repo_names", lambda config_path=None: {"bug"})
        monkeypatch.setattr(issue_maintenance, "app_installations", lambda **kwargs: [{"id": 42}])
        monkeypatch.setattr(issue_maintenance.github_checks, "installation_token", lambda *args: "tok")
        monkeypatch.setattr(
            issue_maintenance,
            "installation_repositories",
            lambda **kwargs: [
                {"full_name": "jclee941/ai-dacon", "name": "ai-dacon"},
                {"full_name": "jclee941/bug", "name": "bug"},
            ],
        )
        maintained: list[tuple[str, bool]] = []
        monkeypatch.setattr(
            issue_maintenance,
            "maintain_repo",
            lambda **kwargs: maintained.append((kwargs["repo_full_name"], kwargs["branch_cleanup"]))
            or {"repo": kwargs["repo_full_name"]},
        )

        # When
        result = issue_maintenance.run_app_maintenance(
            app_id="123",
            private_key="key",
            owner="jclee941",
            dry_run=True,
            mode="force",
        )

        # Then
        assert maintained == [("jclee941/bug", True)]
        assert result == {"dry_run": True, "mode": "force", "repositories": [{"repo": "jclee941/bug"}]}

    def test_force_mode_records_repo_error_and_continues(self, monkeypatch) -> None:
        # Given
        monkeypatch.setattr(issue_maintenance, "managed_repo_names", lambda config_path=None: {"account", "bug"})
        monkeypatch.setattr(issue_maintenance, "app_installations", lambda **kwargs: [{"id": 42}])
        monkeypatch.setattr(issue_maintenance.github_checks, "installation_token", lambda *args: "tok")
        monkeypatch.setattr(
            issue_maintenance,
            "installation_repositories",
            lambda **kwargs: [
                {"full_name": "jclee941/bug", "name": "bug"},
                {"full_name": "jclee941/account", "name": "account"},
            ],
        )

        def maintain_repo(**kwargs):
            if kwargs["repo_full_name"] == "jclee941/bug":
                raise RuntimeError("boom")
            return {"repo": kwargs["repo_full_name"], "actions": []}

        monkeypatch.setattr(issue_maintenance, "maintain_repo", maintain_repo)

        # When
        result = issue_maintenance.run_app_maintenance(
            app_id="123",
            private_key="key",
            owner="jclee941",
            dry_run=False,
            mode="force",
        )

        # Then
        assert result == {
            "dry_run": False,
            "mode": "force",
            "repositories": [
                {"repo": "jclee941/bug", "error": "repo-maintenance-error:RuntimeError"},
                {"repo": "jclee941/account", "actions": []},
            ],
            "errors": [{"repo": "jclee941/bug", "error": "repo-maintenance-error:RuntimeError"}],
            "error": "issue maintenance failed",
        }

    def test_managed_repo_names_returns_none_when_config_file_is_missing(self, tmp_path: Path) -> None:
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

        calls: list[dict[str, str | bool]] = []

        def fake_run_app_maintenance(**kwargs: str | bool) -> dict[str, str | bool | list[dict[str, str]]]:
            calls.append(kwargs)
            return {"dry_run": True, "mode": "safe", "repositories": []}

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
        assert response.json() == {"dry_run": True, "mode": "safe", "repositories": []}
        assert calls == [
            {"app_id": "123", "private_key": "key", "owner": "jclee941", "dry_run": True, "mode": "safe"}
        ]

    def test_runs_force_maintenance_when_requested(self, monkeypatch) -> None:
        # Given
        from jclee_bot import app as app_module

        calls: list[dict[str, str | bool]] = []

        def fake_run_app_maintenance(**kwargs: str | bool) -> dict[str, str | bool | list[dict[str, str]]]:
            calls.append(kwargs)
            return {"dry_run": False, "mode": "force", "repositories": []}

        monkeypatch.setenv("ISSUE_MAINTENANCE_TOKEN", "maint")
        monkeypatch.setenv("GITHUB_APP_ID", "123")
        monkeypatch.setenv("GITHUB_PRIVATE_KEY", "key")
        monkeypatch.setattr(app_module.issue_maintenance, "run_app_maintenance", fake_run_app_maintenance)

        # When
        response = TestClient(app_module.app, raise_server_exceptions=False).post(
            "/api/v1/issue_maintenance",
            json={"dry_run": False, "background": False, "mode": "force"},
            headers={"Authorization": "Bearer maint"},
        )

        # Then
        assert response.status_code == 200
        assert response.json() == {"dry_run": False, "mode": "force", "repositories": []}
        assert calls == [
            {"app_id": "123", "private_key": "key", "owner": "jclee941", "dry_run": False, "mode": "force"}
        ]

    def test_rejects_unknown_maintenance_mode(self, monkeypatch) -> None:
        # Given
        from jclee_bot import app as app_module

        monkeypatch.setenv("ISSUE_MAINTENANCE_TOKEN", "maint")
        monkeypatch.setenv("GITHUB_APP_ID", "123")
        monkeypatch.setenv("GITHUB_PRIVATE_KEY", "key")

        # When
        response = TestClient(app_module.app, raise_server_exceptions=False).post(
            "/api/v1/issue_maintenance",
            json={"dry_run": True, "background": False, "mode": "delete-everything"},
            headers={"Authorization": "Bearer maint"},
        )

        # Then
        assert response.status_code == 400
        assert response.json() == {"error": "mode must be safe or force"}

    def test_rejects_unhashable_maintenance_mode(self, monkeypatch) -> None:
        # Given
        from jclee_bot import app as app_module

        monkeypatch.setenv("ISSUE_MAINTENANCE_TOKEN", "maint")
        monkeypatch.setenv("GITHUB_APP_ID", "123")
        monkeypatch.setenv("GITHUB_PRIVATE_KEY", "key")

        # When
        response = TestClient(app_module.app, raise_server_exceptions=False).post(
            "/api/v1/issue_maintenance",
            json={"dry_run": True, "background": False, "mode": ["force"]},
            headers={"Authorization": "Bearer maint"},
        )

        # Then
        assert response.status_code == 400
        assert response.json() == {"error": "mode must be safe or force"}

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
        assert response.json() == {"accepted": True, "dry_run": True, "mode": "safe", "owner": "jclee941"}


class TestIssueMaintenanceScheduler:
    def test_app_registers_internal_maintenance_scheduler(self) -> None:
        from jclee_bot import app as app_module

        assert app_module._start_issue_maintenance_scheduler in app_module.app.router.on_startup

    def test_scheduled_maintenance_runs_force_without_http(self, monkeypatch, tmp_path: Path) -> None:
        from jclee_bot import app as app_module

        calls: list[dict[str, str | bool]] = []

        def fake_run_app_issue_maintenance(**kwargs: str | bool) -> dict[str, str | list[dict[str, str]]]:
            calls.append(kwargs)
            return {"mode": "force", "repositories": []}

        monkeypatch.setenv("GITHUB_APP_ID", "123")
        monkeypatch.setenv("GITHUB_PRIVATE_KEY", "key")
        monkeypatch.setenv("JCLEE_BOT_ISSUE_MAINTENANCE_LOCK_PATH", str(tmp_path / "maintenance.lock"))
        monkeypatch.setattr(app_module, "_run_app_issue_maintenance", fake_run_app_issue_maintenance)

        result = app_module._run_scheduled_issue_maintenance_once()

        assert result == {"mode": "force", "repositories": []}
        assert calls == [
            {"app_id": "123", "private_key": "key", "owner": "jclee941", "dry_run": False, "mode": "force"}
        ]
