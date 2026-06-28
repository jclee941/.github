from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import requests

from jclee_bot import issue_commands
from jclee_bot.payload_parsing import repo_full_name_from_payload

GITHUB_API = "https://api.github.com"
CheckName = Literal["elk_setup", "elk_health", "runtime_health", "bot_health"]
Status = Literal["healthy", "critical"]
ALL_CHECKS: tuple[CheckName, ...] = ("elk_setup", "elk_health", "runtime_health", "bot_health")


@dataclass(frozen=True, slots=True)
class HealthResult:
    name: CheckName
    status: Status
    summary: str
    issue_title: str
    labels: tuple[str, ...]
    details: dict[str, str] = field(default_factory=dict)


def _env(payload: dict[str, Any], key: str, *aliases: str) -> str:
    for name in (key, *aliases):
        value = payload.get(name.lower()) or payload.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    import os

    for name in (key, *aliases):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _base_url(payload: dict[str, Any]) -> str:
    raw = _env(payload, "ELK_URL", "ELK_HOST", "ELASTICSEARCH_HOSTS")
    if "," in raw:
        raw = raw.split(",", 1)[0].strip()
    if raw and not raw.startswith(("http://", "https://")):
        raw = f"http://{raw}"
    return raw.rstrip("/")


def _auth(payload: dict[str, Any]) -> tuple[str, str] | None:
    user = _env(payload, "ELK_USERNAME", "ELASTICSEARCH_USERNAME")
    password = _env(payload, "ELK_PASSWORD", "ELASTICSEARCH_PASSWORD")
    return (user, password) if user and password else None


def _elk_request(
    payload: dict[str, Any],
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
) -> requests.Response:
    base_url = _base_url(payload)
    if not base_url:
        raise RuntimeError("ELK_URL/ELK_HOST/ELASTICSEARCH_HOSTS is not configured")
    response = requests.request(method, f"{base_url}{path}", auth=_auth(payload), json=json_body, timeout=15)
    response.raise_for_status()
    return response


def _critical(name: CheckName, title: str, labels: tuple[str, ...], summary: str, **details: str) -> HealthResult:
    return HealthResult(
        name=name,
        status="critical",
        summary=summary,
        issue_title=title,
        labels=labels,
        details=details,
    )


def _healthy(name: CheckName, title: str, labels: tuple[str, ...], summary: str, **details: str) -> HealthResult:
    return HealthResult(name=name, status="healthy", summary=summary, issue_title=title, labels=labels, details=details)


def check_elk_setup(payload: dict[str, Any]) -> HealthResult:
    title = "ELK Setup Failed"
    labels = ("elk-health", "automation")
    try:
        _elk_request(
            payload,
            "PUT",
            "/_index_template/jclee-bot-logs",
            json_body={
                "index_patterns": ["jclee-bot-logs-*"],
                "template": {
                    "settings": {
                        "number_of_shards": 1,
                        "number_of_replicas": 0,
                        "refresh_interval": "5s",
                        "index.lifecycle.name": "jclee-bot-logs",
                        "index.lifecycle.rollover_alias": "jclee-bot-logs",
                    }
                },
                "priority": 500,
                "version": 1,
            },
        )
        _elk_request(
            payload,
            "PUT",
            "/_ilm/policy/jclee-bot-logs",
            json_body={
                "policy": {
                    "phases": {
                        "hot": {"actions": {"rollover": {"max_primary_shard_size": "10gb", "max_age": "7d"}}},
                        "delete": {"min_age": "30d", "actions": {"delete": {}}},
                    }
                }
            },
        )
    except Exception as exc:  # noqa: BLE001
        return _critical("elk_setup", title, labels, f"ELK setup failed: {type(exc).__name__}", error=str(exc))
    return _healthy("elk_setup", title, labels, "jclee-bot ELK template and ILM policy are installed")


def _index_count(payload: dict[str, Any], pattern: str) -> int:
    response = _elk_request(payload, "GET", f"/_cat/indices/{pattern}?h=index")
    return len([line for line in response.text.splitlines() if line.strip()])


