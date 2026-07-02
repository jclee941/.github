from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient

from jclee_bot import native_health, native_health_checks


@dataclass(frozen=True)
class FakeResponse:
    text: str = ""
    body: dict[str, Any] | None = None

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.body or {}


def test_elk_health_accepts_legacy_indices_during_rename(monkeypatch) -> None:
    calls: list[str] = []

    def fake_elk_request(payload, method: str, path: str, **kwargs) -> FakeResponse:
        calls.append(path)
        if path == "/_cluster/health":
            return FakeResponse(body={"status": "green"})
        if "jclee-bot-logs-*" in path:
            return FakeResponse(text="")
        if "github-bot-logs-*" in path:
            return FakeResponse(text="github-bot-logs-2026.06.29\n")
        raise AssertionError(path)

    monkeypatch.setattr(native_health_checks, "_elk_request", fake_elk_request)
    monkeypatch.setattr(
        native_health.issue_commands,
        "run_issue_commands",
        lambda **kwargs: {"actions": [command["type"] for command in kwargs["payload"]["commands"]]},
    )

    result = native_health.run_native_health(
        token="tok",
        payload={"repository": "jclee941/jclee-bot", "dry_run": True, "checks": ["elk_health"]},
    )

    assert result["checks"] == [
        {
            "name": "elk_health",
            "status": "healthy",
            "summary": "ELK is reachable and bot log indices are present",
        }
    ]
    assert result["actions"] == ["close_matching_issues"]
    assert any("github-bot-logs-*" in path for path in calls)


def test_runtime_failure_upserts_issue_from_native_bot(monkeypatch) -> None:
    captured: list[dict[str, Any]] = []

    def fake_http_status(url: str, **kwargs) -> int:
        return 503 if "github_webhooks" in url else 401

    def fake_issue_commands(**kwargs) -> dict[str, Any]:
        captured.extend(kwargs["payload"]["commands"])
        return {"actions": ["upsert-create:jclee941/jclee-bot#4"]}

    monkeypatch.setattr(native_health_checks, "_http_status", fake_http_status)
    monkeypatch.setattr(native_health.issue_commands, "run_issue_commands", fake_issue_commands)

    result = native_health.run_native_health(
        token="tok",
        payload={"repository": "jclee941/jclee-bot", "dry_run": False, "checks": ["runtime_health"]},
    )

    assert result["checks"][0]["status"] == "critical"
    assert captured[0]["type"] == "upsert_issue"
    assert captured[0]["title"] == "Bot webhook endpoint unreachable"
    assert "jclee-bot에의해자동화됨" in captured[0]["body"]


def test_runtime_health_defaults_to_internal_bot_and_cliproxy_urls(monkeypatch) -> None:
    calls: list[tuple[str, bool]] = []

    def fake_http_status(url: str, **kwargs) -> int:
        calls.append((url, bool(kwargs.get("head", False))))
        return 405 if "github_webhooks" in url else 401

    monkeypatch.setattr(native_health_checks, "_http_status", fake_http_status)

    result = native_health_checks.check_runtime_health({"OPENAI_BASE_URL": "http://cliproxyapi:8317/v1"})

    assert result.status == "healthy"
    assert calls == [
        ("http://127.0.0.1:3000/api/v1/github_webhooks", True),
        ("http://cliproxyapi:8317/v1/models", False),
    ]


def test_bot_health_request_exception_returns_critical(monkeypatch) -> None:
    def broken_http_status(url: str, **kwargs) -> int:
        raise TimeoutError("cliproxy timeout")

    monkeypatch.setattr(native_health_checks, "_http_status", broken_http_status)

    result = native_health_checks.check_bot_health(
        "tok",
        {"repository": "jclee941/jclee-bot", "CLIPROXY_API_KEY": "key"},
    )

    assert result.status == "critical"
    assert result.summary == "CLIProxyAPI authenticated health did not respond"
    assert result.details["error"].startswith("TimeoutError:")


def test_native_health_returns_json_when_issue_actions_fail(monkeypatch) -> None:
    def fake_http_status(url: str, **kwargs) -> int:
        return 503 if "github_webhooks" in url else 401

    def broken_issue_commands(**kwargs) -> dict[str, Any]:
        raise RuntimeError("label write failed")

    monkeypatch.setattr(native_health_checks, "_http_status", fake_http_status)
    monkeypatch.setattr(native_health.issue_commands, "run_issue_commands", broken_issue_commands)

    result = native_health.run_native_health(
        token="tok",
        payload={"repository": "jclee941/jclee-bot", "checks": ["runtime_health"]},
    )

    assert result["checks"][0]["status"] == "critical"
    assert result["actions"] == ["issue-actions-error:RuntimeError"]
    assert result["issue_error"] == "label write failed"


def test_native_health_endpoint_delegates_to_app_module(monkeypatch) -> None:
    from jclee_bot import app as app_module

    calls: list[dict[str, object]] = []

    def fake_run(**kwargs) -> dict[str, object]:
        calls.append(kwargs)
        return {"dry_run": True, "repository": "jclee941/jclee-bot", "checks": [], "actions": []}

    monkeypatch.setenv("NATIVE_HEALTH_TOKEN", "native")
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "key")
    monkeypatch.setattr(app_module, "_run_app_native_health", fake_run)

    response = TestClient(app_module.app, raise_server_exceptions=False).post(
        "/api/v1/native_health",
        json={"repository": "jclee941/jclee-bot", "dry_run": True, "checks": ["elk_health"]},
        headers={"Authorization": "Bearer native"},
    )

    assert response.status_code == 200
    assert response.json()["repository"] == "jclee941/jclee-bot"
    assert calls[0]["app_id"] == "123"
    assert calls[0]["private_key"] == "key"


def test_native_health_endpoint_returns_critical_shape_on_execution_failure(monkeypatch) -> None:
    from jclee_bot import app as app_module

    def broken_run(**_kwargs: object) -> dict[str, object]:
        raise RuntimeError("github api failed")

    monkeypatch.setenv("NATIVE_HEALTH_TOKEN", "native")
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "key")
    monkeypatch.setattr(app_module, "_run_app_native_health", broken_run)

    response = TestClient(app_module.app, raise_server_exceptions=False).post(
        "/api/v1/native_health",
        json={"repository": "jclee941/jclee-bot", "checks": ["runtime_health"]},
        headers={"Authorization": "Bearer native"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "dry_run": False,
        "repository": "jclee941/jclee-bot",
        "checks": [{"name": "runtime_health", "status": "critical", "summary": "Native health execution failed"}],
        "actions": [],
        "error": "native health execution failed",
        "error_type": "RuntimeError",
    }
