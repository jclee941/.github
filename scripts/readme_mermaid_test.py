#!/usr/bin/env python3
"""readme_mermaid_test.py — guard architecture diagram rendering policy.

Why this exists
---------------
GitHub renders ```mermaid fenced blocks as diagrams, but a parser regression or
unsupported syntax can make a README show the flowchart source instead of a
diagram. README.md is the high-signal landing surface, so it must summarize the
architecture without exposing a Mermaid fenced block. Detailed docs may still
use GitHub-native Mermaid diagrams.

Mermaid renders ``<`` / ``>`` literally only when the label is a quoted string
(``["..."]``) — typically HTML-escaped as ``&lt;`` / ``&gt;``. This test keeps
detailed docs renderable by requiring every node label inside a Mermaid block
to be free of bare angle brackets.

A full Mermaid parse needs a browser/DOMPurify which is unavailable in this
offline CI, so we assert the exact, well-understood failure condition instead.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
README: Final = REPO_ROOT / "README.md"
PROMPTS: Final = REPO_ROOT / "scripts" / "generate_readme_prompts.py"
DOCS: Final = sorted((REPO_ROOT / "docs").glob("**/*.md"))
ARCHITECTURE_DOCS: Final = [README, *DOCS]

# Matches a flowchart node-label payload: NodeId[ ... ] / NodeId( ... ) etc.
# We only care about the text between the brackets that follows an identifier.
_LABEL: Final = re.compile(r"[A-Za-z0-9_]+[\[\(\{]+(.*?)[\]\)\}]+", re.DOTALL)


def extract_mermaid_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    lines = text.splitlines()
    inside = False
    buf: list[str] = []
    for line in lines:
        if line.strip() == "```mermaid":
            inside, buf = True, []
            continue
        if inside and line.strip() == "```":
            blocks.append("\n".join(buf))
            inside = False
            continue
        if inside:
            buf.append(line)
    return blocks


def architecture_fence_languages(path: Path) -> list[str]:
    languages: list[str] = []
    inside_architecture = False
    inside_fence = False

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not inside_fence and stripped.startswith("#"):
            normalized = stripped.casefold()
            inside_architecture = "architecture" in normalized or "아키텍처" in normalized
            continue
        if inside_architecture and stripped.startswith("```"):
            if not inside_fence:
                languages.append(stripped.removeprefix("```").strip())
            inside_fence = not inside_fence

    return languages


def bare_angle_labels(block: str) -> list[str]:
    """Return node labels that contain an unescaped/bare angle bracket."""
    offenders: list[str] = []
    for line in block.splitlines():
        # subgraph headers use quoted labels and are fine; skip control lines.
        for m in _LABEL.finditer(line):
            label = m.group(1)
            # A properly quoted label may legitimately contain &lt;/&gt; — those
            # are fine. Only a RAW '<' or '>' breaks the parser.
            if "<" in label or ">" in label:
                # Allow <br/> which Mermaid supports inside quoted labels.
                stripped = label.replace("<br/>", "").replace("<br>", "")
                if "<" in stripped or ">" in stripped:
                    offenders.append(label.strip())
    return offenders


def subgraphs_without_vertical_direction(block: str) -> list[str]:
    offenders: list[str] = []
    lines = block.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("subgraph "):
            continue
        next_line = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if next_line != "direction TB":
            offenders.append(stripped)
    return offenders


def test_readme_does_not_expose_mermaid_architecture_block():
    blocks = extract_mermaid_blocks(README.read_text(encoding="utf-8"))
    assert not blocks, "README.md must summarize architecture without a ```mermaid fenced block"


def test_readme_generator_does_not_request_readme_mermaid():
    text = PROMPTS.read_text(encoding="utf-8")
    assert "For the README architecture section" in text
    assert "compact Markdown tables" in text
    assert "request-flow steps" in text
    assert "remain readable even when diagram rendering is unavailable" in text
    assert "flowchart inside a ```mermaid fenced block" not in text


def test_no_bare_angle_brackets_in_mermaid_labels():
    all_offenders: list[str] = []
    for path in DOCS:
        for block in extract_mermaid_blocks(path.read_text(encoding="utf-8")):
            all_offenders.extend(bare_angle_labels(block))
    assert not all_offenders, (
        "Mermaid node labels contain bare angle brackets that break GitHub "
        "rendering (shown as raw code). Quote the label and HTML-escape the "
        f"brackets (&lt; &gt;): {all_offenders}"
    )


def test_mermaid_subgraphs_render_as_vertical_stacks():
    all_offenders: list[str] = []
    for path in DOCS:
        for block in extract_mermaid_blocks(path.read_text(encoding="utf-8")):
            all_offenders.extend(subgraphs_without_vertical_direction(block))
    assert not all_offenders, f"Mermaid subgraphs must use direction TB to avoid row layout: {all_offenders}"


def test_architecture_sections_do_not_use_raw_code_blocks():
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in ARCHITECTURE_DOCS
        if "" in architecture_fence_languages(path)
    ]
    assert not offenders, (
        "Architecture sections must render as GitHub-native diagrams instead "
        f"of raw fenced code blocks: {offenders}"
    )