def check_elk_health(payload: dict[str, Any]) -> HealthResult:
    title = "ELK Health Check Failed"
    labels = ("elk-health", "automation")
    try:
        cluster = _elk_request(payload, "GET", "/_cluster/health").json()
        new_count = _index_count(payload, "jclee-bot-logs-*")
        legacy_count = _index_count(payload, "github-bot-logs-*")
    except Exception as exc:  # noqa: BLE001
        return _critical("elk_health", title, labels, f"ELK health check failed: {type(exc).__name__}", error=str(exc))
    if new_count + legacy_count <= 0:
        return _critical(
            "elk_health",
            title,
            labels,
            "No jclee-bot or legacy github-bot log indices exist; filebeat log shipping is broken",
            cluster_status=str(cluster.get("status", "")),
        )
    return _healthy(
        "elk_health",
        title,
        labels,
        "ELK is reachable and bot log indices are present",
        cluster_status=str(cluster.get("status", "")),
        jclee_bot_indices=str(new_count),
        legacy_indices=str(legacy_count),
    )


def _http_status(url: str, *, headers: dict[str, str] | None = None, head: bool = False) -> int:
    method = requests.head if head else requests.get
    response = method(url, headers=headers, timeout=20, allow_redirects=True)
    return response.status_code


def check_runtime_health(payload: dict[str, Any]) -> HealthResult:
    labels = ("runtime-health", "automation")
    base_url = _env(payload, "BOT_PUBLIC_BASE_URL") or "https://bot.jclee.me"
    webhook = f"{base_url.rstrip('/')}/api/v1/github_webhooks"
    cliproxy = _env(payload, "CLIPROXY_MODELS_URL") or "https://cliproxy.jclee.me/v1/models"
    try:
        webhook_status = _http_status(webhook, head=True)
    except Exception as exc:  # noqa: BLE001
        return _critical(
            "runtime_health",
            "Bot webhook endpoint unreachable",
            labels,
            "Webhook endpoint did not respond",
            error=str(exc),
        )
    if webhook_status not in {200, 401, 403, 404, 405}:
        return _critical(
            "runtime_health",
            "Bot webhook endpoint unreachable",
            labels,
            f"Unexpected webhook HTTP {webhook_status}",
        )
    try:
        cliproxy_status = _http_status(cliproxy)
    except Exception as exc:  # noqa: BLE001
        return _critical(
            "runtime_health",
            "CLIProxyAPI unreachable",
            labels,
            "CLIProxyAPI did not respond",
            error=str(exc),
        )
    if cliproxy_status != 401:
        return _critical(
            "runtime_health",
            "CLIProxyAPI unreachable",
            labels,
            f"Unexpected unauthenticated CLIProxyAPI HTTP {cliproxy_status}",
        )
    return _healthy(
        "runtime_health",
        "Runtime Health Check failed",
        labels,
        "Webhook and CLIProxyAPI runtime endpoints responded",
    )


def check_bot_health(token: str, payload: dict[str, Any]) -> HealthResult:
    title = "[bot-health] jclee-bot critical alert"
    labels = ("bot-health", "critical", "automation")
    api_key = _env(payload, "CLIPROXY_API_KEY")
    if not api_key:
        return _critical("bot_health", title, labels, "CLIPROXY_API_KEY is not configured for native bot health")
    status = _http_status("https://cliproxy.jclee.me/v1/models", headers={"Authorization": f"Bearer {api_key}"})
    if status != 200:
        return _critical("bot_health", title, labels, f"CLIProxyAPI authenticated health returned HTTP {status}")
    owner = str(repo_full_name_from_payload(payload) or "jclee941/jclee-bot").split("/", 1)[0]
    cutoff = (datetime.now(UTC) - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
    response = requests.get(
        f"{GITHUB_API}/search/issues",
        headers=issue_commands._headers(token),  # noqa: SLF001
        params={"q": f"commenter:jclee-bot[bot] user:{owner} updated:>={cutoff}", "per_page": 1},
        timeout=30,
    )
    response.raise_for_status()
    count = int(response.json().get("total_count", 0) or 0)
    if count <= 0:
        return _critical(
            "bot_health",
            title,
            labels,
            "jclee-bot has no issue or PR comment activity in the last 48 hours",
        )
    return _healthy("bot_health", title, labels, f"CLIProxyAPI is healthy and jclee-bot has {count} recent activities")
