from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import jclee_bot.review_engine.servers.github_app as github_app
from jclee_bot.review_engine.servers.monitoring import WEBHOOK_FAILURES_TOTAL


@pytest.mark.asyncio
async def test_handle_request_with_metrics_records_failure_and_reraises():
    body = {
        "action": "opened",
        "repository": {"full_name": "jclee941/example"},
        "sender": {"login": "octocat"},
        "installation": {"id": 12345},
        "pull_request": {"html_url": "https://github.com/jclee941/example/pull/7"},
    }
    event = "pull_request"
    counter = WEBHOOK_FAILURES_TOTAL.labels(event=event, action="opened", exception_type="ValueError")
    before = counter._value.get()
    logger = MagicMock()

    with (
        patch.object(github_app, "handle_request", new=AsyncMock(side_effect=ValueError("boom"))),
        patch.object(github_app, "record_webhook_failure", wraps=github_app.record_webhook_failure) as record_failure,
        patch.object(github_app, "get_logger", return_value=logger),
    ):
        with pytest.raises(ValueError, match="boom"):
            await github_app._handle_request_with_metrics(body, event)

    record_failure.assert_called_once_with(event, "opened", "ValueError")
    assert counter._value.get() == before + 1
    logger.exception.assert_called_once()
    message, = logger.exception.call_args.args
    assert message == "Unhandled exception in webhook handler"
    artifact = logger.exception.call_args.kwargs["artifact"]
    assert artifact == {
        "event": event,
        "action": "opened",
        "repo": "jclee941/example",
        "sender": "octocat",
        "installation_id": 12345,
        "pr_url": "https://github.com/jclee941/example/pull/7",
        "exception_type": "ValueError",
    }


def test_webhook_route_fast_acks_and_defers_processing():
    """GitHub webhooks must be acknowledged quickly (200) with LLM-backed work
    deferred to a background task, otherwise GitHub's webhook timeout triggers
    retry storms / duplicate reviews. Guard against accidentally moving the
    minutes-long handler into the request path.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from starlette.background import BackgroundTasks
    from starlette.middleware import Middleware
    from starlette_context.middleware import RawContextMiddleware

    app = FastAPI(middleware=[Middleware(RawContextMiddleware)])
    app.include_router(github_app.router)

    deferred = []
    real_add_task = BackgroundTasks.add_task

    def spy_add_task(self, func, *args, **kwargs):
        deferred.append(func)
        return real_add_task(self, func, *args, **kwargs)

    handler = AsyncMock(return_value={})
    body = {"action": "opened", "repository": {"full_name": "jclee941/example"}}
    with (
        patch.object(github_app, "handle_request", new=handler),
        patch.object(github_app, "get_logger", return_value=MagicMock()),
        patch.object(BackgroundTasks, "add_task", spy_add_task),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/github_webhooks",
            json=body,
            headers={"X-GitHub-Event": "pull_request"},
        )

    assert resp.status_code == 200, resp.status_code
    # The processing must be deferred to a BackgroundTask, not run inline.
    # (TestClient runs background tasks before returning, so the add_task spy
    # is the reliable signal, not handler await timing.)
    assert any(f is github_app._handle_request_with_metrics for f in deferred), (
        f"webhook processing must be deferred to BackgroundTasks, got: {deferred}"
    )


@pytest.mark.asyncio
async def test_deferred_webhook_task_failures_are_not_swallowed():
    """The deferred background task must re-raise on failure so the error is
    visible to logs/Sentry/metrics rather than silently swallowed — the
    original defect (#234/#235/#240). Without a durable queue GitHub retry is
    not achievable, so observability (not HTTP status) is the contract.
    """
    body = {
        "action": "opened",
        "repository": {"full_name": "jclee941/example"},
        "sender": {"login": "octocat"},
    }
    with (
        patch.object(github_app, "handle_request", new=AsyncMock(side_effect=ValueError("boom"))),
        patch.object(github_app, "get_logger", return_value=MagicMock()),
    ):
        with pytest.raises(ValueError, match="boom"):
            await github_app._handle_request_with_metrics(body, "pull_request")


def test_record_webhook_failure_defaults_to_lowercase_unknown():
    """All metric label defaults must be lowercase 'unknown' for PromQL consistency."""
    from jclee_bot.review_engine.servers.monitoring import record_webhook_failure

    record_webhook_failure(None, None, None)
    # The labeled counter must exist with all-lowercase 'unknown' values
    counter = WEBHOOK_FAILURES_TOTAL.labels(
        event="unknown", action="unknown", exception_type="unknown"
    )
    assert counter._value.get() >= 1

    # Also verify no 'Unknown' (capitalized) label slipped through
    label_keys = list(WEBHOOK_FAILURES_TOTAL._metrics.keys())
    capitalized = [k for k in label_keys if "Unknown" in k]
    assert not capitalized, f"Found capitalized 'Unknown' in labels: {capitalized}"
