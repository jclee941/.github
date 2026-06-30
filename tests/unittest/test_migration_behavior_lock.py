"""Behavior-lock smoke tests for the pr_agent -> jclee_bot.review_engine migration.

These pin the production-critical surfaces that the package relocation could break:
the FastAPI app composition (reused upstream app object + fork routes), the review
engine entry points, secret masking, and config loading. They must stay GREEN on the
current code AND after the migration completes; their job is to make a missed import
or lost package-data fail loudly here rather than silently in production.
"""

from __future__ import annotations

import importlib

import pytest
from starlette.routing import Match

# Routes the running GitHub App MUST expose. The first four come from the reused
# upstream FastAPI app object; the rest are fork-owned (jclee_bot) routes.
REQUIRED_ROUTES = {
    ("POST", "/api/v1/github_webhooks"),
    ("GET", "/health"),
    ("GET", "/ready"),
    ("GET", "/metrics"),
    ("POST", "/api/v1/checks_webhook"),
    ("POST", "/api/v1/issue_maintenance"),
    ("POST", "/api/v1/ci_failure_issues"),
    ("POST", "/api/v1/issue_commands"),
    ("POST", "/api/v1/native_health"),
    ("POST", "/api/v1/repo_metadata"),
    ("POST", "/api/v1/readme_automation"),
}


def _app_matches_path(app, path: str, method: str) -> bool:
    scope = {"type": "http", "path": path, "method": method, "root_path": "", "headers": []}
    return any(route.matches(scope)[0] is Match.FULL for route in app.router.routes)


def test_app_loads_and_exposes_required_routes() -> None:
    from jclee_bot.app import app

    missing = {f"{method} {path}" for method, path in REQUIRED_ROUTES if not _app_matches_path(app, path, method)}
    assert not missing, f"app is missing required production routes: {sorted(missing)}"


def test_review_engine_cli_run_is_importable() -> None:
    """The AI review CLI entry point must remain importable and callable."""
    cli = importlib.import_module("jclee_bot.review_engine.cli")
    assert callable(cli.run), "review engine cli.run must be a callable entry point"


def test_review_engine_core_tools_importable() -> None:
    """The core AI review tools must stay importable from the new namespace."""
    reviewer = importlib.import_module("jclee_bot.review_engine.tools.pr_reviewer")
    assert hasattr(reviewer, "PRReviewer")
    agent = importlib.import_module("jclee_bot.review_engine.agent.pr_agent")
    assert hasattr(agent, "PRAgent")


def test_secret_masking_redacts_known_secret() -> None:
    """secret_masking.mask_text is used by scripts/redact_exposed_secrets.py."""
    masking = importlib.import_module("jclee_bot.review_engine.algo.secret_masking")
    secret = "ghp_" + "a" * 36
    masked = masking.mask_text(secret)
    assert secret not in masked, "GitHub PAT pattern must be redacted by mask_text"


def test_config_loader_resolves_settings() -> None:
    """Config loader + bundled settings TOMLs must resolve from the new package."""
    loader = importlib.import_module("jclee_bot.review_engine.config_loader")
    settings = loader.get_settings()
    # Bundled prompt/config TOMLs are package data; a missing file would raise here.
    assert settings is not None


@pytest.mark.parametrize(
    "module",
    [
        "jclee_bot.review_engine.servers.github_app",
        "jclee_bot.review_engine.servers.github_action_runner",
        "jclee_bot.review_engine.servers.gunicorn_config",
    ],
)
def test_server_modules_importable(module: str) -> None:
    """Server modules that Docker/CI entrypoints reference must stay importable."""
    assert importlib.import_module(module) is not None
