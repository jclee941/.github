"""E2E tests for GitHub webhook handling."""

from unittest.mock import patch

import pytest


class TestWebhookPRReviewFlow:
    """Test the full PR webhook flow."""

    def test_pull_request_opened_webhook(self, test_client, pull_request_opened_payload, github_headers):
        """Test that a pull_request.opened webhook is accepted."""
        response = test_client.post(
            "/api/v1/github_webhooks",
            json=pull_request_opened_payload,
            headers=github_headers,
        )
        # Should return 200 immediately (background task is async)
        assert response.status_code == 200

    def test_issue_comment_review_webhook(self, test_client, issue_comment_payload):
        """Test that a PR comment with /review is accepted."""
        headers = {
            "X-GitHub-Event": "issue_comment",
            "Content-Type": "application/json",
        }
        response = test_client.post(
            "/api/v1/github_webhooks",
            json=issue_comment_payload,
            headers=headers,
        )
        assert response.status_code == 200

    def test_webhook_without_action(self, test_client):
        """Test that webhooks without action are handled gracefully."""
        payload = {
            "installation": {"id": 12345},
            "repository": {"full_name": "jclee941/test"},
        }
        response = test_client.post(
            "/api/v1/github_webhooks",
            json=payload,
            headers={"X-GitHub-Event": "pull_request", "Content-Type": "application/json"},
        )
        assert response.status_code == 200

    def test_webhook_bot_user_ignored(self, test_client):
        """Test that webhooks from bot users are ignored."""
        payload = {
            "action": "opened",
            "pull_request": {
                "url": "https://api.github.com/repos/jclee941/test/pulls/1",
                "number": 1,
                "title": "Test",
                "state": "open",
                "draft": False,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "user": {
                    "login": "dependabot[bot]",
                    "id": 49699333,
                    "type": "Bot",
                },
                "base": {"ref": "master", "sha": "abc123"},
                "head": {"ref": "feature", "sha": "def456"},
            },
            "repository": {"full_name": "jclee941/test"},
            "installation": {"id": 12345},
            "sender": {
                "login": "dependabot[bot]",
                "id": 49699333,
                "type": "Bot",
            },
        }
        response = test_client.post(
            "/api/v1/github_webhooks",
            json=payload,
            headers={"X-GitHub-Event": "pull_request", "Content-Type": "application/json"},
        )
        assert response.status_code == 200

    def test_marketplace_webhook(self, test_client):
        """Test that marketplace webhooks are accepted."""
        payload = {
            "action": "purchased",
            "marketplace_purchase": {
                "account": {"login": "testuser", "id": 12345},
            },
        }
        response = test_client.post(
            "/api/v1/marketplace_webhooks",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200
