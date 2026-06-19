from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from openai import OpenAI

DEFAULT_CLIPROXY_BASE_URL = "https://cliproxy.jclee.me/v1"


class CliproxyCredentialError(RuntimeError):
    pass


class CliproxyResponseError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CliproxyMessage:
    role: str
    content: str


def _read_1password_secret(secret_ref: str) -> str:
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
        raise CliproxyCredentialError("1Password CLI timed out while reading CLIPROXY_API_KEY") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        message = "1Password CLI failed to read CLIPROXY_API_KEY"
        if detail:
            message = f"{message}: {detail}"
        raise CliproxyCredentialError(message) from exc

    value = completed.stdout.strip()
    if not value:
        raise CliproxyCredentialError("1Password returned an empty CLIPROXY_API_KEY")
    return value


def resolve_cliproxy_api_key(env: Mapping[str, str] | None = None) -> str:
    source = env if env is not None else os.environ
    direct = source.get("CLIPROXY_API_KEY", "").strip()
    if direct:
        return direct

    secret_ref = source.get("CLIPROXY_API_KEY_OP_REF", "").strip()
    if secret_ref:
        return _read_1password_secret(secret_ref)

    raise CliproxyCredentialError("CLIPROXY_API_KEY or CLIPROXY_API_KEY_OP_REF is required")


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
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": message.role, "content": message.content} for message in messages],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    content = response.choices[0].message.content
    if content is None:
        raise CliproxyResponseError(f"CLIProxyAPI returned empty content for model {model}")
    return content
