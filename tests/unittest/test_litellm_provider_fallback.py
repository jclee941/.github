from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest

from pr_agent.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler


def _handler():
    """Build a handler without running the network-touching __init__."""
    h = LiteLLMAIHandler.__new__(LiteLLMAIHandler)
    h.streaming_required_models = []
    return h


@pytest.mark.asyncio
async def test_no_fallback_configured_propagates_after_single_attempt():
    """Empty api_base_fallbacks preserves original behavior: one attempt, then raise."""
    h = _handler()
    once = AsyncMock(side_effect=openai.APIConnectionError(request=MagicMock()))
    with (
        patch.object(h, "_get_completion_once", new=once),
        patch("pr_agent.algo.ai_handlers.litellm_ai_handler.get_settings") as gs,
    ):
        gs.return_value.get.return_value = []
        with pytest.raises(openai.APIConnectionError):
            await h._get_completion(model="kimi-k2.6")
    assert once.await_count == 1


@pytest.mark.asyncio
async def test_connect_failure_switches_to_fallback_base():
    """A connection/timeout failure on the primary base retries on the fallback base."""
    h = _handler()
    bases = []

    async def fake_once(**kwargs):
        bases.append(kwargs.get("api_base"))
        if kwargs.get("api_base") is None:  # primary base
            raise openai.APITimeoutError(request=MagicMock())
        return ("resp", "stop", MagicMock())

    with (
        patch.object(h, "_get_completion_once", new=fake_once),
        patch("pr_agent.algo.ai_handlers.litellm_ai_handler.get_settings") as gs,
    ):
        gs.return_value.get.return_value = ["https://backup.example/v1"]
        resp, finish, _ = await h._get_completion(model="kimi-k2.6")

    assert resp == "resp"
    assert bases == [None, "https://backup.example/v1"]


@pytest.mark.asyncio
async def test_rate_limit_does_not_switch_base():
    """Non-connectivity errors (rate limit) must propagate without trying fallbacks."""
    h = _handler()
    once = AsyncMock(
        side_effect=openai.RateLimitError("rl", response=MagicMock(), body=None)
    )
    with (
        patch.object(h, "_get_completion_once", new=once),
        patch("pr_agent.algo.ai_handlers.litellm_ai_handler.get_settings") as gs,
    ):
        gs.return_value.get.return_value = ["https://backup.example/v1"]
        with pytest.raises(openai.RateLimitError):
            await h._get_completion(model="kimi-k2.6")
    assert once.await_count == 1


@pytest.mark.asyncio
async def test_all_bases_exhausted_raises_last_error():
    """If every base fails to connect, the last connection error propagates."""
    h = _handler()
    once = AsyncMock(side_effect=openai.APIConnectionError(request=MagicMock()))
    with (
        patch.object(h, "_get_completion_once", new=once),
        patch("pr_agent.algo.ai_handlers.litellm_ai_handler.get_settings") as gs,
    ):
        gs.return_value.get.return_value = ["https://b1/v1", "https://b2/v1"]
        with pytest.raises(openai.APIConnectionError):
            await h._get_completion(model="kimi-k2.6")
    # primary + 2 fallbacks = 3 attempts
    assert once.await_count == 3
