from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import pr_agent.servers.github_app as github_app
from pr_agent.servers.monitoring import WEBHOOK_FAILURES_TOTAL


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


def test_record_webhook_failure_defaults_to_lowercase_unknown():
    """All metric label defaults must be lowercase 'unknown' for PromQL consistency."""
    from pr_agent.servers.monitoring import record_webhook_failure

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
