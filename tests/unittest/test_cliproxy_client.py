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


def test_management_config_allows_internal_management_without_tls_verification():
    config = cliproxy_routing.resolve_cliproxy_management_config(
        {
            "CLIPROXY_MANAGEMENT_URL": "http://cliproxyapi:8317/v0/management",
            "CLIPROXY_MANAGEMENT_KEY": "management-key",
            "CLIPROXY_MANAGEMENT_TLS_VERIFY": "false",
        }
    )

    assert config is not None
    assert config.base_url == "http://cliproxyapi:8317/v0/management"
    assert config.tls_verify is False


def test_management_config_rejects_tls_disabled_for_external_url():
    with pytest.raises(cliproxy_client.CliproxyCredentialError):
        cliproxy_routing.resolve_cliproxy_management_config(
            {
                "CLIPROXY_MANAGEMENT_URL": "https://cliproxy.jclee.me/management.html",
                "CLIPROXY_MANAGEMENT_KEY": "management-key",
                "CLIPROXY_MANAGEMENT_TLS_VERIFY": "false",
            }
        )


def test_management_config_rejects_external_plain_http():
    with pytest.raises(cliproxy_client.CliproxyCredentialError):
        cliproxy_routing.resolve_cliproxy_management_config(
            {
                "CLIPROXY_MANAGEMENT_URL": "http://cliproxy.jclee.me/v0/management",
                "CLIPROXY_MANAGEMENT_KEY": "management-key",
            }
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
