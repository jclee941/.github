#!/usr/bin/env python3
"""Build a static HTML site from docs/ for GitHub Pages.

Converts every docs/*.md (plus README.md) into <name>.html, preserving
```mermaid``` fenced blocks as <div class="mermaid"> so Mermaid.js renders them
client-side, and emits an index.html linking all documents. Managed by jclee-bot.
"""

from __future__ import annotations

import html
import pathlib
import re
import shutil

import markdown

ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
SITE = ROOT / "_site"

MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ max-width: 980px; margin: 2rem auto; padding: 0 1rem;
         font-family: -apple-system, Segoe UI, Roboto, sans-serif; line-height: 1.6; color: #24292f; }}
  pre {{ background: #f6f8fa; padding: 1rem; overflow:auto; border-radius: 6px; }}
  code {{ background: #f6f8fa; padding: 0.1em 0.3em; border-radius: 4px; }}
  table {{ border-collapse: collapse; }} td, th {{ border: 1px solid #d0d7de; padding: 6px 12px; }}
  .mermaid {{ background: #fff; }}
  a {{ color: #0969da; }} nav {{ margin-bottom: 1.5rem; }}
</style>
</head>
<body>
<nav><a href="index.html">&larr; Docs index</a></nav>
{body}
<script type="module">
import mermaid from "{cdn}";
mermaid.initialize({{ startOnLoad: true, theme: "default" }});
</script>
</body>
</html>
"""

MERMAID_BLOCK = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)


def render_markdown(text: str) -> str:
    """Extract mermaid fences first (so the md renderer does not escape them),
    convert the rest with python-markdown, then re-inject mermaid divs."""
    placeholders: list[str] = []

    def stash(m: re.Match[str]) -> str:
        placeholders.append(m.group(1))
        return f"@@MERMAID_{len(placeholders) - 1}@@"

    stripped = MERMAID_BLOCK.sub(stash, text)
    body = markdown.markdown(stripped, extensions=["fenced_code", "tables", "toc"])
    for i, diagram in enumerate(placeholders):
        div = f'<div class="mermaid">\n{html.escape(diagram)}</div>'
        body = body.replace(f"@@MERMAID_{i}@@", div)
        body = body.replace(f"<p>@@MERMAID_{i}@@</p>", div)
    return body


def first_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def main() -> None:
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)

    sources: list[pathlib.Path] = sorted(DOCS.glob("*.md"))
    readme = ROOT / "README.md"
    if readme.exists():
        sources.append(readme)

    # copy asset dirs verbatim
    for sub in ("assets", "review-templates"):
        src = DOCS / sub
        if src.is_dir():
            shutil.copytree(src, SITE / sub)

    entries: list[tuple[str, str]] = []  # (html_name, title)
    for md in sources:
        text = md.read_text(encoding="utf-8")
        name = md.stem if md.name != "README.md" else "readme"
        title = first_title(text, md.name)
        html_name = f"{name}.html"
        body = render_markdown(text)
        (SITE / html_name).write_text(
            PAGE_TEMPLATE.format(title=html.escape(title), body=body, cdn=MERMAID_CDN),
            encoding="utf-8",
        )
        entries.append((html_name, title))

    # index
    items = "\n".join(
        f'<li><a href="{h}">{html.escape(t)}</a></li>' for h, t in entries
    )
    index_body = (
        "<h1>jclee-bot Automation Docs | 자동화 문서</h1>\n"
        "<p><em>Auto-published by <code>41_pages-deploy.yml</code>. Managed by jclee-bot.</em></p>\n"
        f"<h2>Documents</h2>\n<ul>\n{items}\n</ul>"
    )
    (SITE / "index.html").write_text(
        PAGE_TEMPLATE.format(title="jclee-bot Automation Docs", body=index_body, cdn=MERMAID_CDN),
        encoding="utf-8",
    )
    print(f"built {len(entries) + 1} html pages into {SITE}")


if __name__ == "__main__":
    main()
