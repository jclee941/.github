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
PROMPTS_SCRIPT = REPO_ROOT / "scripts" / "generate_readme_prompts.py"
assert SCRIPT.exists(), f"generate_readme.py not found: {SCRIPT}"


def _load_module():
    """Import generate_readme.py as a module (no API key required)."""
    spec = importlib.util.spec_from_file_location("generate_readme", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_canonical_model_chain():
    """MODELS must try the requested minimax-m3 primary before fallback models."""
    mod = _load_module()
    assert mod.MODELS == ["minimax-m3", "gpt-5.5"], (
        f"generate_readme MODELS drifted from canonical model: {mod.MODELS}"
    )


def test_no_stale_model_text_in_prompt():
    """README-generator prompt must not hardcode the retired minimax fallback."""
    text = SCRIPT.read_text() + PROMPTS_SCRIPT.read_text()
    assert "minimax-m2.7" not in text, (
        "generate_readme.py must not hardcode minimax-m2.7; fallback is minimax-m3"
    )


def test_prompt_keeps_jclee_bot_as_automation_surface():
    text = PROMPTS_SCRIPT.read_text()
    assert "jclee-bot automation surfaces" in text
    assert "Do NOT render a GitHub workflow inventory table" in text
    assert "workflow files are implementation triggers" in text
    assert "jclee-bot에의해자동화됨" in text
    assert "list all real workflow files grouped by trigger type" not in text


def test_downstream_repo_prompt_includes_agents_md_without_readme_boilerplate(monkeypatch, tmp_path):
    mod = _load_module()
    captured: dict[str, str] = {}

    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: CI\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(
        "Project instructions: document the CLI entry point and npm test command.\n",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text('{"name":"demo-tool"}\n', encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "# demo\n\n## jclee-bot Automation\n\nREADME Generation via gpt-5.5.\n",
        encoding="utf-8",
    )

    def fake_call_llm(system: str, user: str) -> str:
        captured["system"] = system
        captured["user"] = user
        return "# demo-tool\n"

    monkeypatch.setattr(mod, "run_tree", lambda _repo_root: ".\n├── package.json\n└── README.md")
    monkeypatch.setattr(mod, "call_llm", fake_call_llm)

    assert mod.generate_readme(tmp_path) == "# demo-tool\n"

    assert "Document the repository's actual product" in captured["system"]
    assert "Do NOT add jclee-bot automation surfaces" in captured["system"]
    assert "stale boilerplate from a previous generator run" in captured["system"]
    assert "REPOSITORY INSTRUCTIONS (AGENTS.md)" in captured["user"]
    assert "document the CLI entry point and npm test command" in captured["user"]
    assert "AUTOMATION INVENTORY" not in captured["user"]
    assert "WORKFLOW FILES" not in captured["user"]
    assert "jclee-bot Automation" not in captured["user"]


def test_downstream_boilerplate_detector_keeps_product_readme_context():
    mod = _load_module()
    readme = (
        "# Product README Generator\n\n"
        "This CLI documents workflow files for users and supports README generation.\n"
        "It can call gpt-5.5 through a user-supplied provider key.\n"
    )

    assert not mod._looks_like_downstream_automation_boilerplate(readme)


def test_downstream_boilerplate_detector_flags_jclee_bot_context():
    mod = _load_module()
    readme = (
        "# Demo\n\n"
        "## jclee-bot Automation\n\n"
        "README Generation via gpt-5.5 and bot.jclee.me.\n"
    )

    assert mod._looks_like_downstream_automation_boilerplate(readme)


def test_downstream_boilerplate_detector_flags_control_plane_context():
    mod = _load_module()
    readme = (
        "# Tool\n\n"
        "README Generation via gpt-5.5 and minimax-m3. "
        "Workflow files are automation surfaces.\n"
    )

    assert mod._looks_like_downstream_automation_boilerplate(readme)


def test_source_repo_prompt_keeps_automation_contract(monkeypatch, tmp_path):
    mod = _load_module()
    captured: dict[str, str] = {}

    (tmp_path / "jclee_bot").mkdir()
    (tmp_path / "jclee_bot" / "review_engine").mkdir(parents=True)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "repos.yaml").write_text("repositories: []\n", encoding="utf-8")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "10_pr-review.yml").write_text(
        "name: PR Review\n",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("Automation inventory\n", encoding="utf-8")

    def fake_call_llm(system: str, user: str) -> str:
        captured["system"] = system
        captured["user"] = user
        return "# github-bot\n"

    monkeypatch.setattr(mod, "run_tree", lambda _repo_root: ".\n├── jclee_bot\n└── pr_agent")
    monkeypatch.setattr(mod, "call_llm", fake_call_llm)

    assert mod.generate_readme(tmp_path) == "# github-bot\n"

    assert "jclee-bot automation surfaces" in captured["system"]
    assert "jclee-bot에의해자동화됨" in captured["system"]
    assert "WORKFLOW FILES" in captured["user"]
    assert "10_pr-review.yml" in captured["user"]
    assert "AUTOMATION INVENTORY" in captured["user"]


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


def test_is_transient_error_classification():
    """Transient backend errors (524/502/503/timeout/connection) must be
    classified as retryable; genuine client errors (4xx other than 429) must
    not."""
    import urllib.error
    from email.message import Message

    mod = _load_module()
    # 524/502/503 + 429 are transient
    for code in (524, 502, 503, 429, 500):
        e = urllib.error.HTTPError("u", code, "x", Message(), None)
        assert mod._is_transient(e), f"HTTP {code} should be transient"
    # 400/401/403/404 are NOT transient
    for code in (400, 401, 403, 404):
        e = urllib.error.HTTPError("u", code, "x", Message(), None)
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
