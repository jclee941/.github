from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TypeAlias
from urllib.parse import urlsplit, urlunsplit

try:
    from cliproxy_client import CliproxyCredentialError, _read_1password_secret
except ModuleNotFoundError:
    from scripts.cliproxy_client import CliproxyCredentialError, _read_1password_secret

DEFAULT_CLIPROXY_MANAGEMENT_BASE_PATH = "/v0/management"
JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True, slots=True)
class CliproxyManagementConfig:
    base_url: str
    key: str


@dataclass(frozen=True, slots=True)
class ProviderQuota:
    provider: str
    recent_success: int = 0
    recent_failed: int = 0
    total_success: int = 0
    total_failed: int = 0
    unavailable: bool = False


def _resolve_optional_secret(
    *,
    env: Mapping[str, str],
    value_key: str,
    ref_key: str,
    secret_name: str,
) -> str:
    direct = env.get(value_key, "").strip()
    if direct:
        return direct
    secret_ref = env.get(ref_key, "").strip()
    if not secret_ref:
        return ""
    return _read_1password_secret(secret_ref, secret_name=secret_name)


def _management_base_url(raw_url: str) -> str:
    parsed = urlsplit(raw_url)
    path = parsed.path.rstrip("/")
    if path.endswith(DEFAULT_CLIPROXY_MANAGEMENT_BASE_PATH):
        return raw_url.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, DEFAULT_CLIPROXY_MANAGEMENT_BASE_PATH, "", ""))


def resolve_cliproxy_management_config(env: Mapping[str, str] | None = None) -> CliproxyManagementConfig | None:
    source = env if env is not None else os.environ
    url = _resolve_optional_secret(
        env=source,
        value_key="CLIPROXY_MANAGEMENT_URL",
        ref_key="CLIPROXY_MANAGEMENT_URL_OP_REF",
        secret_name="CLIPROXY_MANAGEMENT_URL",
    )
    key = _resolve_optional_secret(
        env=source,
        value_key="CLIPROXY_MANAGEMENT_KEY",
        ref_key="CLIPROXY_MANAGEMENT_KEY_OP_REF",
        secret_name="CLIPROXY_MANAGEMENT_KEY",
    )
    if not url or not key:
        return None
    return CliproxyManagementConfig(base_url=_management_base_url(url), key=key)


