from __future__ import annotations

import json
import threading
from typing import TypedDict

from fastapi.testclient import TestClient

from jclee_bot import issue_management


class LabelCall(TypedDict):
    token: str
    repo_full_name: str
    issue_number: int
    labels: list[str]


class RemoveCall(TypedDict):
    token: str
    repo_full_name: str
    issue_number: int
    label: str


def _issue_payload(
    *,
    action: str = "opened",
    title: str = "Bug: crash in coverage workflow",
    body: str | None = "Please add tests for this error.",
    labels: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "action": action,
        "installation": {"id": 42},
        "repository": {"full_name": "jclee941/propose"},
        "issue": {
            "number": 7,
            "title": title,
            "body": body,
            "labels": labels or [],
        },
        "sender": {"login": "octocat", "id": 1},
    }


class TestLabelsForIssue:
    def test_returns_matching_labels_when_title_and_body_contain_keywords(self) -> None:
        # Given
        title = "Bug: crash while adding docs"
        body = "CVE coverage is slow after dependency upgrade."

        # When
        labels = issue_management.labels_for_issue(title=title, body=body)

        # Then
        assert labels == [
            "bug",
            "enhancement",
            "documentation",
            "security",
            "tests",
            "performance",
            "dependencies",
        ]

    def test_returns_empty_list_when_issue_has_no_keyword_matches(self) -> None:
        # Given
        title = "Question about repository direction"

        # When
        labels = issue_management.labels_for_issue(title=title, body=None)

        # Then
        assert labels == []


class TestShouldRemoveStale:
    def test_returns_true_when_new_issue_comment_is_on_stale_issue(self) -> None:
        # Given
        payload = _issue_payload(action="created", labels=[{"name": "stale"}])

        # When
        should_remove = issue_management.should_remove_stale(payload, "issue_comment")

        # Then
        assert should_remove is True

    def test_returns_true_when_stale_issue_is_edited(self) -> None:
        # Given
        payload = _issue_payload(action="edited", labels=[{"name": "stale"}])

        # When
        should_remove = issue_management.should_remove_stale(payload, "issues")

        # Then
        assert should_remove is True

    def test_returns_false_when_event_does_not_reactivate_stale_issue(self) -> None:
        # Given
        payload = _issue_payload(action="opened", labels=[{"name": "stale"}])

        # When
        should_remove = issue_management.should_remove_stale(payload, "issues")

        # Then
        assert should_remove is False


class TestHandleIssueEvent:
    def test_adds_labels_when_issue_is_opened(self, monkeypatch) -> None:
        # Given
        calls: list[LabelCall] = []

        def fake_add_labels(
            *,
            token: str,
            repo_full_name: str,
            issue_number: int,
            labels: list[str],
        ) -> None:
            calls.append(
                {
                    "token": token,
                    "repo_full_name": repo_full_name,
                    "issue_number": issue_number,
                    "labels": labels,
                }
            )

        monkeypatch.setattr(issue_management, "add_labels", fake_add_labels)
        payload = _issue_payload()

        # When
        result = issue_management.handle_issue_event(
            token="tok",
            payload=payload,
            event="issues",
        )

        # Then
        assert result == {"actions": ["add-labels:bug,enhancement,tests"]}
        assert calls == [
            {
                "token": "tok",
                "repo_full_name": "jclee941/propose",
                "issue_number": 7,
                "labels": ["bug", "enhancement", "tests"],
            }
        ]

    def test_removes_stale_when_issue_comment_reactivates_issue(self, monkeypatch) -> None:
        # Given
        calls: list[RemoveCall] = []

        def fake_remove_label(
            *,
            token: str,
            repo_full_name: str,
            issue_number: int,
            label: str,
        ) -> None:
            calls.append(
                {
                    "token": token,
                    "repo_full_name": repo_full_name,
                    "issue_number": issue_number,
                    "label": label,
                }
            )

        monkeypatch.setattr(issue_management, "remove_label", fake_remove_label)
        payload = _issue_payload(action="created", labels=[{"name": "stale"}])

        # When
        result = issue_management.handle_issue_event(
            token="tok",
            payload=payload,
            event="issue_comment",
        )

        # Then
        assert result == {"actions": ["remove-label:stale"]}
        assert calls == [
            {
                "token": "tok",
                "repo_full_name": "jclee941/propose",
                "issue_number": 7,
                "label": "stale",
            }
        ]

    def test_skips_pull_request_payloads_without_network_actions(self, monkeypatch) -> None:
        # Given
        calls: list[str] = []
        monkeypatch.setattr(
            issue_management,
            "add_labels",
            lambda **kwargs: calls.append("add"),
        )
        monkeypatch.setattr(
            issue_management,
            "remove_label",
            lambda **kwargs: calls.append("remove"),
        )
        payload = _issue_payload()
        issue = payload["issue"]
        assert isinstance(issue, dict)
        issue["pull_request"] = {"url": "https://api.github.com/repos/jclee941/propose/pulls/7"}

        # When
        result = issue_management.handle_issue_event(
            token="tok",
            payload=payload,
            event="issues",
        )

        # Then
        assert result == {"actions": []}
        assert calls == []


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
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "")
        payload = _issue_payload()

        # When
        response = TestClient(app_module.app, raise_server_exceptions=False).post(
            "/api/v1/github_webhooks",
            content=json.dumps(payload),
            headers={"X-GitHub-Event": "issues"},
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
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "")
        payload = _issue_payload(action="created", labels=[{"name": "stale"}])

        # When
        response = TestClient(app_module.app, raise_server_exceptions=False).post(
            "/api/v1/github_webhooks",
            content=json.dumps(payload),
            headers={"X-GitHub-Event": "issue_comment"},
        )

        # Then
        assert response.status_code != 500
        assert done.wait(2.0), "issue_comment webhook did not dispatch issue management"
        assert dispatched == [("issue_comment", payload)]
