from __future__ import annotations

from fastapi.testclient import TestClient

from jclee_bot import issue_commands


def test_issue_command_upsert_dry_run_does_not_mutate(monkeypatch) -> None:
    mutations: list[str] = []

    monkeypatch.setattr(issue_commands, "_find_issue", lambda **kwargs: None)
    monkeypatch.setattr(issue_commands, "_ensure_labels", lambda **kwargs: mutations.append("label"))
    monkeypatch.setattr(issue_commands, "_create_issue", lambda **kwargs: mutations.append("create") or 4)

    result = issue_commands.run_issue_commands(
        token="tok",
        payload={
            "repository": "jclee941/.github",
            "dry_run": True,
            "commands": [
                {
                    "type": "upsert_issue",
                    "title": "[bot-health] jclee-bot critical alert",
                    "body": "body",
                    "labels": ["bot-health", "critical", "automation"],
                }
            ],
        },
    )

    assert result == {
        "dry_run": True,
        "actions": ["upsert-create:jclee941/.github:[bot-health] jclee-bot critical alert"],
    }
    assert mutations == []


def test_issue_command_endpoint_delegates_to_app_module(monkeypatch) -> None:
    from jclee_bot import app as app_module

    calls: list[dict[str, object]] = []

    def fake_run(**kwargs) -> dict[str, object]:
        calls.append(kwargs)
        return {"dry_run": True, "repository": "jclee941/.github", "actions": ["upsert-create:x"]}

    monkeypatch.setenv("ISSUE_COMMANDS_TOKEN", "issue")
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "key")
    monkeypatch.setattr(app_module, "_run_app_issue_commands", fake_run)

    response = TestClient(app_module.app, raise_server_exceptions=False).post(
        "/api/v1/issue_commands",
        json={
            "repository": "jclee941/.github",
            "dry_run": True,
            "commands": [{"type": "upsert_issue", "title": "x", "body": "y"}],
        },
        headers={"Authorization": "Bearer issue"},
    )

    assert response.status_code == 200
    assert response.json() == {"dry_run": True, "repository": "jclee941/.github", "actions": ["upsert-create:x"]}
    assert calls[0]["app_id"] == "123"
    assert calls[0]["private_key"] == "key"
