from __future__ import annotations

from typing import Any

from jclee_bot import issue_management
from tests.unittest.issue_management_helpers import LabelCall, RemoveCall, issue_payload


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
        payload = issue_payload()

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
        payload = issue_payload(labels=[{"name": "bug"}])

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
        payload = issue_payload(action="created", labels=[{"name": "stale"}])

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
        payload = issue_payload()
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
