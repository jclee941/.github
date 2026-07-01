from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Protocol, TypeGuard

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_SCRIPT = REPO_ROOT / "scripts" / "generate_readme_prompts.py"


class ReadmePromptsModule(Protocol):
    def automation_source_system_prompt(self) -> str: ...

    def product_readme_system_prompt(self) -> str: ...


def _load_prompts_module() -> ReadmePromptsModule:
    spec = importlib.util.spec_from_file_location("generate_readme_prompts", PROMPTS_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    assert _is_prompts_module(mod)
    return mod


def _is_prompts_module(mod: ModuleType) -> TypeGuard[ReadmePromptsModule]:
    return hasattr(mod, "automation_source_system_prompt") and hasattr(mod, "product_readme_system_prompt")


def _all_prompts() -> tuple[str, str]:
    mod = _load_prompts_module()
    return mod.automation_source_system_prompt(), mod.product_readme_system_prompt()


def test_prompts_generate_korean_first_visual_landing_section() -> None:
    for prompt in _all_prompts():
        assert "Korean-first output" in prompt
        assert "Korean summary first" in prompt
        assert "English as secondary text" in prompt
        assert "first viewport" in prompt
        assert "short Korean summary" in prompt
        assert "quick-glance status table" in prompt
        assert "compact flow summary" in prompt
        assert "CJK line breaks natural" in prompt


def test_prompts_generate_google_style_readme_outline() -> None:
    expected_sections = (
        "Purpose / Package Contents",
        "Status",
        "First Files to Read",
        "API or Entry Points",
        "Quickstart / Usage",
        "Maintainers / Points of Contact",
        "Further Documentation",
    )
    for prompt in _all_prompts():
        assert "Google-style README Template" in prompt
        assert all(section in prompt for section in expected_sections)
        assert "what the project does" in prompt
        assert "whether it is deprecated or production-ready" in prompt
        assert "where to get help" in prompt


def test_product_prompt_keeps_visual_upgrade_without_bot_boilerplate() -> None:
    product_prompt = _load_prompts_module().product_readme_system_prompt()

    assert "quick-glance status table" in product_prompt
    assert "Do NOT add jclee-bot automation surfaces" in product_prompt
    assert "unless this repository's own source code implements that as the product" in product_prompt
