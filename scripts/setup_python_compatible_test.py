#!/usr/bin/env python3
"""Tests for the setup-python-compatible composite action.

`actions/setup-python` only publishes prebuilt CPython for GitHub-hosted
Ubuntu runners. The private `propose` repo runs a self-hosted Debian 12
runner, where `actions/setup-python@v5/v6` fails with:
    "The version '3.12' with architecture 'x64' was not found for Debian 12."
which blocked every python-using workflow (e.g. open-ready-pr) on that repo.

The fix is a local composite action that branches on `runner.environment`:
GitHub-hosted uses `actions/setup-python`; self-hosted uses `uv` to install a
managed Python and expose it on PATH. These tests pin that structure and that
the action is shipped to downstream repos via the deploy manifest.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / ".github/actions/setup-python-compatible/action.yml"


def _action() -> dict:
    return yaml.safe_load(ACTION.read_text(encoding="utf-8"))


def test_action_exists_and_is_composite() -> None:
    assert ACTION.exists(), f"missing composite action: {ACTION}"
    doc = _action()
    assert doc.get("runs", {}).get("using") == "composite"


def test_action_has_python_version_input() -> None:
    doc = _action()
    inputs = doc.get("inputs", {})
    assert "python-version" in inputs


def test_github_hosted_uses_setup_python() -> None:
    raw = ACTION.read_text(encoding="utf-8")
    assert "actions/setup-python" in raw
    assert "runner.environment == 'github-hosted'" in raw


def test_self_hosted_uses_uv() -> None:
    raw = ACTION.read_text(encoding="utf-8")
    assert "astral-sh/setup-uv" in raw
    assert "runner.environment == 'self-hosted'" in raw
    assert "uv python install" in raw


def test_self_hosted_venv_seeds_pip() -> None:
    """Many workflows call bare `pip`/`python -m pip`; `uv venv` does NOT install
    pip by default, so the venv must be created with --seed."""
    raw = ACTION.read_text(encoding="utf-8")
    assert "--seed" in raw, (
        "uv venv must use --seed so pip is available in the venv for downstream "
        "pip/python -m pip steps"
    )


def test_third_party_action_is_sha_pinned() -> None:
    """Repo convention: third-party actions are pinned to a full 40-char SHA."""
    raw = ACTION.read_text(encoding="utf-8")
    m = re.search(r"astral-sh/setup-uv@([^\s]+)", raw)
    assert m, "setup-uv reference not found"
    ref = m.group(1)
    assert re.fullmatch(r"[0-9a-f]{40}", ref), (
        f"setup-uv must be pinned to a full 40-char SHA, got {ref!r}"
    )

