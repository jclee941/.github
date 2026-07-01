from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Protocol, TypeGuard

from pytest import MonkeyPatch

REPO_ROOT = Path(__file__).resolve().parents[2]
CLEANING_SCRIPT = REPO_ROOT / "scripts" / "generate_readme_cleaning.py"


class CleaningModule(Protocol):
    _REPO_ROOT: Path

    def normalize_llm_readme_response(self, text: str) -> str: ...

    def sanitize_links(self, text: str) -> str: ...

    def known_jclee_repos(self) -> set[str]: ...


def _load_cleaning_module() -> CleaningModule:
    spec = importlib.util.spec_from_file_location("generate_readme_cleaning", CLEANING_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    assert _is_cleaning_module(mod)
    return mod


def _is_cleaning_module(mod: ModuleType) -> TypeGuard[CleaningModule]:
    return (
        hasattr(mod, "normalize_llm_readme_response")
        and hasattr(mod, "sanitize_links")
        and hasattr(mod, "known_jclee_repos")
        and hasattr(mod, "_REPO_ROOT")
    )


def _use_inventory(
    mod: CleaningModule, tmp_path: Path, monkeypatch: MonkeyPatch, *entries: str
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    _ = (config_dir / "repos.yaml").write_text("\n".join(("repositories:", *entries, "")), encoding="utf-8")
    monkeypatch.setattr(mod, "_REPO_ROOT", tmp_path)


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


def test_normalize_repairs_known_stale_resume_branding():
    mod = _load_cleaning_module()
    raw = (
        "# 레쥬메 모노레포 / Resume Portfolio Monorepo\n\n"
        "> Resume portfolio monorepo: Cloudflare Worker edge site, job automation.\n\n"
        "이 저장소는 개인 포트폴리오 사이트와 운영 대시보드를 하나의 "
        "npm 워크스페이스 모노레포로 통합한 사설 저장소입니다.\n\n"
        "This repository is a private npm workspaces monorepo that unifies a "
        "personal portfolio site and operations dashboard.\n\n"
        "`package.json`의 `description` 필드는 이 모노레포를 다음과 같이 정의합니다.\n\n"
        "- **npm 워크스페이스 모노레포** — `apps/*`와 `packages/*`를 통합 빌드합니다.\n"
        "- **npm workspaces monorepo** — Unifies `apps/*` and `packages/*`.\n"
    )

    out = mod.normalize_llm_readme_response(raw)

    assert "레쥬메 모노레포" not in out
    assert "Resume Portfolio Monorepo" not in out
    assert "Resume portfolio monorepo" not in out
    assert "npm 워크스페이스 모노레포" not in out
    assert "npm workspaces monorepo" not in out
    assert "이 모노레포" not in out
    assert out.startswith("# 포트폴리오 자동화 워크스페이스 / Portfolio Automation Workspace")
    assert "Portfolio automation workspace: Cloudflare Worker edge site" in out
    assert "npm 워크스페이스 빌드" in out
    assert "npm workspaces build" in out


def test_normalize_repairs_resume_monorepo_branding_variants():
    mod = _load_cleaning_module()
    raw = (
        "# Resume-site monorepo\n\n"
        "> résumé portfolio monorepo for Cloudflare Worker delivery.\n\n"
        "## 개요\n\n"
        "레쥬메 포트폴리오 모노레포라는 오래된 이름이 남아 있었습니다.\n\n"
        "- npm workspace monorepo layout\n"
    )

    out = mod.normalize_llm_readme_response(raw)

    assert "Resume-site monorepo" not in out
    assert "résumé portfolio monorepo" not in out
    assert "레쥬메 포트폴리오 모노레포" not in out
    assert "npm workspace monorepo" not in out
    assert out.startswith("# Portfolio Automation Workspace")
    assert "> Portfolio Automation Workspace for Cloudflare Worker delivery." in out
    assert "포트폴리오 자동화 워크스페이스라는 오래된 이름" in out
    assert "- npm workspaces build layout" in out


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


def test_sanitize_links_rewrites_known_jclee_main_branch_paths_to_master(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    mod = _load_cleaning_module()
    _use_inventory(mod, tmp_path, monkeypatch, "  - visibility: public", "    name: account")
    out = mod.sanitize_links(
        "Docs https://github.com/jclee941/account/blob/main/README.md "
        "Bot https://github.com/jclee941/jclee-bot/blob/main/scripts/generate_readme.py"
    )

    assert "https://github.com/jclee941/account/blob/master/README.md" in out, out
    assert "https://github.com/jclee941/jclee-bot/blob/master/scripts/generate_readme.py" in out, out
    assert "/blob/main/" not in out, out


def test_sanitize_links_rewrites_tree_main_paths_with_http_www_variants(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    mod = _load_cleaning_module()
    _use_inventory(mod, tmp_path, monkeypatch, "  - visibility: public", "    name: account")
    out = mod.sanitize_links(
        "[docs](http://github.com/jclee941/account/tree/main/docs) "
        "[scripts](https://www.github.com/jclee941/jclee-bot/tree/main/scripts) "
        "[root](https://github.com/jclee941/account/tree/main?tab=readme-ov-file) "
        "[raw](https://www.github.com/jclee941/jclee-bot/blob/main?raw=1) "
        "[section](https://github.com/jclee941/account/blob/main#readme)"
    )

    assert "https://github.com/jclee941/account/tree/master/docs" in out, out
    assert "https://github.com/jclee941/jclee-bot/tree/master/scripts" in out, out
    assert "https://github.com/jclee941/account/tree/master?tab=readme-ov-file" in out, out
    assert "https://github.com/jclee941/jclee-bot/blob/master?raw=1" in out, out
    assert "https://github.com/jclee941/account/blob/master#readme" in out, out
    assert "http://github.com" not in out, out
    assert "www.github.com" not in out, out
    assert "/tree/main" not in out, out
    assert "/blob/main" not in out, out


def test_sanitize_links_canonicalizes_unknown_repo_paths_to_repo_root():
    mod = _load_cleaning_module()
    md = (
        "bad https://github.com/jclee941/no-such-repo/settings/secrets/actions "
        "doc https://github.com/jclee941/no-such-repo/blob/master/README.md"
    )
    out = mod.sanitize_links(md)
    assert "settings/secrets/actions" not in out, out
    assert "blob/master/README.md" not in out, out
    assert out.count("https://github.com/jclee941/jclee-bot") == 2


def test_known_repos_excludes_private_inventory_entries(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    mod = _load_cleaning_module()
    _use_inventory(
        mod, tmp_path, monkeypatch,
        "  - visibility: public",
        "    name: account",
        "  - visibility: private",
        "    name: hycu",
    )

    assert mod.known_jclee_repos() == {"jclee-bot", "account"}


def test_known_repos_parses_inventory_variation(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    mod = _load_cleaning_module()
    _use_inventory(
        mod, tmp_path, monkeypatch,
        "  - visibility: public",
        "    name: account",
        "  - visibility: public",
        "    name: jclee-bot",
        "    automation:",
        "      branch_protection: true",
        "  - visibility: public",
        "    name: propose",
    )

    assert mod.known_jclee_repos() == {"jclee-bot", "account", "propose"}


def test_normalize_strips_thinking_variant():
    mod = _load_cleaning_module()
    raw = "<thinking>\nplan\n</thinking>\n\n# Title\n\nbody"
    out = mod.normalize_llm_readme_response(raw)
    assert "<thinking>" not in out and "plan" not in out, out
    assert out.lstrip().startswith("# Title"), out
