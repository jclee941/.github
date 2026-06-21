from __future__ import annotations

import os
from pathlib import Path


def run_tree(repo_root: Path) -> str:
    ignore = {".git", ".github", "node_modules", "venv", ".venv", "__pycache__", ".cache", "dist", "build"}
    lines = []
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in ignore and not d.startswith(".")]
        level = root.replace(str(repo_root), "").count(os.sep)
        indent = "  " * level
        rel = Path(root).relative_to(repo_root)
        lines.append(f"{indent}{rel.name}/")
        subindent = "  " * (level + 1)
        for f in sorted(files):
            if f.startswith(".") or f.endswith((".pyc", ".log")):
                continue
            lines.append(f"{subindent}{f}")
    return "\n".join(lines[:100])
