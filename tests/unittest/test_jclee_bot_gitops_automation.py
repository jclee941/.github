from __future__ import annotations

from typing import Any

import pytest

from jclee_bot import gitops_automation


def _create_payload(*, ref: str = "fix/issue-7-broken-ci", sender: str = "jclee941") -> dict[str, Any]:
    return {
        "ref": ref,
        "ref_type": "branch",
        "sender": {"login": sender},
        "repository": {"full_name": "jclee941/propose", "default_branch": "master"},
    }


class TestCreateEventDecision:
    def test_accepts_gitops_branch_from_human_sender(self) -> None:
        # Given
        payload = _create_payload()

        # When
        accepted = gitops_automation.should_open_pull_request(payload, "create")

        # Then
        assert accepted is True

    def test_skips_non_branch_and_bot_sender(self) -> None:
        # Given
        tag_payload = {**_create_payload(), "ref_type": "tag"}
        bot_payload = _create_payload(sender="jclee-bot")

        # Then
        assert gitops_automation.should_open_pull_request(tag_payload, "create") is False
        assert gitops_automation.should_open_pull_request(bot_payload, "create") is False


class TestCreateEventHandler:
    def test_creates_pull_request_labels_and_enables_auto_merge(self, monkeypatch) -> None:
        # Given
        actions: list[str] = []
        monkeypatch.setattr(gitops_automation, "_existing_pull_request", lambda *args: None)
        monkeypatch.setattr(gitops_automation, "_commit_title", lambda *args: "fix: broken ci")
        monkeypatch.setattr(
            gitops_automation,
            "_create_pull_request",
            lambda *args: {"number": 17, "node_id": "PR_kw"},
        )
        monkeypatch.setattr(
            gitops_automation,
            "add_auto_merge_label",
            lambda token, repo_full_name, pr_number: actions.append(f"label:{pr_number}"),
        )
        monkeypatch.setattr(
            gitops_automation,
            "enable_auto_merge",
            lambda token, pull_request_id: actions.append(f"merge:{pull_request_id}"),
        )

        # When
        result = gitops_automation.handle_create_event(
            token="tok",
            payload=_create_payload(),
            event="create",
        )

        # Then
        assert result == {"actions": ["create-pr:17", "add-label:auto-merge", "enable-auto-merge"]}
        assert actions == ["label:17", "merge:PR_kw"]

    def test_skips_existing_pull_request(self, monkeypatch) -> None:
        # Given
        monkeypatch.setattr(gitops_automation, "_existing_pull_request", lambda *args: 9)

        # When
        result = gitops_automation.handle_create_event(
            token="tok",
            payload=_create_payload(),
            event="create",
        )

        # Then
        assert result == {"actions": ["skip-existing-pr"]}


class TestPullRequestAutoMergeHandler:
    def test_enables_auto_merge_when_auto_merge_label_is_added(self, monkeypatch) -> None:
        # Given
        calls: list[str] = []
        monkeypatch.setattr(
            gitops_automation,
            "enable_auto_merge",
            lambda token, pull_request_id: calls.append(pull_request_id),
        )
        payload = {
            "action": "labeled",
            "label": {"name": "auto-merge"},
            "pull_request": {"number": 3, "node_id": "PR_3", "draft": False},
        }

        # When
        result = gitops_automation.handle_pull_request_auto_merge(token="tok", payload=payload, event="pull_request")

        # Then
        assert result == {"actions": ["enable-auto-merge:3"]}
        assert calls == ["PR_3"]

    def test_enables_auto_merge_when_auto_merge_label_is_already_present(self, monkeypatch) -> None:
        # Given
        calls: list[str] = []
        monkeypatch.setattr(
            gitops_automation,
            "enable_auto_merge",
            lambda token, pull_request_id: calls.append(pull_request_id),
        )
        payload = {
            "action": "ready_for_review",
            "pull_request": {
                "number": 5,
                "node_id": "PR_5",
                "draft": False,
                "labels": [{"name": "auto-merge"}],
            },
        }

        # When
        result = gitops_automation.handle_pull_request_auto_merge(token="tok", payload=payload, event="pull_request")

        # Then
        assert result == {"actions": ["enable-auto-merge:5"]}
        assert calls == ["PR_5"]

    def test_enables_auto_merge_on_human_approval(self, monkeypatch) -> None:
        # Given
        calls: list[str] = []
        monkeypatch.setattr(
            gitops_automation,
            "enable_auto_merge",
            lambda token, pull_request_id: calls.append(pull_request_id),
        )
        payload = {
            "review": {"state": "approved"},
            "pull_request": {
                "number": 4,
                "node_id": "PR_4",
                "draft": False,
                "user": {"login": "jclee941"},
            },
        }

        # When
        result = gitops_automation.handle_pull_request_auto_merge(
            token="tok",
            payload=payload,
            event="pull_request_review",
        )

        # Then
        assert result == {"actions": ["enable-auto-merge:4"]}
        assert calls == ["PR_4"]


class TestEnableAutoMerge:
    def test_raises_when_graphql_returns_errors(self, monkeypatch) -> None:
        # Given
        class Response:
            status_code = 200

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, list[dict[str, str]]]:
                return {"errors": [{"message": "Pull request auto-merge is not allowed"}]}

        monkeypatch.setattr(gitops_automation.requests, "post", lambda *args, **kwargs: Response())

        # When / Then
        with pytest.raises(RuntimeError, match="Pull request auto-merge is not allowed"):
            gitops_automation.enable_auto_merge("tok", "PR_bad")
