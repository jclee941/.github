from __future__ import annotations

import subprocess

import pytest

from scripts import cliproxy_client, cliproxy_routing


def test_resolve_cliproxy_api_key_prefers_direct_env(monkeypatch):
    called = {"op": False}

    def fake_read(_secret_ref: str, *, secret_name: str) -> str:
        called["op"] = True
        assert secret_name == "CLIPROXY_API_KEY"
        return "from-op"

    monkeypatch.setattr(cliproxy_client, "_read_1password_secret", fake_read)

    assert cliproxy_client.resolve_cliproxy_api_key(
        {
            "CLIPROXY_API_KEY": "direct-key",
            "CLIPROXY_API_KEY_OP_REF": "op://vault/item/field",
        }
    ) == "direct-key"
    assert called["op"] is False


def test_resolve_cliproxy_api_key_uses_1password_ref(monkeypatch):
    refs = []

    def fake_read(secret_ref: str, *, secret_name: str) -> str:
        refs.append(secret_ref)
        assert secret_name == "CLIPROXY_API_KEY"
        return "from-op"

    monkeypatch.setattr(cliproxy_client, "_read_1password_secret", fake_read)

    assert cliproxy_client.resolve_cliproxy_api_key(
        {"CLIPROXY_API_KEY_OP_REF": "op://vault/cliproxy/credential"}
    ) == "from-op"
    assert refs == ["op://vault/cliproxy/credential"]


def test_read_1password_secret_does_not_use_shell(monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(args, 0, stdout="secret\n", stderr="")

    monkeypatch.setattr(cliproxy_client.subprocess, "run", fake_run)

    assert cliproxy_client._read_1password_secret("op://vault/item/field", secret_name="CLIPROXY_API_KEY") == "secret"
    assert captured["args"] == ["op", "read", "op://vault/item/field"]
    assert captured["kwargs"]["check"] is True
    assert captured["kwargs"]["capture_output"] is True


def test_resolve_cliproxy_api_key_requires_key_or_1password_ref():
    with pytest.raises(cliproxy_client.CliproxyCredentialError):
        cliproxy_client.resolve_cliproxy_api_key({})


def test_management_url_normalizes_panel_url():
    assert (
        cliproxy_routing._management_base_url("https://cliproxy.jclee.me/management.html")
        == "https://cliproxy.jclee.me/v0/management"
    )


def test_route_models_by_quota_deprioritizes_failed_primary(monkeypatch):
    monkeypatch.setattr(
        cliproxy_routing,
        "resolve_cliproxy_management_config",
        lambda _env: cliproxy_routing.CliproxyManagementConfig(
            base_url="https://cliproxy.jclee.me/v0/management",
            key="management-key",
        ),
    )
    monkeypatch.setattr(
        cliproxy_routing,
        "_provider_quotas",
        lambda _config: {
            "codex": cliproxy_routing.ProviderQuota(provider="codex", recent_success=0, recent_failed=1),
            "minimax": cliproxy_routing.ProviderQuota(provider="minimax", recent_success=3, recent_failed=0),
        },
    )

    routed = cliproxy_routing.route_models_by_quota(
        ["gpt-5.5", "minimax-m3"],
        {"CLIPROXY_ROUTE_FAILURE_THRESHOLD": "1"},
    )

    assert routed == ["minimax-m3", "gpt-5.5"]


def test_route_models_by_quota_preserves_order_without_management_config():
    assert cliproxy_routing.route_models_by_quota(["gpt-5.5", "minimax-m3"], {}) == [
        "gpt-5.5",
        "minimax-m3",
    ]
