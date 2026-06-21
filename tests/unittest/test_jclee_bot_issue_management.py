from __future__ import annotations

import hashlib
import hmac
import json
import threading
from typing import Any, TypedDict

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
    state: str = "open",
) -> dict[str, object]:
    return {
        "action": action,
        "installation": {"id": 42},
        "repository": {"full_name": "jclee941/propose"},
        "issue": {
            "number": 7,
            "title": title,
            "body": body,
            "state": state,
            "labels": labels or [],
        },
        "sender": {"login": "octocat", "id": 1},
    }


def _signature(secret: str, payload: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


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


class TestShouldCreateBranch:
    def test_returns_true_when_issue_is_opened(self) -> None:
        # Given
        payload = _issue_payload(action="opened")

        # When
        should_create = issue_management.should_create_branch(payload, "issues")

        # Then
        assert should_create is True

    def test_returns_true_when_issue_gets_in_progress_label(self) -> None:
        # Given
        payload = _issue_payload(action="labeled")
        payload["label"] = {"name": "in-progress"}

        # When
        should_create = issue_management.should_create_branch(payload, "issues")

        # Then
        assert should_create is True

    def test_returns_true_when_issue_is_assigned_to_human(self) -> None:
        # Given
        payload = _issue_payload(action="assigned")
        payload["assignee"] = {"login": "jclee941"}

        # When
        should_create = issue_management.should_create_branch(payload, "issues")

        # Then
        assert should_create is True

    def test_returns_false_when_issue_is_assigned_to_bot(self) -> None:
        # Given
        payload = _issue_payload(action="assigned")
        payload["assignee"] = {"login": "jclee-bot"}

        # When
        should_create = issue_management.should_create_branch(payload, "issues")

        # Then
        assert should_create is False

    def test_returns_false_when_issue_is_closed(self) -> None:
        # Given
        payload = _issue_payload(action="opened", state="closed")

        # When
        should_create = issue_management.should_create_branch(payload, "issues")

        # Then
        assert should_create is False


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
        monkeypatch.setattr(issue_management, "create_issue_branch", lambda **kwargs: None)
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

    def test_creates_branch_from_master_when_issue_is_opened(self, monkeypatch) -> None:
        # Given
        calls: list[dict[str, Any]] = []

        def fake_create_issue_branch(**kwargs: Any) -> str:
            calls.append(kwargs)
            return "fix/issue-7-bug-crash-in-coverage-workflow"

        monkeypatch.setattr(issue_management, "add_labels", lambda **kwargs: None)
        monkeypatch.setattr(issue_management, "create_issue_branch", fake_create_issue_branch)
        payload = _issue_payload(labels=[{"name": "bug"}])

        # When
        result = issue_management.handle_issue_event(
            token="tok",
            payload=payload,
            event="issues",
        )

        # Then
        assert result == {
            "actions": [
                "add-labels:bug,enhancement,tests",
                "create-branch:fix/issue-7-bug-crash-in-coverage-workflow",
            ]
        }
        assert calls == [
            {
                "token": "tok",
                "repo_full_name": "jclee941/propose",
                "issue_number": 7,
                "title": "Bug: crash in coverage workflow",
                "labels": [{"name": "bug"}, "bug", "enhancement", "tests"],
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
            "create_issue_branch",
            lambda **kwargs: calls.append("branch"),
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


class TestCreateIssueBranch:
    def test_creates_issue_branch_from_master_and_comments(self, monkeypatch) -> None:
        # Given
        requests: list[tuple[str, str, dict[str, Any] | None]] = []

        class FakeResponse:
            def __init__(self, status_code: int, payload: dict[str, Any] | None = None) -> None:
                self.status_code = status_code
                self._payload = payload or {}

            def json(self) -> dict[str, Any]:
                return self._payload

            def raise_for_status(self) -> None:
                if self.status_code >= 400:
                    raise AssertionError(f"unexpected HTTP status {self.status_code}")

        def fake_get(url: str, **kwargs: Any) -> FakeResponse:
            requests.append(("GET", url, None))
            if url.endswith("/git/ref/heads/fix/issue-7-bug-crash-in-coverage-workflow"):
                return FakeResponse(404)
            if url.endswith("/git/ref/heads/master"):
                return FakeResponse(200, {"object": {"sha": "abc123"}})
            raise AssertionError(f"unexpected GET {url}")

        def fake_post(url: str, **kwargs: Any) -> FakeResponse:
            requests.append(("POST", url, kwargs.get("json")))
            return FakeResponse(201)

        monkeypatch.setattr(issue_management.requests, "get", fake_get)
        monkeypatch.setattr(issue_management.requests, "post", fake_post)

        # When
        branch = issue_management.create_issue_branch(
            token="tok",
            repo_full_name="jclee941/propose",
            issue_number=7,
            title="Bug: crash in coverage workflow",
            labels=[{"name": "bug"}],
        )

        # Then
        assert branch == "fix/issue-7-bug-crash-in-coverage-workflow"
        assert requests == [
            (
                "GET",
                "https://api.github.com/repos/jclee941/propose/git/ref/heads/fix/issue-7-bug-crash-in-coverage-workflow",
                None,
            ),
            (
                "GET",
                "https://api.github.com/repos/jclee941/propose/git/ref/heads/master",
                None,
            ),
            (
                "POST",
                "https://api.github.com/repos/jclee941/propose/git/refs",
                {
                    "ref": "refs/heads/fix/issue-7-bug-crash-in-coverage-workflow",
                    "sha": "abc123",
                },
            ),
            (
                "POST",
                "https://api.github.com/repos/jclee941/propose/issues/7/comments",
                {
                    "body": "Branch `fix/issue-7-bug-crash-in-coverage-workflow` created. "
                    "Push commits to that branch and a draft PR will open automatically."
                },
            ),
        ]

    def test_skips_branch_creation_when_branch_already_exists(self, monkeypatch) -> None:
        # Given
        posts: list[str] = []

        class FakeResponse:
            status_code = 200

            def raise_for_status(self) -> None:
                raise AssertionError("existing branch should not be treated as an error")

        monkeypatch.setattr(issue_management.requests, "get", lambda *args, **kwargs: FakeResponse())
        monkeypatch.setattr(
            issue_management.requests,
            "post",
            lambda url, **kwargs: posts.append(url),
        )

        # When
        branch = issue_management.create_issue_branch(
            token="tok",
            repo_full_name="jclee941/propose",
            issue_number=7,
            title="Bug: crash in coverage workflow",
            labels=[{"name": "bug"}],
        )

        # Then
        assert branch is None
        assert posts == []


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
        payload = _issue_payload()
        body = json.dumps(payload).encode()

        # When
        response = TestClient(app_module.app, raise_server_exceptions=False).post(
            "/api/v1/github_webhooks",
            content=body,
            headers={
                "X-GitHub-Event": "issues",
                "X-Hub-Signature-256": _signature("secret", body),
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
        payload = _issue_payload(action="created", labels=[{"name": "stale"}])
        body = json.dumps(payload).encode()

        # When
        response = TestClient(app_module.app, raise_server_exceptions=False).post(
            "/api/v1/github_webhooks",
            content=body,
            headers={
                "X-GitHub-Event": "issue_comment",
                "X-Hub-Signature-256": _signature("secret", body),
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
        payload = _issue_payload()

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
        payload = _issue_payload(action="created", labels=[{"name": "stale"}])

        # When
        response = TestClient(app_module.app, raise_server_exceptions=False).post(
            "/api/v1/github_webhooks",
            content=json.dumps(payload),
            headers={"X-GitHub-Event": "issue_comment", "X-Hub-Signature-256": "sha256=bad"},
        )

        # Then
        assert response.status_code != 500
        assert dispatched == []
