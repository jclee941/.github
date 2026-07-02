from __future__ import annotations

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from jclee_bot import issue_commands


def test_issue_command_upsert_dry_run_does_not_mutate(monkeypatch: MonkeyPatch) -> None:
    mutations: list[str] = []

    def no_existing_issue(**_kwargs: object) -> None:
        return None

    def record_label(**_kwargs: object) -> None:
        mutations.append("label")

    def create_issue(**_kwargs: object) -> int:
        mutations.append("create")
        return 4

    monkeypatch.setattr(issue_commands, "_find_issue", no_existing_issue)
    monkeypatch.setattr(issue_commands, "_ensure_labels", record_label)
    monkeypatch.setattr(issue_commands, "_create_issue", create_issue)

    result = issue_commands.run_issue_commands(
        token="tok",
        payload={
            "repository": "jclee941/jclee-bot",
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
        "actions": ["upsert-create:jclee941/jclee-bot:[bot-health] jclee-bot critical alert"],
    }
    assert mutations == []


def test_issue_command_uses_repository_object_full_name() -> None:
    result = issue_commands.run_issue_commands(
        token="tok",
        payload={
            "repository": {"full_name": "jclee941/jclee-bot"},
            "dry_run": True,
            "commands": [{"type": "create_issue", "title": "x", "body": "y"}],
        },
    )

    assert result == {
        "dry_run": True,
        "actions": ["create:jclee941/jclee-bot:x"],
    }


def test_issue_command_label_skips_malformed_number() -> None:
    for malformed_number in ["not-a-number", True, 1.2, float("inf")]:
        payload = {
            "repository": "jclee941/jclee-bot",
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
        "repository": "jclee941/jclee-bot",
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
        "actions": ["close:jclee941/jclee-bot#7", "close:jclee941/jclee-bot#8"],
    }


def test_issue_command_endpoint_delegates_to_app_module(monkeypatch: MonkeyPatch) -> None:
    from jclee_bot import app as app_module

    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"dry_run": True, "repository": "jclee941/jclee-bot", "actions": ["upsert-create:x"]}

    monkeypatch.setenv("ISSUE_COMMANDS_TOKEN", "issue")
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "key")
    monkeypatch.setattr(app_module, "_run_app_issue_commands", fake_run)

    response = TestClient(app_module.app, raise_server_exceptions=False).post(
        "/api/v1/issue_commands",
        json={
            "repository": "jclee941/jclee-bot",
            "dry_run": True,
            "commands": [{"type": "upsert_issue", "title": "x", "body": "y"}],
        },
        headers={"Authorization": "Bearer issue"},
    )

    assert response.status_code == 200
    assert response.json() == {"dry_run": True, "repository": "jclee941/jclee-bot", "actions": ["upsert-create:x"]}
    assert calls[0]["app_id"] == "123"
    assert calls[0]["private_key"] == "key"


def test_issue_command_endpoint_returns_action_shape_on_execution_failure(monkeypatch: MonkeyPatch) -> None:
    from jclee_bot import app as app_module

    def broken_run(**_kwargs: object) -> dict[str, object]:
        raise RuntimeError("github api failed")

    monkeypatch.setenv("ISSUE_COMMANDS_TOKEN", "issue")
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "key")
    monkeypatch.setattr(app_module, "_run_app_issue_commands", broken_run)

    response = TestClient(app_module.app, raise_server_exceptions=False).post(
        "/api/v1/issue_commands",
        json={
            "repository": "jclee941/jclee-bot",
            "commands": [
                {
                    "type": "close_matching_issues",
                    "title_contains": "[health-check] Downstream workflow failures detected",
                    "labels": ["health-check"],
                }
            ],
        },
        headers={"Authorization": "Bearer issue"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "dry_run": False,
        "repository": "jclee941/jclee-bot",
        "actions": [],
        "error": "issue command execution failed",
        "error_type": "RuntimeError",
    }
