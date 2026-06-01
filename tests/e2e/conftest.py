"""E2E test fixtures for the GitHub App."""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Ensure we use test settings
os.environ.setdefault("CONFIG.LOG_LEVEL", "DEBUG")
os.environ.setdefault("GITHUB.WEBHOOK_SECRET", "false")
os.environ.setdefault("OPENAI.KEY", "test-key")
os.environ.setdefault("OPENAI.API_BASE", "http://localhost:8317/v1")


@pytest.fixture(scope="session", autouse=True)
def mock_git_provider():
    """Mock the GitHub provider for all E2E tests."""
    mock_provider = MagicMock()
    mock_provider.get_repo_settings.return_value = {}
    mock_provider.get_pr_description.return_value = ""
    mock_provider.get_diff_files.return_value = []
    mock_provider.publish_description.return_value = None
    mock_provider.publish_comment.return_value = None
    mock_provider.publish_persistent_comment.return_value = None
    mock_provider.publish_code_suggestions.return_value = None
    mock_provider.get_labels.return_value = []
    mock_provider.publish_labels.return_value = None
    mock_provider.remove_initial_comment.return_value = None
    mock_provider.get_previous_review.return_value = ""
    mock_provider.get_issue_comments.return_value = []
    mock_provider.add_eyes_reaction.return_value = None
    mock_provider.remove_reaction.return_value = None
    mock_provider.get_commit_messages.return_value = ""
    mock_provider.get_pr_branch.return_value = ""
    mock_provider.get_user_id.return_value = ""
    mock_provider.get_pr_title.return_value = ""

    with patch("pr_agent.git_providers.get_git_provider_with_context", return_value=mock_provider):
        yield mock_provider


@pytest.fixture(scope="session")
def test_client(mock_git_provider):
    """Create a TestClient for the FastAPI app."""
    from pr_agent.servers.github_app import app

    with TestClient(app) as client:
        yield client


@pytest.fixture
def pull_request_opened_payload():
    """Sample GitHub pull_request.opened webhook payload."""
    return {
        "action": "opened",
        "number": 1,
        "pull_request": {
            "url": "https://api.github.com/repos/jclee941/test/pulls/1",
            "html_url": "https://github.com/jclee941/test/pull/1",
            "number": 1,
            "title": "feat: test PR",
            "body": "Test description",
            "state": "open",
            "draft": False,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "user": {
                "login": "testuser",
                "id": 12345,
                "type": "User",
            },
            "base": {
                "ref": "master",
                "sha": "abc123",
                "repo": {
                    "full_name": "jclee941/test",
                    "clone_url": "https://github.com/jclee941/test.git",
                },
            },
            "head": {
                "ref": "feature",
                "sha": "def456",
                "repo": {
                    "full_name": "jclee941/test",
                    "clone_url": "https://github.com/jclee941/test.git",
                },
            },
        },
        "repository": {
            "full_name": "jclee941/test",
            "clone_url": "https://github.com/jclee941/test.git",
        },
        "installation": {"id": 12345},
        "sender": {
            "login": "testuser",
            "id": 12345,
            "type": "User",
        },
    }


@pytest.fixture
def issue_comment_payload():
    """Sample GitHub issue_comment.created webhook payload (PR comment)."""
    return {
        "action": "created",
        "issue": {
            "number": 1,
            "pull_request": {
                "url": "https://api.github.com/repos/jclee941/test/pulls/1",
            },
        },
        "comment": {
            "id": 123456,
            "body": "/review",
            "user": {
                "login": "testuser",
                "id": 12345,
            },
            "pull_request_url": "https://api.github.com/repos/jclee941/test/pulls/1",
        },
        "repository": {
            "full_name": "jclee941/test",
        },
        "installation": {"id": 12345},
        "sender": {
            "login": "testuser",
            "id": 12345,
            "type": "User",
        },
    }


@pytest.fixture
def github_headers():
    """Standard GitHub webhook headers."""
    return {
        "X-GitHub-Event": "pull_request",
        "Content-Type": "application/json",
    }
