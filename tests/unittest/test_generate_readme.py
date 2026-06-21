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
    """MODELS must try the requested gpt-5.5 primary before fallback models."""
    mod = _load_module()
    assert mod.MODELS == ["gpt-5.5", "minimax-m3"], (
        f"generate_readme MODELS drifted from canonical model: {mod.MODELS}"
    )


def test_no_stale_model_text_in_prompt():
    """README-generator prompt must not hardcode the retired minimax fallback."""
    text = SCRIPT.read_text()
    assert "minimax-m2.7" not in text, (
        "generate_readme.py must not hardcode minimax-m2.7; fallback is minimax-m3"
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


def test_sanitize_links_strips_nonexistent_jclee_repos():
    """The LLM hallucinates GitHub repo URLs (e.g. jclee941/CLIProxyAPI,
    jclee941/github-bot) that 404 and pollute documentation policy checks. The generator
    must neutralize links to non-existent jclee941 repos."""
    mod = _load_module()
    assert hasattr(mod, "sanitize_links"), (
        "generate_readme.py must define sanitize_links(text) to remove "
        "hallucinated/non-existent GitHub repo links before writing README."
    )
    md = (
        "See [CLIProxyAPI](https://github.com/jclee941/CLIProxyAPI) and "
        "[badge](https://github.com/jclee941/github-bot) plus the real "
        "[upstream](https://github.com/qodo-ai/pr-agent) and [self](https://github.com/jclee941/.github)."
    )
    out = mod.sanitize_links(md)
    # Hallucinated repo URLs must be gone (rewritten to the canonical repo).
    assert "github.com/jclee941/CLIProxyAPI" not in out, out
    assert "github.com/jclee941/github-bot" not in out, out
    # Real/allowed links must survive untouched.
    assert "github.com/qodo-ai/pr-agent" in out, out
    assert "github.com/jclee941/.github" in out, out

    # Badge form (nested brackets) must also be handled.
    badge = "[![v](https://img.shields.io/badge/x.svg)](https://github.com/jclee941/github-bot)"
    bout = mod.sanitize_links(badge)
    assert "jclee941/github-bot" not in bout, bout
    assert "img.shields.io" in bout, "badge image/label must be preserved"


def test_normalize_strips_think_block():
    """LLM emits <think>...</think> reasoning that must never reach README.md."""
    mod = _load_module()
    assert hasattr(mod, "normalize_llm_readme_response"), (
        "generate_readme.py must define normalize_llm_readme_response(text)."
    )
    raw = "<think>\nI will write a readme.\n</think>\n\n# Real Title\n\nbody"
    out = mod.normalize_llm_readme_response(raw)
    assert "<think>" not in out and "will write a readme" not in out, out
    assert out.lstrip().startswith("# Real Title"), out


def test_normalize_unwraps_json_content():
    """LLM wraps the README in a fenced JSON {"content": "..."} object."""
    mod = _load_module()
    raw = '```json\n{\n  "content": "# Title\\n\\nHello **world**\\n"\n}\n```'
    out = mod.normalize_llm_readme_response(raw)
    assert out.lstrip().startswith("# Title"), out
    assert "Hello **world**" in out, out
    assert '"content"' not in out and "```json" not in out, out


def test_normalize_think_then_json():
    """The real failure: <think> block followed by a fenced JSON content object."""
    mod = _load_module()
    raw = '<think>\nreasoning\n</think>\n\n```json\n{"content": "# T\\n\\nbody\\n"}\n```'
    out = mod.normalize_llm_readme_response(raw)
    assert out.lstrip().startswith("# T"), out
    assert "<think>" not in out and "```json" not in out and "reasoning" not in out, out


def test_normalize_unwraps_truncated_json():
    """Truncated JSON (response hit max_tokens mid-string, no closing brace/fence)
    must still yield best-effort Markdown, not a raw JSON wrapper."""
    mod = _load_module()
    raw = '```json\n{\n  "content": "# Title\\n\\nbody line that got cut off mid'
    out = mod.normalize_llm_readme_response(raw)
    assert out.lstrip().startswith("# Title"), out
    assert '"content"' not in out and "```json" not in out, out


def test_normalize_truncated_json_with_invalid_unicode_escape():
    """Truncated JSON whose body ends mid invalid \\u escape must not raise
    UnicodeDecodeError; normalize must degrade gracefully (#354/#356/#357)."""
    mod = _load_module()
    raw = '```json\n{\n  "content": "# Title\\n\\npath C:\\\\Users and a cut \\u00'
    out = mod.normalize_llm_readme_response(raw)
    assert isinstance(out, str)
    assert out.lstrip().startswith("# Title"), out


def test_normalize_passthrough_plain_markdown():
    """Plain markdown (no think / no json wrapper) must pass through unchanged."""
    mod = _load_module()
    raw = "# Title\n\nplain body\n"
    out = mod.normalize_llm_readme_response(raw)
    assert out.strip() == raw.strip(), out


def test_normalize_fixes_empty_badge_links():
    """LLM emits badge placeholders [![alt](img)](#) — the empty (#) link fails
    markdownlint MD042. normalize must drop the empty link wrapper, keep the badge."""
    mod = _load_module()
    raw = "# T\n\n[![Version](https://img.shields.io/badge/v.svg)](#)\n\nbody\n"
    out = mod.normalize_llm_readme_response(raw)
    assert "](#)" not in out, out
    assert "img.shields.io/badge/v.svg" in out, out


def test_sanitize_links_handles_http_and_www():
    """sanitize_links must catch http:// and www. variants of hallucinated repos."""
    mod = _load_module()
    md = (
        "[a](http://github.com/jclee941/github-bot) "
        "[b](https://www.github.com/jclee941/CLIProxyAPI) "
        "[ok](https://github.com/jclee941/.github)"
    )
    out = mod.sanitize_links(md)
    assert "jclee941/github-bot" not in out, out
    assert "jclee941/CLIProxyAPI" not in out, out
    assert "jclee941/.github" in out, out


def test_normalize_strips_thinking_variant():
    """The <thinking>...</thinking> tag variant must also be stripped."""
    mod = _load_module()
    raw = "<thinking>\nplan\n</thinking>\n\n# Title\n\nbody"
    out = mod.normalize_llm_readme_response(raw)
    assert "<thinking>" not in out and "plan" not in out, out
    assert out.lstrip().startswith("# Title"), out


def test_is_transient_error_classification():
    """Transient backend errors (524/502/503/timeout/connection) must be
    classified as retryable; genuine client errors (4xx other than 429) must
    not."""
    import urllib.error
    mod = _load_module()
    # 524/502/503 + 429 are transient
    for code in (524, 502, 503, 429, 500):
        e = urllib.error.HTTPError("u", code, "x", {}, None)
        assert mod._is_transient(e), f"HTTP {code} should be transient"
    # 400/401/403/404 are NOT transient
    for code in (400, 401, 403, 404):
        e = urllib.error.HTTPError("u", code, "x", {}, None)
        assert not mod._is_transient(e), f"HTTP {code} should NOT be transient"
    # URLError (connection) and timeout are transient
    assert mod._is_transient(urllib.error.URLError("connection refused"))
    assert mod._is_transient(TimeoutError("timed out"))


def test_call_llm_retries_transient_then_succeeds(monkeypatch):
    """call_llm must retry a transient 524 and succeed on a later attempt
    without raising."""
    mod = _load_module()
    monkeypatch.setattr(mod, "API_KEY", "test-key")
    monkeypatch.setattr(mod, "MODELS", ["m1"])
    monkeypatch.setattr(mod, "_RETRY_BACKOFF_SECONDS", [0, 0, 0])  # no real sleeping

    calls = {"n": 0}

    def fake_chat_completion(**_kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("timeout")
        return "# OK"

    monkeypatch.setattr(mod, "cliproxy_chat_completion", fake_chat_completion)
    out = mod.call_llm("sys", "user")
    assert out == "# OK", out
    assert calls["n"] == 3, f"expected 3 attempts (2 retries), got {calls['n']}"
