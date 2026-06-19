from __future__ import annotations

from fastapi.testclient import TestClient

from jclee_bot import readme_automation


def test_run_app_readme_automation_filters_managed_repos(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(readme_automation.issue_maintenance, "managed_repo_names", lambda: {"propose"})
    monkeypatch.setattr(readme_automation.issue_maintenance, "app_installations", lambda **kwargs: [{"id": 42}])
    monkeypatch.setattr(readme_automation.github_checks, "installation_token", lambda *args: "tok")
    monkeypatch.setattr(
        readme_automation.issue_maintenance,
        "installation_repositories",
        lambda **kwargs: [
            {"full_name": "jclee941/propose", "name": "propose", "default_branch": "master"},
            {"full_name": "jclee941/skip", "name": "skip", "default_branch": "master"},
            {"full_name": "someone/propose", "name": "propose", "default_branch": "master"},
        ],
    )

    def fake_ensure(**kwargs):
        calls.append(kwargs["repo"]["full_name"])
        return {"repo": kwargs["repo"]["full_name"], "changed": True}

    monkeypatch.setattr(readme_automation, "_ensure_readme_commit", fake_ensure)

    result = readme_automation.run_app_readme_automation(
        app_id="123",
        private_key="key",
        owner="jclee941",
        dry_run=True,
    )

    assert calls == ["jclee941/propose"]
    assert result == {"dry_run": True, "repositories": [{"repo": "jclee941/propose", "changed": True}]}


def test_readme_automation_endpoint_runs_sync_when_requested(monkeypatch):
    from jclee_bot import app as app_module

    calls: list[dict[str, object]] = []

    def fake_run_app_readme_automation(**kwargs) -> dict[str, object]:
        calls.append(kwargs)
        return {"dry_run": True, "repositories": []}

    monkeypatch.setenv("README_AUTOMATION_TOKEN", "readme")
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "key")
    monkeypatch.setattr(readme_automation, "run_app_readme_automation", fake_run_app_readme_automation)

    response = TestClient(app_module.app, raise_server_exceptions=False).post(
        "/api/v1/readme_automation",
        json={"dry_run": True, "background": False, "repos": ["propose"]},
        headers={"Authorization": "Bearer readme"},
    )

    assert response.status_code == 200
    assert response.json() == {"dry_run": True, "repositories": []}
    assert calls == [
        {
            "app_id": "123",
            "private_key": "key",
            "owner": "jclee941",
            "dry_run": True,
            "repo_names": {"propose"},
        }
    ]


def test_readme_automation_endpoint_rejects_missing_token(monkeypatch):
    from jclee_bot import app as app_module

    monkeypatch.delenv("README_AUTOMATION_TOKEN", raising=False)
    monkeypatch.delenv("ISSUE_MAINTENANCE_TOKEN", raising=False)

    response = TestClient(app_module.app, raise_server_exceptions=False).post(
        "/api/v1/readme_automation",
        json={"dry_run": True},
    )

    assert response.status_code == 401
