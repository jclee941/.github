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


def test_issue_command_uses_repository_object_full_name() -> None:
    result = issue_commands.run_issue_commands(
        token="tok",
        payload={
            "repository": {"full_name": "jclee941/.github"},
            "dry_run": True,
            "commands": [{"type": "create_issue", "title": "x", "body": "y"}],
        },
    )

    assert result == {
        "dry_run": True,
        "actions": ["create:jclee941/.github:x"],
    }


def test_issue_command_label_skips_malformed_number() -> None:
    for malformed_number in ["not-a-number", True, 1.2, float("inf")]:
        payload = {
            "repository": "jclee941/.github",
            "dry_run": True,
            "commands": [{"type": "label_issue", "number": malformed_number, "labels": ["triage"]}],
        }

        result = issue_commands.run_issue_commands(token="tok", payload=payload)

        assert result == {
            "dry_run": True,
            "actions": ["skip-label:missing-repo-or-number"],
        }


def test_issue_command_close_issues_ignores_malformed_numbers() -> None:
    payload = {
        "repository": "jclee941/.github",
        "dry_run": True,
        "commands": [
            {
                "type": "close_issues",
                "numbers": ["7", "not-a-number", None, 0, -1, True, 1.2, float("inf"), 8],
            }
        ],
    }

    result = issue_commands.run_issue_commands(token="tok", payload=payload)

    assert result == {
        "dry_run": True,
        "actions": ["close:jclee941/.github#7", "close:jclee941/.github#8"],
    }


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
