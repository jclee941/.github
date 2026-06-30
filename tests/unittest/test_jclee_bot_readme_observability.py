from __future__ import annotations

import pytest
from _pytest.monkeypatch import MonkeyPatch

from jclee_bot import readme_runner


def test_run_app_readme_automation_reports_progress(monkeypatch: MonkeyPatch) -> None:
    progress: list[dict[str, bool | str]] = []

    monkeypatch.setattr(readme_runner.issue_maintenance, "managed_repo_names", lambda: {"propose", "bug"})
    monkeypatch.setattr(readme_runner.issue_maintenance, "app_installations", lambda **kwargs: [{"id": 42}])
    monkeypatch.setattr(readme_runner.github_checks, "installation_token", lambda *args: "tok")
    monkeypatch.setattr(
        readme_runner.issue_maintenance,
        "installation_repositories",
        lambda **kwargs: [
            {"full_name": "jclee941/propose", "name": "propose", "default_branch": "master"},
            {"full_name": "jclee941/bug", "name": "bug", "default_branch": "master"},
        ],
    )
    monkeypatch.setattr(
        readme_runner,
        "ensure_readme_commit",
        lambda **kwargs: {"repo": kwargs["repo"]["full_name"], "changed": True},
    )

    result = readme_runner.run_app_readme_automation(
        app_id="123",
        private_key="key",
        owner="jclee941",
        dry_run=True,
        progress=progress.append,
    )

    assert progress == result["repositories"]
    assert [item["repo"] for item in progress] == ["jclee941/propose", "jclee941/bug"]


def test_run_app_readme_automation_includes_observable_summary(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(readme_runner.issue_maintenance, "managed_repo_names", lambda: {"propose", "bug", "tmux", "hycu"})
    monkeypatch.setattr(readme_runner.issue_maintenance, "app_installations", lambda **kwargs: [{"id": 42}])
    monkeypatch.setattr(readme_runner.github_checks, "installation_token", lambda *args: "tok")
    monkeypatch.setattr(
        readme_runner.issue_maintenance,
        "installation_repositories",
        lambda **kwargs: [
            {"full_name": "jclee941/propose", "name": "propose", "default_branch": "master"},
            {"full_name": "jclee941/bug", "name": "bug", "default_branch": "master"},
            {"full_name": "jclee941/tmux", "name": "tmux", "default_branch": "master"},
            {"full_name": "jclee941/hycu", "name": "hycu", "default_branch": "master"},
        ],
    )

    def fake_ensure(*, token: str, repo: dict[str, str], dry_run: bool) -> dict[str, bool | int | str]:
        repo_name = repo["full_name"]
        match repo_name:
            case "jclee941/propose":
                return {"repo": repo_name, "changed": True, "dry_run": dry_run}
            case "jclee941/bug":
                return {"repo": repo_name, "changed": True, "pr": 7}
            case "jclee941/tmux":
                return {"repo": repo_name, "changed": False}
            case "jclee941/hycu":
                return {"repo": repo_name, "changed": False, "error": "render failed"}
            case unreachable:
                pytest.fail(f"unexpected repo: {unreachable}")

    monkeypatch.setattr(readme_runner, "ensure_readme_commit", fake_ensure)

    result = readme_runner.run_app_readme_automation(
        app_id="123",
        private_key="key",
        owner="jclee941",
        dry_run=True,
    )

    assert result["summary"] == {
        "repository_count": 4,
        "changed_count": 2,
        "unchanged_count": 1,
        "dry_run_changed_count": 1,
        "pr_count": 1,
        "error_count": 1,
    }
