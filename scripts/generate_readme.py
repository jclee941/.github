#!/usr/bin/env python3
"""generate_readme.py — Automated README.md generator using CLIProxyAPI.

Scans repository structure, reads key configuration files, and generates
a comprehensive README.md via the homelab LLM backend.

Usage:
    python scripts/generate_readme.py [--dry-run]

Environment:
    CLIPROXY_API_KEY — API key for CLIProxyAPI (required)
    OPENAI_BASE_URL  — CLIProxyAPI endpoint (default: https://cliproxy.jclee.me/v1)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

API_BASE = os.environ.get("OPENAI_BASE_URL", "https://cliproxy.jclee.me/v1")
API_KEY = os.environ.get("CLIPROXY_API_KEY", "")
MODEL = "gpt-4.1-mini"
MAX_TOKENS = 4000


def run_tree(repo_root: Path) -> str:
    """Return a `tree`-like representation of the repo, excluding noise."""
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
    return "\n".join(lines[:100])  # cap size


def read_key_files(repo_root: Path) -> dict[str, str]:
    """Read important config / entry-point files for context."""
    candidates = [
        "package.json",
        "pyproject.toml",
        "setup.py",
        "go.mod",
        "Cargo.toml",
        "requirements.txt",
        "Makefile",
        "Dockerfile",
        "docker-compose.yml",
        "README.md",
    ]
    result: dict[str, str] = {}
    for name in candidates:
        path = repo_root / name
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="ignore")
            result[name] = text[:2000]  # cap each file
    return result


def call_llm(system: str, user: str) -> str:
    """Call CLIProxyAPI (OpenAI-compatible) and return the generated text."""
    if not API_KEY:
        raise SystemExit("ERROR: CLIPROXY_API_KEY environment variable is required.")

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": MAX_TOKENS,
        "temperature": 0.3,
    }
    req = urllib.request.Request(
        f"{API_BASE}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def generate_readme(repo_root: Path) -> str:
    tree = run_tree(repo_root)
    files = read_key_files(repo_root)

    system = (
        "You are a technical writer bot. Generate a clean, professional README.md in Korean. "
        "Use Markdown. Include: title, description, features, installation, usage, project structure, "
        "and contribution guide if applicable. Keep it concise but informative."
    )

    user_parts = [
        "Generate a README.md for the following repository.",
        "",
        "=== PROJECT STRUCTURE ===",
        tree,
        "",
    ]
    for name, content in files.items():
        user_parts.append(f"=== {name} ===")
        user_parts.append(content)
        user_parts.append("")

    user = "\n".join(user_parts)
    return call_llm(system, user)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate README.md via CLIProxyAPI")
    parser.add_argument("--dry-run", action="store_true", help="Print output instead of writing")
    parser.add_argument("--repo", type=Path, default=Path("."), help="Repository root")
    args = parser.parse_args()

    repo_root = args.repo.resolve()
    readme_path = repo_root / "README.md"

    print(f"Scanning {repo_root} ...")
    content = generate_readme(repo_root)

    if args.dry_run:
        print("\n--- GENERATED README ---\n")
        print(content)
        return 0

    readme_path.write_text(content, encoding="utf-8")
    print(f"Wrote {readme_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
