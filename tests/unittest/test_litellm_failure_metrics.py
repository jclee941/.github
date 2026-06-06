from unittest.mock import patch

import httpx
import openai
import pytest
from prometheus_client import REGISTRY
from tenacity import RetryError

import pr_agent.algo.ai_handlers.litellm_ai_handler as litellm_ai_handler
from pr_agent.algo.ai_handlers.litellm_ai_handler import MODEL_RETRIES, LiteLLMAIHandler


def _make_settings():
    return type("Settings", (), {
        "config": type("Config", (), {
            "reasoning_effort": None,
            "ai_timeout": 30,
            "custom_reasoning_model": False,
            "max_model_tokens": 32000,
            "verbosity_level": 0,
            "seed": -1,
            "get": lambda self, key, default=None: default,
        })(),
        "litellm": type("LiteLLM", (), {
            "get": lambda self, key, default=None: default,
        })(),
        "get": lambda self, key, default=None: default,
    })()


def _request():
    return httpx.Request("POST", "https://example.test/v1/chat/completions")


def _rate_limit_error():
    response = httpx.Response(429, request=_request())
    return openai.RateLimitError("rate limited", response=response, body=None)


def _api_timeout_error():
    return openai.APITimeoutError(_request())


def _api_connection_error():
    return openai.APIConnectionError(request=_request())


def _api_error():
    return openai.APIError("api failed", _request(), body=None)


def _metric_value(reason, model):
    return REGISTRY.get_sample_value("llm_failures_total", {"reason": reason, "model": model}) or 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reason", "exception_factory", "expected_exception", "expected_increment"),
    [
        ("rate_limit", _rate_limit_error, openai.RateLimitError, 1),
        ("timeout", _api_timeout_error, RetryError, MODEL_RETRIES),
        ("connect", _api_connection_error, RetryError, MODEL_RETRIES),
        ("api_error", _api_error, RetryError, MODEL_RETRIES),
        ("unknown", lambda: ValueError("unexpected"), TypeError, 1),
    ],
)
async def test_chat_completion_records_llm_failure_metrics(
    monkeypatch, reason, exception_factory, expected_exception, expected_increment
):
    model = f"test-model-{reason}"
    monkeypatch.setattr(litellm_ai_handler, "get_settings", lambda: _make_settings())

    async def raise_failure(self, **kwargs):
        raise exception_factory()

    with patch.object(LiteLLMAIHandler, "_get_completion", raise_failure):
        handler = LiteLLMAIHandler()
        before = _metric_value(reason, model)

        with pytest.raises(expected_exception):
            await handler.chat_completion(model=model, system="system", user="user")

    after = _metric_value(reason, model)
    assert after - before == expected_increment
