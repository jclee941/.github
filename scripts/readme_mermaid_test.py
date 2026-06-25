#!/usr/bin/env python3
"""readme_mermaid_test.py — guard the README architecture Mermaid diagram.

Why this exists
---------------
GitHub renders ```mermaid fenced blocks as diagrams. When a flowchart node
label contains a *bare* angle bracket (``[<homelab-host>...]`` or an
``<https://...>`` autolink), Mermaid's parser treats ``<`` as the start of an
HTML tag, fails, and GitHub silently falls back to showing the raw code instead
of the diagram. That regression shipped in README.md (the architecture diagram
rendered as code).

Mermaid renders ``<`` / ``>`` literally only when the label is a quoted string
(``["..."]``) — typically HTML-escaped as ``&lt;`` / ``&gt;``. This test pins
that invariant so the diagram can never silently regress to raw code: every
node label inside the ```mermaid block must be free of bare angle brackets.

A full Mermaid parse needs a browser/DOMPurify which is unavailable in this
offline CI, so we assert the exact, well-understood failure condition instead.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"

# Matches a flowchart node-label payload: NodeId[ ... ] / NodeId( ... ) etc.
# We only care about the text between the brackets that follows an identifier.
_LABEL = re.compile(r"[A-Za-z0-9_]+[\[\(\{]+(.*?)[\]\)\}]+", re.DOTALL)


def extract_mermaid_blocks(text: str) -> list[str]:
    blocks, lines, inside, buf = [], text.splitlines(), False, []
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


def bare_angle_labels(block: str) -> list[str]:
    """Return node labels that contain an unescaped/bare angle bracket."""
    offenders = []
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
    offenders = []
    lines = block.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("subgraph "):
            continue
        next_line = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if next_line != "direction TB":
            offenders.append(stripped)
    return offenders


def test_readme_has_mermaid_architecture_block():
    blocks = extract_mermaid_blocks(README.read_text(encoding="utf-8"))
    assert blocks, "README.md must contain a ```mermaid architecture diagram"


def test_no_bare_angle_brackets_in_mermaid_labels():
    blocks = extract_mermaid_blocks(README.read_text(encoding="utf-8"))
    all_offenders = []
    for block in blocks:
        all_offenders.extend(bare_angle_labels(block))
    assert not all_offenders, (
        "Mermaid node labels contain bare angle brackets that break GitHub "
        "rendering (shown as raw code). Quote the label and HTML-escape the "
        f"brackets (&lt; &gt;): {all_offenders}"
    )


def test_mermaid_subgraphs_render_as_vertical_stacks():
    blocks = extract_mermaid_blocks(README.read_text(encoding="utf-8"))
    all_offenders = []
    for block in blocks:
        all_offenders.extend(subgraphs_without_vertical_direction(block))
    assert not all_offenders, f"Mermaid subgraphs must use direction TB to avoid row layout: {all_offenders}"
