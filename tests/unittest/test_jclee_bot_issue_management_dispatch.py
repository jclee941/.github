from __future__ import annotations

import json
import threading

from fastapi.testclient import TestClient

from tests.unittest.issue_management_helpers import issue_payload, signature


class TestIssueMiddlewareDispatch:
    def test_issues_event_dispatches_issue_management_in_background(self, monkeypatch) -> None:
        # Given
        from jclee_bot import app as app_module

        dispatched: list[tuple[str, dict[str, object]]] = []
        done = threading.Event()

        def fake_run_issue_management(payload: dict[str, object], event: str) -> dict[str, list[str]]:
            dispatched.append((event, payload))
            done.set()
            return {"actions": ["add-labels:bug"]}

        monkeypatch.setattr(app_module, "_run_issue_management_for_payload", fake_run_issue_management)
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
        payload = issue_payload()
        body = json.dumps(payload).encode()

        # When
        response = TestClient(app_module.app, raise_server_exceptions=False).post(
            "/api/v1/github_webhooks",
            content=body,
            headers={
                "X-GitHub-Event": "issues",
                "X-Hub-Signature-256": signature("secret", body),
            },
        )

        # Then
        assert response.status_code != 500
        assert done.wait(2.0), "issues webhook did not dispatch issue management"
        assert dispatched == [("issues", payload)]

    def test_issue_comment_event_dispatches_issue_management_in_background(self, monkeypatch) -> None:
        # Given
        from jclee_bot import app as app_module

        dispatched: list[tuple[str, dict[str, object]]] = []
        done = threading.Event()

        def fake_run_issue_management(payload: dict[str, object], event: str) -> dict[str, list[str]]:
            dispatched.append((event, payload))
            done.set()
            return {"actions": ["remove-label:stale"]}

        monkeypatch.setattr(app_module, "_run_issue_management_for_payload", fake_run_issue_management)
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
        payload = issue_payload(action="created", labels=[{"name": "stale"}])
        body = json.dumps(payload).encode()

        # When
        response = TestClient(app_module.app, raise_server_exceptions=False).post(
            "/api/v1/github_webhooks",
            content=body,
            headers={
                "X-GitHub-Event": "issue_comment",
                "X-Hub-Signature-256": signature("secret", body),
            },
        )

        # Then
        assert response.status_code != 500
        assert done.wait(2.0), "issue_comment webhook did not dispatch issue management"
        assert dispatched == [("issue_comment", payload)]

    def test_issues_event_without_secret_does_not_dispatch_issue_management(self, monkeypatch) -> None:
        # Given
        from jclee_bot import app as app_module

        dispatched: list[tuple[str, dict[str, object]]] = []

        def fake_run_issue_management(payload: dict[str, object], event: str) -> dict[str, list[str]]:
            dispatched.append((event, payload))
            return {"actions": ["add-labels:bug"]}

        monkeypatch.setattr(app_module, "_run_issue_management_for_payload", fake_run_issue_management)
        monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
        payload = issue_payload()

        # When
        response = TestClient(app_module.app, raise_server_exceptions=False).post(
            "/api/v1/github_webhooks",
            content=json.dumps(payload),
            headers={"X-GitHub-Event": "issues"},
        )

        # Then
        assert response.status_code != 500
        assert dispatched == []

    def test_issue_comment_event_with_bad_signature_does_not_dispatch_issue_management(self, monkeypatch) -> None:
        # Given
        from jclee_bot import app as app_module

        dispatched: list[tuple[str, dict[str, object]]] = []

        def fake_run_issue_management(payload: dict[str, object], event: str) -> dict[str, list[str]]:
            dispatched.append((event, payload))
            return {"actions": ["remove-label:stale"]}

        monkeypatch.setattr(app_module, "_run_issue_management_for_payload", fake_run_issue_management)
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
        payload = issue_payload(action="created", labels=[{"name": "stale"}])

        # When
        response = TestClient(app_module.app, raise_server_exceptions=False).post(
            "/api/v1/github_webhooks",
            content=json.dumps(payload),
            headers={"X-GitHub-Event": "issue_comment", "X-Hub-Signature-256": "sha256=bad"},
        )

        # Then
        assert response.status_code != 500
        assert dispatched == []
