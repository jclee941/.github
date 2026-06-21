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
    """CLIProxy-only routing makes one attempt, then raises."""
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
async def test_configured_fallback_base_is_ignored_for_cliproxy_only_routing():
    """Even configured fallback bases must not route traffic away from CLIProxyAPI."""
    h = _handler()
    bases = []

    async def fake_once(**kwargs):
        bases.append(kwargs.get("api_base"))
        raise openai.APITimeoutError(request=MagicMock())

    with (
        patch.object(h, "_get_completion_once", new=fake_once),
        patch("pr_agent.algo.ai_handlers.litellm_ai_handler.get_settings") as gs,
    ):
        gs.return_value.get.return_value = ["https://backup.example/v1"]
        with pytest.raises(openai.APITimeoutError):
            await h._get_completion(model="kimi-k2.6")

    assert bases == [None]


@pytest.mark.asyncio
async def test_rate_limit_does_not_switch_base():
    """Non-connectivity errors propagate without trying another base."""
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
async def test_multiple_configured_fallback_bases_are_ignored():
    """CLIProxy-only routing ignores every configured provider fallback base."""
    h = _handler()
    once = AsyncMock(side_effect=openai.APIConnectionError(request=MagicMock()))
    with (
        patch.object(h, "_get_completion_once", new=once),
        patch("pr_agent.algo.ai_handlers.litellm_ai_handler.get_settings") as gs,
    ):
        gs.return_value.get.return_value = ["https://b1/v1", "https://b2/v1"]
        with pytest.raises(openai.APIConnectionError):
            await h._get_completion(model="kimi-k2.6")
    assert once.await_count == 1


@pytest.mark.asyncio
async def test_minimax_m3_routes_as_openai_compatible():
    """MiniMax-M3 (capitalized id, served via api.minimax.io OpenAI-compatible
    endpoint) must get custom_llm_provider='openai' so litellm routes it.
    Regression guard: the prefix tuple originally only had lowercase 'minimax-',
    so 'MiniMax-M3'.startswith('minimax-') was False and the model failed.
    """
    h = _handler()
    captured = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        return {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}

    with (
        patch("pr_agent.algo.ai_handlers.litellm_ai_handler.acompletion", new=fake_acompletion),
        patch("pr_agent.algo.ai_handlers.litellm_ai_handler.get_settings") as gs,
    ):
        gs.return_value.get.return_value = 128000
        await h._get_completion_once(model="MiniMax-M3", messages=[{"role": "user", "content": "hi"}])

    assert captured.get("custom_llm_provider") == "openai", (
        "MiniMax-M3 must be routed as an OpenAI-compatible model "
        f"(custom_llm_provider='openai'), got {captured.get('custom_llm_provider')!r}"
    )
