from __future__ import annotations

import runpy
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class MarkdownModule(types.ModuleType):
    def markdown(self, text: str, extensions: list[str]) -> str:
        _ = extensions
        return text


def test_elk_evidence_demo_page_builds_into_pages_site() -> None:
    # Given: GitHub Pages is built from docs markdown.
    sys.modules["markdown"] = MarkdownModule("markdown")
    site_page = REPO_ROOT / "_site" / "elk-evidence-demo.html"

    # When: the static Pages build runs.
    _ = runpy.run_path(str(REPO_ROOT / ".github" / "scripts" / "build_pages.py"), run_name="__main__")

    # Then: the ELK evidence demo page is published with a safe native-health demo surface.
    html = site_page.read_text(encoding="utf-8")
    assert "ELK Evidence Demo" in html
    assert "https://bot.jclee.me/api/v1/native_health" in html
    assert "readonly" in html
    assert "allowedNativeHealthEndpoints" in html
    assert "Blocked unsafe endpoint" in html
    assert "NATIVE_HEALTH_TOKEN" in html
    assert "checks: [\"elk_health\"]" in html
    assert "<homelab-elk>" in html
    assert "ELK_PASSWORD" not in html
