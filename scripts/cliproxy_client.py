from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from openai import OpenAI
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

DEFAULT_CLIPROXY_BASE_URL = "https://cliproxy.jclee.me/v1"


class CliproxyCredentialError(RuntimeError):
    pass


class CliproxyResponseError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CliproxyMessage:
    role: str
    content: str


def _read_1password_secret(secret_ref: str, *, secret_name: str) -> str:
    try:
        completed = subprocess.run(
            ["op", "read", secret_ref],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except FileNotFoundError as exc:
        raise CliproxyCredentialError("1Password CLI 'op' is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise CliproxyCredentialError(f"1Password CLI timed out while reading {secret_name}") from exc
    except subprocess.CalledProcessError as exc:
        stderr = cast(str | None, exc.stderr)
        stdout = cast(str | None, exc.stdout)
        detail = (stderr or stdout or "").strip()
        message = f"1Password CLI failed to read {secret_name}"
        if detail:
            message = f"{message}: {detail}"
        raise CliproxyCredentialError(message) from exc

    value = completed.stdout.strip()
    if not value:
        raise CliproxyCredentialError(f"1Password returned an empty {secret_name}")
    return value


def read_1password_secret(secret_ref: str, *, secret_name: str) -> str:
    return _read_1password_secret(secret_ref, secret_name=secret_name)


def resolve_cliproxy_api_key(env: Mapping[str, str] | None = None) -> str:
    source = env if env is not None else os.environ
    direct = source.get("CLIPROXY_API_KEY", "").strip()
    if direct:
        return direct

    secret_ref = source.get("CLIPROXY_API_KEY_OP_REF", "").strip()
    if secret_ref:
        return _read_1password_secret(secret_ref, secret_name="CLIPROXY_API_KEY")

    raise CliproxyCredentialError("CLIPROXY_API_KEY or CLIPROXY_API_KEY_OP_REF is required")


def _chat_message_param(message: CliproxyMessage) -> ChatCompletionMessageParam:
    if message.role == "system":
        system_message: ChatCompletionSystemMessageParam = {"role": "system", "content": message.content}
        return system_message
    if message.role == "assistant":
        assistant_message: ChatCompletionAssistantMessageParam = {"role": "assistant", "content": message.content}
        return assistant_message
    user_message: ChatCompletionUserMessageParam = {"role": "user", "content": message.content}
    return user_message


def cliproxy_chat_completion(
    *,
    model: str,
    messages: Sequence[CliproxyMessage],
    api_key: str,
    base_url: str = DEFAULT_CLIPROXY_BASE_URL,
    max_tokens: int,
    temperature: float,
    timeout_seconds: float,
) -> str:
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout_seconds,
        max_retries=0,
    )
    request_messages = [_chat_message_param(message) for message in messages]
    response = client.chat.completions.create(
        model=model,
        messages=request_messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    content = response.choices[0].message.content
    if content is None:
        raise CliproxyResponseError(f"CLIProxyAPI returned empty content for model {model}")
    return content