def _management_get_json(config: CliproxyManagementConfig, path: str) -> JsonValue:
    req = urllib.request.Request(
        f"{config.base_url}/{path.lstrip('/')}",
        headers={"Authorization": f"Bearer {config.key}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _as_int(value: JsonValue) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _recent_counts(value: JsonValue) -> tuple[int, int]:
    if not isinstance(value, list):
        return 0, 0
    success = 0
    failed = 0
    for item in value:
        if isinstance(item, dict):
            success += _as_int(item.get("success"))
            failed += _as_int(item.get("failed"))
    return success, failed


def _provider_from_model(model: str) -> str:
    normalized = model.lower()
    if normalized.startswith(("minimax-", "minimax/")):
        return "minimax"
    if normalized.startswith(("gpt-", "codex-", "openai/gpt-")):
        return "codex"
    if normalized.startswith(("claude-", "anthropic/")):
        return "claude"
    if normalized.startswith(("gemini-", "google/")):
        return "gemini"
    return normalized.split("/", 1)[0]


def _merge_quota(current: ProviderQuota, update: ProviderQuota) -> ProviderQuota:
    return ProviderQuota(
        provider=current.provider,
        recent_success=current.recent_success + update.recent_success,
        recent_failed=current.recent_failed + update.recent_failed,
        total_success=current.total_success + update.total_success,
        total_failed=current.total_failed + update.total_failed,
        unavailable=current.unavailable or update.unavailable,
    )


def _quota_from_auth_files(payload: JsonValue) -> dict[str, ProviderQuota]:
    if not isinstance(payload, dict):
        return {}
    files = payload.get("files")
    if not isinstance(files, list):
        return {}

    quotas: dict[str, ProviderQuota] = {}
    for item in files:
        if not isinstance(item, dict):
            continue
        provider_value = item.get("provider")
        if not isinstance(provider_value, str) or not provider_value:
            continue
        recent_success, recent_failed = _recent_counts(item.get("recent_requests"))
        quota = ProviderQuota(
            provider=provider_value,
            recent_success=recent_success,
            recent_failed=recent_failed,
            total_success=_as_int(item.get("success")),
            total_failed=_as_int(item.get("failed")),
            unavailable=bool(item.get("disabled")) or bool(item.get("unavailable")),
        )
        quotas[provider_value] = _merge_quota(quotas.get(provider_value, ProviderQuota(provider_value)), quota)
    return quotas


def _quota_from_api_key_usage(payload: JsonValue) -> dict[str, ProviderQuota]:
    if not isinstance(payload, dict):
        return {}
    quotas: dict[str, ProviderQuota] = {}
    for provider, entries in payload.items():
        if not isinstance(entries, dict):
            continue
        quota = ProviderQuota(provider=provider)
        for stats in entries.values():
            if not isinstance(stats, dict):
                continue
            recent_success, recent_failed = _recent_counts(stats.get("recent_requests"))
            quota = _merge_quota(
                quota,
                ProviderQuota(
                    provider=provider,
                    recent_success=recent_success,
                    recent_failed=recent_failed,
                    total_success=_as_int(stats.get("success")),
                    total_failed=_as_int(stats.get("failed")),
                ),
            )
        quotas[provider] = quota
    return quotas


def _provider_quotas(config: CliproxyManagementConfig) -> dict[str, ProviderQuota]:
    quotas = _quota_from_auth_files(_management_get_json(config, "auth-files"))
    usage_quotas = _quota_from_api_key_usage(_management_get_json(config, "api-key-usage"))
    for provider, quota in usage_quotas.items():
        quotas[provider] = _merge_quota(quotas.get(provider, ProviderQuota(provider)), quota)
    return quotas


def _env_int(env: Mapping[str, str], name: str, default: int) -> int:
    try:
        return int(env.get(name, str(default)))
    except ValueError:
        return default


def _env_float(env: Mapping[str, str], name: str, default: float) -> float:
    try:
        return float(env.get(name, str(default)))
    except ValueError:
        return default


def route_models_by_quota(models: Sequence[str], env: Mapping[str, str] | None = None) -> list[str]:
    source = env if env is not None else os.environ
    if source.get("CLIPROXY_DYNAMIC_ROUTING", "true").lower() == "false":
        return list(models)
    try:
        config = resolve_cliproxy_management_config(source)
        if config is None:
            return list(models)
        quotas = _provider_quotas(config)
    except (CliproxyCredentialError, OSError, urllib.error.URLError, ValueError):
        return list(models)

    failure_threshold = _env_int(source, "CLIPROXY_ROUTE_FAILURE_THRESHOLD", 1)
    failure_ratio = _env_float(source, "CLIPROXY_ROUTE_FAILURE_RATIO", 0.5)
    recent_success_limit = _env_int(source, "CLIPROXY_ROUTE_RECENT_SUCCESS_LIMIT", 0)

    def sort_key(index_and_model: tuple[int, str]) -> tuple[int, int, int]:
        index, model = index_and_model
        quota = quotas.get(_provider_from_model(model))
        if quota is None:
            return 0, 0, index
        recent_total = quota.recent_success + quota.recent_failed
        ratio = quota.recent_failed / recent_total if recent_total else 0.0
        degraded = (
            quota.unavailable
            or quota.recent_failed >= failure_threshold
            or (recent_total > 0 and ratio >= failure_ratio)
        )
        overloaded = recent_success_limit > 0 and quota.recent_success >= recent_success_limit
        penalty = 2 if degraded else 1 if overloaded else 0
        return penalty, quota.recent_success, index

    return [model for _, model in sorted(enumerate(models), key=sort_key)]
