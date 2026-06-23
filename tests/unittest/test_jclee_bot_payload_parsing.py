from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from jclee_bot import app as app_module


@pytest.mark.parametrize(
    ("path", "token_env", "authorization"),
    [
        ("/api/v1/checks_webhook", "GITHUB_WEBHOOK_SECRET", None),
        ("/api/v1/issue_maintenance", "ISSUE_MAINTENANCE_TOKEN", "Bearer tok"),
        ("/api/v1/ci_failure_issues", "CI_FAILURE_ISSUES_TOKEN", "Bearer tok"),
        ("/api/v1/issue_commands", "ISSUE_COMMANDS_TOKEN", "Bearer tok"),
        ("/api/v1/readme_automation", "README_AUTOMATION_TOKEN", "Bearer tok"),
    ],
)
def test_authenticated_json_endpoints_reject_malformed_json(
    monkeypatch,
    path: str,
    token_env: str,
    authorization: str | None,
) -> None:
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "key")
    monkeypatch.setenv(token_env, "" if token_env == "GITHUB_WEBHOOK_SECRET" else "tok")
    headers = {"Authorization": authorization} if authorization is not None else {}

    response = TestClient(app_module.app, raise_server_exceptions=False).post(
        path,
        content=b"{bad-json",
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json() == {"error": "invalid json"}
