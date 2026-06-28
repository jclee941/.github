from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLEANING_SCRIPT = REPO_ROOT / "scripts" / "generate_readme_cleaning.py"


def _load_cleaning_module():
    spec = importlib.util.spec_from_file_location("generate_readme_cleaning", CLEANING_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sanitize_links_strips_nonexistent_jclee_repos():
    mod = _load_cleaning_module()
    md = (
        "See [CLIProxyAPI](https://github.com/jclee941/CLIProxyAPI) and "
        "[badge](https://github.com/jclee941/github-bot) plus the real "
        "[upstream](https://github.com/qodo-ai/pr-agent) and [self](https://github.com/jclee941/jclee-bot)."
    )
    out = mod.sanitize_links(md)
    assert "github.com/jclee941/CLIProxyAPI" not in out, out
    assert "github.com/jclee941/github-bot" not in out, out
    assert "github.com/qodo-ai/pr-agent" in out, out
    assert "github.com/jclee941/jclee-bot" in out, out

    badge = "[![v](https://img.shields.io/badge/x.svg)](https://github.com/jclee941/github-bot)"
    bout = mod.sanitize_links(badge)
    assert "jclee941/github-bot" not in bout, bout
    assert "img.shields.io" in bout, "badge image/label must be preserved"


def test_normalize_strips_think_block():
    mod = _load_cleaning_module()
    raw = "<think>\nI will write a readme.\n</think>\n\n# Real Title\n\nbody"
    out = mod.normalize_llm_readme_response(raw)
    assert "<think>" not in out and "will write a readme" not in out, out
    assert out.lstrip().startswith("# Real Title"), out


def test_normalize_unwraps_json_content():
    mod = _load_cleaning_module()
    raw = '```json\n{\n  "content": "# Title\\n\\nHello **world**\\n"\n}\n```'
    out = mod.normalize_llm_readme_response(raw)
    assert out.lstrip().startswith("# Title"), out
    assert "Hello **world**" in out, out
    assert '"content"' not in out and "```json" not in out, out


def test_normalize_think_then_json():
    mod = _load_cleaning_module()
    raw = '<think>\nreasoning\n</think>\n\n```json\n{"content": "# T\\n\\nbody\\n"}\n```'
    out = mod.normalize_llm_readme_response(raw)
    assert out.lstrip().startswith("# T"), out
    assert "<think>" not in out and "```json" not in out and "reasoning" not in out, out


def test_normalize_unwraps_truncated_json():
    mod = _load_cleaning_module()
    raw = '```json\n{\n  "content": "# Title\\n\\nbody line that got cut off mid'
    out = mod.normalize_llm_readme_response(raw)
    assert out.lstrip().startswith("# Title"), out
    assert '"content"' not in out and "```json" not in out, out


def test_normalize_truncated_json_with_invalid_unicode_escape():
    mod = _load_cleaning_module()
    raw = '```json\n{\n  "content": "# Title\\n\\npath C:\\\\Users and a cut \\u00'
    out = mod.normalize_llm_readme_response(raw)
    assert isinstance(out, str)
    assert out.lstrip().startswith("# Title"), out


def test_normalize_passthrough_plain_markdown():
    mod = _load_cleaning_module()
    raw = "# Title\n\nplain body\n"
    out = mod.normalize_llm_readme_response(raw)
    assert out.strip() == raw.strip(), out


def test_normalize_fixes_empty_badge_links():
    mod = _load_cleaning_module()
    raw = "# T\n\n[![Version](https://img.shields.io/badge/v.svg)](#)\n\nbody\n"
    out = mod.normalize_llm_readme_response(raw)
    assert "](#)" not in out, out
    assert "img.shields.io/badge/v.svg" in out, out


def test_normalize_strips_generator_meta_note():
    mod = _load_cleaning_module()
    raw = (
        "# Hycu\n\n"
        "Actual product overview.\n\n"
        "Note: I noticed the existing README was truncated mid-sentence. "
        "I removed any stale jclee-bot / automation-policy boilerplate.\n\n"
        "## Usage\n\nRun the tool.\n"
    )
    out = mod.normalize_llm_readme_response(raw)
    assert "Actual product overview" in out
    assert "## Usage" in out
    assert "I noticed" not in out
    assert "jclee-bot" not in out
    assert "automation-policy boilerplate" not in out


def test_normalize_strips_wrapped_generator_meta_note():
    mod = _load_cleaning_module()
    raw = (
        "# Hycu\n\n"
        "Actual product overview.\n\n"
        "Note: I noticed the existing README had stale generator context.\n"
        "I removed stale jclee-bot / automation-policy boilerplate before regenerating.\n\n"
        "## Usage\n\nRun the tool.\n"
    )
    out = mod.normalize_llm_readme_response(raw)
    assert "Actual product overview" in out
    assert "## Usage" in out
    assert "I noticed" not in out
    assert "jclee-bot" not in out
    assert "automation-policy boilerplate" not in out


def test_sanitize_links_handles_http_and_www():
    mod = _load_cleaning_module()
    md = (
        "[a](http://github.com/jclee941/github-bot) "
        "[b](https://www.github.com/jclee941/CLIProxyAPI) "
        "[ok](https://github.com/jclee941/jclee-bot)"
    )
    out = mod.sanitize_links(md)
    assert "jclee941/github-bot" not in out, out
    assert "jclee941/CLIProxyAPI" not in out, out
    assert "jclee941/jclee-bot" in out, out


def test_sanitize_links_canonicalizes_unknown_repo_paths_to_repo_root():
    mod = _load_cleaning_module()
    md = (
        "bad https://github.com/jclee941/no-such-repo/settings/secrets/actions "
        "doc https://github.com/jclee941/no-such-repo/blob/main/README.md"
    )
    out = mod.sanitize_links(md)
    assert "settings/secrets/actions" not in out, out
    assert "blob/main/README.md" not in out, out
    assert out.count("https://github.com/jclee941/jclee-bot") == 2


def test_known_repos_excludes_private_inventory_entries(tmp_path, monkeypatch):
    mod = _load_cleaning_module()
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "repos.yaml").write_text(
        "\n"
        "repositories:\n"
        "  - visibility: public\n"
        "    name: account\n"
        "  - visibility: private\n"
        "    name: hycu\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "_REPO_ROOT", tmp_path)
    assert mod._known_jclee_repos() == {"jclee-bot", "account"}


def test_known_repos_parses_inventory_variation(tmp_path, monkeypatch):
    mod = _load_cleaning_module()
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "repos.yaml").write_text(
        "\n"
        "repositories:\n"
        "  - visibility: public\n"
        "    name: account\n"
        "  - visibility: public\n"
        "    name: jclee-bot\n"
        "    automation:\n"
        "      branch_protection: true\n"
        "  - visibility: public\n"
        "    name: propose\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "_REPO_ROOT", tmp_path)
    assert mod._known_jclee_repos() == {"jclee-bot", "account", "propose"}


def test_normalize_strips_thinking_variant():
    mod = _load_cleaning_module()
    raw = "<thinking>\nplan\n</thinking>\n\n# Title\n\nbody"
    out = mod.normalize_llm_readme_response(raw)
    assert "<thinking>" not in out and "plan" not in out, out
    assert out.lstrip().startswith("# Title"), out
