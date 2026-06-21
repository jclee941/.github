from __future__ import annotations

from jclee_bot import issue_management
from tests.unittest.issue_management_helpers import issue_payload


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
        payload = issue_payload(action="created", labels=[{"name": "stale"}])

        # When
        should_remove = issue_management.should_remove_stale(payload, "issue_comment")

        # Then
        assert should_remove is True

    def test_returns_true_when_stale_issue_is_edited(self) -> None:
        # Given
        payload = issue_payload(action="edited", labels=[{"name": "stale"}])

        # When
        should_remove = issue_management.should_remove_stale(payload, "issues")

        # Then
        assert should_remove is True

    def test_returns_false_when_event_does_not_reactivate_stale_issue(self) -> None:
        # Given
        payload = issue_payload(action="opened", labels=[{"name": "stale"}])

        # When
        should_remove = issue_management.should_remove_stale(payload, "issues")

        # Then
        assert should_remove is False


class TestShouldCreateBranch:
    def test_returns_true_when_issue_is_opened(self) -> None:
        # Given
        payload = issue_payload(action="opened")

        # When
        should_create = issue_management.should_create_branch(payload, "issues")

        # Then
        assert should_create is True

    def test_returns_true_when_issue_gets_in_progress_label(self) -> None:
        # Given
        payload = issue_payload(action="labeled")
        payload["label"] = {"name": "in-progress"}

        # When
        should_create = issue_management.should_create_branch(payload, "issues")

        # Then
        assert should_create is True

    def test_returns_true_when_issue_is_assigned_to_human(self) -> None:
        # Given
        payload = issue_payload(action="assigned")
        payload["assignee"] = {"login": "jclee941"}

        # When
        should_create = issue_management.should_create_branch(payload, "issues")

        # Then
        assert should_create is True

    def test_returns_false_when_issue_is_assigned_to_bot(self) -> None:
        # Given
        payload = issue_payload(action="assigned")
        payload["assignee"] = {"login": "jclee-bot"}

        # When
        should_create = issue_management.should_create_branch(payload, "issues")

        # Then
        assert should_create is False

    def test_returns_false_when_issue_is_closed(self) -> None:
        # Given
        payload = issue_payload(action="opened", state="closed")

        # When
        should_create = issue_management.should_create_branch(payload, "issues")

        # Then
        assert should_create is False
