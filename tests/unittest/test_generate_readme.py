"""Unit tests for scripts/generate_readme.py.

These tests validate the README generator helper WITHOUT making network
calls. They guard against the dead-code duplication bug and enforce the
canonical CLIProxyAPI model fallback chain.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "generate_readme.py"
assert SCRIPT.exists(), f"generate_readme.py not found: {SCRIPT}"


def _load_module():
    """Import generate_readme.py as a module (no API key required)."""
    spec = importlib.util.spec_from_file_location("generate_readme", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_canonical_model_chain():
    """MODELS must match the canonical CLIProxyAPI fallback chain."""
    mod = _load_module()
    assert mod.MODELS == ["minimax-m2.7", "gpt-5.5"], (
        f"generate_readme MODELS drifted from canonical chain: {mod.MODELS}"
    )


def test_no_stale_model_text_in_prompt():
    """Prompt must not advertise the old Kimi-inclusive chain."""
    text = SCRIPT.read_text()
    assert "kimi-k2.6" not in text and "kimi-k2.5" not in text, (
        "generate_readme.py still names the stale Kimi model chain in its prompt"
    )


def test_no_unreachable_duplicate_function_bodies():
    """read_key_files and generate_readme must each have exactly one body.

    The original file accidentally pasted each function body twice; the
    second copy was dead code after the `return`. Guard against regression.
    """
    text = SCRIPT.read_text()
    assert text.count("def read_key_files(") == 1, (
        "read_key_files is defined/duplicated more than once"
    )
    assert text.count("def generate_readme(") == 1, (
        "generate_readme is defined/duplicated more than once"
    )
    # The unreachable duplicate followed each `return` with a re-declared
    # `candidates = [` / `user_parts = [`. After cleanup there must be exactly
    # one `candidates = [` (inside read_key_files).
    assert text.count("candidates = [") == 1, (
        "duplicate unreachable 'candidates = [' block still present"
    )


def test_module_imports_without_api_key(monkeypatch):
    """Importing the module must not require CLIPROXY_API_KEY."""
    monkeypatch.delenv("CLIPROXY_API_KEY", raising=False)
    mod = _load_module()
    assert callable(mod.generate_readme)
    assert callable(mod.read_key_files)
