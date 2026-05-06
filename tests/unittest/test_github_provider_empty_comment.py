from unittest.mock import MagicMock, patch

import pytest

from pr_agent.git_providers.github_provider import GithubProvider


class TestGithubProviderEmptyComment:
    """Test suite for empty comment body guards in GitHub provider."""

    @pytest.fixture
    def provider(self):
        provider = object.__new__(GithubProvider)
        provider.max_comment_chars = 65000
        provider.limit_output_characters = lambda text, limit: text
        provider.pr = MagicMock()
        provider.issue_main = None
        provider.repo = "jclee941/test-repo"
        provider.base_url = "https://api.github.com"
        return provider

    def test_publish_comment_skips_empty_string(self, provider):
        result = provider.publish_comment("")
        assert result is None
        provider.pr.create_issue_comment.assert_not_called()

    def test_publish_comment_skips_whitespace(self, provider):
        result = provider.publish_comment("   \n\t")
        assert result is None
        provider.pr.create_issue_comment.assert_not_called()

    def test_publish_comment_publishes_non_empty_body(self, provider):
        response = MagicMock()
        response.user = MagicMock()
        response.user.login = "jclee-bot"
        provider.pr.create_issue_comment.return_value = response

        result = provider.publish_comment("hello")

        assert result == response
        provider.pr.create_issue_comment.assert_called_once_with("hello")
        assert response.is_temporary is False
        assert provider.github_user_id == "jclee-bot"

    def test_publish_comment_skips_empty_issue_comment(self, provider):
        provider.pr = None
        provider.issue_main = MagicMock()
        result = provider.publish_comment("")
        assert result is None
        provider.issue_main.create_comment.assert_not_called()

    def test_edit_comment_skips_empty_string(self, provider):
        comment = MagicMock()
        provider.edit_comment(comment, "")
        comment.edit.assert_not_called()

    def test_edit_comment_skips_whitespace(self, provider):
        comment = MagicMock()
        provider.edit_comment(comment, "   \n\t")
        comment.edit.assert_not_called()

    def test_edit_comment_edits_non_empty_body(self, provider):
        comment = MagicMock()
        provider.edit_comment(comment, "updated")
        comment.edit.assert_called_once_with(body="updated")

    def test_edit_comment_from_comment_id_skips_empty_string(self, provider):
        provider.pr._requester.requestJsonAndCheck = MagicMock()
        provider.edit_comment_from_comment_id(123, "")
        provider.pr._requester.requestJsonAndCheck.assert_not_called()

    def test_edit_comment_from_comment_id_skips_whitespace(self, provider):
        provider.pr._requester.requestJsonAndCheck = MagicMock()
        provider.edit_comment_from_comment_id(123, "   \n\t")
        provider.pr._requester.requestJsonAndCheck.assert_not_called()

    def test_edit_comment_from_comment_id_patches_non_empty_body(self, provider):
        provider.pr._requester.requestJsonAndCheck = MagicMock()
        provider.edit_comment_from_comment_id(123, "updated")
        provider.pr._requester.requestJsonAndCheck.assert_called_once_with(
            "PATCH",
            "https://api.github.com/repos/jclee941/test-repo/issues/comments/123",
            input={"body": "updated"},
        )

    def test_publish_comment_missing_context_returns_none(self, provider):
        provider.pr = None
        provider.issue_main = None
        result = provider.publish_comment("hello")
        assert result is None
