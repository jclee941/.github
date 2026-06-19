from __future__ import annotations

import subprocess

import pytest

from scripts import cliproxy_client


def test_resolve_cliproxy_api_key_prefers_direct_env(monkeypatch):
    called = {"op": False}

    def fake_read(_secret_ref: str) -> str:
        called["op"] = True
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

    def fake_read(secret_ref: str) -> str:
        refs.append(secret_ref)
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

    assert cliproxy_client._read_1password_secret("op://vault/item/field") == "secret"
    assert captured["args"] == ["op", "read", "op://vault/item/field"]
    assert captured["kwargs"]["check"] is True
    assert captured["kwargs"]["capture_output"] is True


def test_resolve_cliproxy_api_key_requires_key_or_1password_ref():
    with pytest.raises(cliproxy_client.CliproxyCredentialError):
        cliproxy_client.resolve_cliproxy_api_key({})
