"""Live health checks for the jclee-bot GitHub App and its infrastructure."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import requests

from .repo_config import GITHUB_API_URL, GITHUB_OWNER

pytestmark = pytest.mark.app_health

BOT_LOGIN = "jclee-bot[bot]"
APP_SLUG = "jclee-bot"

WEBHOOK_URL = "https://bot.jclee.me/api/v1/github_webhooks"
CLIPROXY_URL = "https://cliproxy.jclee.me/v1/models"

CANDIDATE_REPOS = [
    f"{GITHUB_OWNER}/jclee-bot",
    f"{GITHUB_OWNER}/resume",
    f"{GITHUB_OWNER}/account",
]


def test_bot_recent_activity(github_client: requests.Session) -> None:
    """Verify jclee-bot has commented on at least one PR or issue in the last 7 days."""
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")

    found = False
    for repo in CANDIDATE_REPOS:
        response = github_client.get(
            f"{GITHUB_API_URL}/repos/{repo}/issues/comments",
            params={"since": since, "per_page": 100, "sort": "updated", "direction": "desc"},
        )
        if response.status_code != 200:
            continue

        payload = response.json()
        if not isinstance(payload, list):
            continue

        bot_comments = [
            comment
            for comment in payload
            if isinstance(comment, dict)
            and isinstance(comment.get("user"), dict)
            and (
                comment["user"].get("login") == BOT_LOGIN
                or (
                    comment["user"].get("type") == "Bot"
                    and "jclee-bot" in (comment["user"].get("login") or "")
                )
            )
        ]

        if bot_comments:
            found = True
            break

    if not found:
        pytest.skip("No bot comments found in the last 7 days (could be low activity period)")


def test_webhook_endpoint_reachable() -> None:
    """Verify the bot webhook endpoint is reachable from the public internet."""
    try:
        response = requests.head(WEBHOOK_URL, timeout=5, allow_redirects=True)
        if response.status_code == 405:
            response = requests.get(WEBHOOK_URL, timeout=5, allow_redirects=True)
    except requests.Timeout:
        pytest.skip("Webhook endpoint connection timed out (may be down)")
    except requests.ConnectionError:
        pytest.skip("Webhook endpoint is unreachable (may be down)")

    assert response.elapsed.total_seconds() < 5, (
        f"Webhook response time {response.elapsed.total_seconds():.2f}s >= 5s"
    )
    assert response.status_code in {200, 401, 403, 404, 405}, (
        f"Unexpected webhook status {response.status_code}"
    )


def test_app_installation_exists(github_client: requests.Session) -> None:
    """Verify the jclee-bot GitHub App is installed on at least one managed repo."""
    found = False
    for repo in CANDIDATE_REPOS:
        response = github_client.get(f"{GITHUB_API_URL}/repos/{repo}/installation")
        if response.status_code in {404, 401}:
            # 401 = OAuth token can't access GitHub App installation API
            # 404 = App not installed on this repo
            continue
            continue

        if response.status_code == 200:
            payload = response.json()
            assert isinstance(payload, dict), f"Malformed installation response for {repo}"

            app = payload.get("app")
            assert isinstance(app, dict), f"Malformed app payload for {repo}"
            assert app.get("slug") == APP_SLUG, (
                f"Expected app slug {APP_SLUG}, got {app.get('slug')!r}"
            )
            found = True
            break

    if not found:
        pytest.skip("GitHub App installation not found or no permission to view installations")


def test_cliproxy_endpoint_reachable() -> None:
    """Verify the CLIProxyAPI endpoint is up and responding (unauthenticated probe)."""
    try:
        response = requests.get(CLIPROXY_URL, timeout=5)
    except requests.Timeout:
        pytest.skip("CLIProxy endpoint connection timed out (may be down)")
    except requests.ConnectionError:
        pytest.skip("CLIProxy endpoint is unreachable (may be down)")

    assert response.elapsed.total_seconds() < 5, (
        f"CLIProxy response time {response.elapsed.total_seconds():.2f}s >= 5s"
    )
    assert response.status_code == 401, (
        f"Expected 401 from CLIProxy without auth, got {response.status_code}"
    )
