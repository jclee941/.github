from unittest.mock import MagicMock

import pytest

from jclee_bot.review_engine.git_providers.github_provider import GithubProvider


class TestGithubProviderIssueCreation:
    """Test suite for GitHub provider issue creation helpers."""

    @pytest.fixture
    def provider(self):
        provider = object.__new__(GithubProvider)
        provider.repo = "jclee941/test-repo"
        provider.base_url = "https://api.github.com"
        return provider

    @pytest.fixture
    def mock_repo(self):
        return MagicMock()

    def test_create_issue_delegates_to_repo_create_issue(self, provider, mock_repo):
        provider._get_repo = MagicMock(return_value=mock_repo)
        issue = MagicMock()
        mock_repo.create_issue.return_value = issue

        result = provider.create_issue("Title", "Body", ["label"])

        mock_repo.create_issue.assert_called_once_with(title="Title", body="Body", labels=["label"])
        assert result == issue

    def test_create_issue_defaults_labels_to_empty_list(self, provider, mock_repo):
        provider._get_repo = MagicMock(return_value=mock_repo)
        issue = MagicMock()
        mock_repo.create_issue.return_value = issue

        result = provider.create_issue("Title", "Body", None)

        mock_repo.create_issue.assert_called_once_with(title="Title", body="Body", labels=[])
        assert result == issue

    def test_create_issue_soft_fails_and_returns_none(self, provider, mock_repo):
        provider._get_repo = MagicMock(return_value=mock_repo)
        mock_repo.create_issue.side_effect = Exception("api error")

        result = provider.create_issue("Title", "Body", ["label"])

        assert result is None

    def test_find_open_issue_by_marker_returns_matching_issue(self, provider, mock_repo):
        provider._get_repo = MagicMock(return_value=mock_repo)
        issue_without = MagicMock()
        issue_without.pull_request = None
        issue_without.body = "Some other body"
        issue_with = MagicMock()
        issue_with.pull_request = None
        issue_with.body = "Body with <!-- marker-123 --> marker"
        mock_repo.get_issues.return_value = [issue_without, issue_with]

        result = provider.find_open_issue_by_marker("marker-123", labels=["review-finding"])

        mock_repo.get_issues.assert_called_once_with(state="open", labels=["review-finding"])
        assert result == issue_with

    def test_find_open_issue_by_marker_ignores_pull_requests(self, provider, mock_repo):
        provider._get_repo = MagicMock(return_value=mock_repo)
        issue = MagicMock()
        issue.pull_request = {"url": "https://api.github.com/repos/jclee941/test-repo/pulls/1"}
        issue.body = "Body with <!-- marker-123 --> marker"
        mock_repo.get_issues.return_value = [issue]

        result = provider.find_open_issue_by_marker("marker-123", labels=["review-finding"])

        assert result is None

    def test_find_open_issue_by_marker_handles_empty_body(self, provider, mock_repo):
        provider._get_repo = MagicMock(return_value=mock_repo)
        issue = MagicMock()
        issue.pull_request = None
        issue.body = None
        mock_repo.get_issues.return_value = [issue]

        result = provider.find_open_issue_by_marker("marker-123", labels=["review-finding"])

        assert result is None

    def test_find_open_issue_by_marker_returns_none_when_absent(self, provider, mock_repo):
        provider._get_repo = MagicMock(return_value=mock_repo)
        issue = MagicMock()
        issue.pull_request = None
        issue.body = "Body without marker"
        mock_repo.get_issues.return_value = [issue]

        result = provider.find_open_issue_by_marker("marker-123", labels=["review-finding"])

        assert result is None

    def test_find_open_issue_by_marker_soft_fails_and_returns_none(self, provider, mock_repo):
        provider._get_repo = MagicMock(return_value=mock_repo)
        mock_repo.get_issues.side_effect = Exception("api error")

        result = provider.find_open_issue_by_marker("marker-123", labels=["review-finding"])

        assert result is None

    def test_ensure_labels_creates_missing_labels(self, provider, mock_repo):
        provider._get_repo = MagicMock(return_value=mock_repo)
        existing_label = MagicMock()
        existing_label.name = "jclee-bot"
        mock_repo.get_labels.return_value = [existing_label]

        provider.ensure_labels(["jclee-bot", "review-finding", "critical"])

        mock_repo.create_label.assert_any_call(name="review-finding", color="ededed")
        mock_repo.create_label.assert_any_call(name="critical", color="ededed")
        assert mock_repo.create_label.call_count == 2

    def test_ensure_labels_noops_when_all_exist(self, provider, mock_repo):
        provider._get_repo = MagicMock(return_value=mock_repo)
        existing_labels = []
        for name in ["jclee-bot", "review-finding", "critical"]:
            label = MagicMock()
            label.name = name
            existing_labels.append(label)
        mock_repo.get_labels.return_value = existing_labels

        provider.ensure_labels(["jclee-bot", "review-finding", "critical"])

        mock_repo.create_label.assert_not_called()

    def test_ensure_labels_soft_fails(self, provider, mock_repo):
        provider._get_repo = MagicMock(return_value=mock_repo)
        mock_repo.get_labels.side_effect = Exception("api error")

        provider.ensure_labels(["jclee-bot", "review-finding"])

        # Should not raise
