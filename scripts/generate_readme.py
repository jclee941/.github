#!/usr/bin/env python3
"""generate_readme.py — Automated README.md generator using CLIProxyAPI.

Scans repository structure, reads key configuration files, and generates
a comprehensive README.md via the homelab LLM backend.

Usage:
    python scripts/generate_readme.py [--dry-run]

Environment:
    MINIMAX_API_KEY  — API key for the direct MiniMax API (required)
    OPENAI_BASE_URL  — MiniMax endpoint (default: https://api.minimax.io/v1)
"""
from __future__ import annotations

import argparse
import codecs
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = os.environ.get("OPENAI_BASE_URL", "https://api.minimax.io/v1")
API_KEY = os.environ.get("MINIMAX_API_KEY", "") or os.environ.get("CLIPROXY_API_KEY", "")
MODELS = ["MiniMax-M3"]
MAX_TOKENS = 16000  # README is long; 4000 truncated the JSON mid-string

# Backoff (seconds) between retry attempts for a single model on transient
# backend errors (Cloudflare 524, 502/503, 429, connection/timeouts). The
# length of this list determines the number of EXTRA attempts per model.
_RETRY_BACKOFF_SECONDS = [2, 5, 10]
# HTTP status codes that indicate a transient backend condition worth retrying.
_TRANSIENT_HTTP_CODES = {429, 500, 502, 503, 504, 520, 522, 524}


class TransientLLMError(RuntimeError):
    """Raised when every model+retry hit a transient backend failure. The
    caller can catch this to degrade gracefully (skip the README update)
    instead of hard-failing CI on a temporary LLM outage."""


def _is_transient(error: Exception) -> bool:
    """Classify whether an exception from the LLM call is transient/retryable."""
    if isinstance(error, urllib.error.HTTPError):
        return error.code in _TRANSIENT_HTTP_CODES
    if isinstance(error, (urllib.error.URLError, TimeoutError, ConnectionError)):
        return True
    # Socket timeouts surface as OSError on some Python builds.
    if isinstance(error, OSError):
        return True
    return False

# Repos that actually exist under github.com/jclee941. Links to any OTHER
# jclee941 repo are LLM hallucinations (e.g. jclee941/CLIProxyAPI,
# jclee941/github-bot) that 404 and fail the docs-sync link-check.
_KNOWN_JCLEE_REPOS = {
    ".github", "account", "ai-dacon", "blacklist", "bug", "firewall",
    "hycu", "hycu_fsds", "idle-outpost", "jclee941", "learnprint",
    "opencode", "propose", "pr-agent", "resume", "safetywallet",
    "splunk", "terraform", "tmux", "youtube",
}


def normalize_llm_readme_response(text: str) -> str:
    """Strip LLM artifacts so only clean Markdown reaches README.md.

    Models (kimi/minimax/gpt via CLIProxyAPI) sometimes emit a <think>...</think>
    reasoning block and/or wrap the whole README in a fenced JSON object
    {"content": "..."} (which truncates mid-string at max_tokens). Without this,
    README.md is published with leaked reasoning and an escaped JSON string
    instead of real Markdown."""
    if not text:
        return text
    s = text
    # 1. Remove <think>/<thinking> reasoning blocks.
    s = re.sub(r"<(think|thinking)\b[^>]*>.*?</\1>", "", s, flags=re.DOTALL | re.IGNORECASE)
    s = s.strip()
    # 2. Strip an opening code fence (```json / ```markdown). Handle BOTH closed
    #    fences and unclosed ones (truncated output that hit max_tokens).
    s = re.sub(r"^```[a-zA-Z0-9]*\s*\n", "", s)
    s = re.sub(r"\n```\s*$", "", s).strip()
    # 3. If the body is (or starts as) a JSON object with a string 'content'
    #    field, unwrap it. Covers complete and truncated JSON.
    if s.startswith("{") and '"content"' in s:
        try:
            obj = json.loads(s)
            if isinstance(obj, dict) and isinstance(obj.get("content"), str):
                s = obj["content"].strip()
        except (json.JSONDecodeError, ValueError):
            # Truncated/incomplete JSON (response hit max_tokens mid-string).
            mcontent = re.search(r'"content"\s*:\s*"', s)
            if mcontent:
                body = s[mcontent.end():]
                body = re.sub(r'"\s*\}\s*$', "", body)
                try:
                    s = json.loads('"' + body + '"')
                except (json.JSONDecodeError, ValueError):
                    # Truncated output may end mid backslash escape; drop
                    # undecodable tail bytes rather than crashing the run.
                    s = codecs.decode(body.encode(), "unicode_escape", errors="ignore")
                s = s.strip()
    # 4. Unwrap a trailing markdown fence if the content itself is fenced.
    fence2 = re.match(r"^```[a-zA-Z0-9]*\s*\n(.*)\n```\s*$", s, flags=re.DOTALL)
    if fence2:
        s = fence2.group(1).strip()
    # 5. Drop empty-link wrappers around badges: [![alt](img)](#) -> ![alt](img).
    #    The placeholder '(#)' fails markdownlint MD042 (no-empty-links).
    s = re.sub(r"\[(!\[[^\]]*\]\([^)]*\))\]\(#\)", r"\1", s)
    return s


def sanitize_links(text: str) -> str:
    """Rewrite links to non-existent github.com/jclee941/<repo> URLs (LLM
    hallucinations such as jclee941/CLIProxyAPI or jclee941/github-bot) to the
    canonical source repo so they no longer 404 in the docs-sync link-check.

    Operates on the bare URL, so it works for plain links, badges (nested
    brackets), and raw URLs alike. Real jclee941 repos and any non-jclee941
    link (e.g. qodo-ai/pr-agent) are left untouched."""
    canonical = "https://github.com/jclee941/.github"
    url_re = re.compile(r"https?://(?:www\.)?github\.com/jclee941/([A-Za-z0-9._-]+)")

    def _replace(m: re.Match) -> str:
        repo = m.group(1)
        if repo in _KNOWN_JCLEE_REPOS:
            return m.group(0)  # real repo, keep the URL
        return canonical  # hallucinated repo, rewrite to the canonical repo

    return url_re.sub(_replace, text)


def redact_private_ips(text: str) -> str:
    """Replace any RFC1918 private IP (with optional :port) in generated README
    text with placeholders, so internal homelab addresses never leak even if the
    LLM ignores the system prompt. Public IPs are left untouched."""
    ip_re = re.compile(r"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(:\d+)?\b")

    def _is_private(o1: int, o2: int, o3: int, o4: int) -> bool:
        if any(o > 255 for o in (o1, o2, o3, o4)):
            return False
        if o1 == 10:
            return True
        if o1 == 172 and 16 <= o2 <= 31:
            return True
        if o1 == 192 and o2 == 168:
            return True
        return False

    def _replace(m: re.Match) -> str:
        octets = tuple(int(m.group(i)) for i in range(1, 5))
        if not _is_private(*octets):
            return m.group(0)
        port = m.group(5) or ""
        return f"<homelab-host>{port}"

    return ip_re.sub(_replace, text)


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
    """Call CLIProxyAPI (OpenAI-compatible) with fallback models.

    Each model is attempted up to len(_RETRY_BACKOFF_SECONDS)+1 times, sleeping
    between attempts on transient backend errors (524/502/503/429/timeout/
    connection). If EVERY model+retry hit a transient error, raise
    TransientLLMError so the caller can degrade gracefully. A non-transient
    error (bad request, auth) still raises SystemExit immediately.
    """
    if not API_KEY:
        raise SystemExit("ERROR: MINIMAX_API_KEY environment variable is required.")

    last_error = None
    all_transient = True
    for model in MODELS:
        payload = {
            "model": model,
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
        # attempt 0 = initial try; subsequent attempts use the backoff list.
        for attempt in range(len(_RETRY_BACKOFF_SECONDS) + 1):
            try:
                with urllib.request.urlopen(req, timeout=300) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                print(f"Generated with model: {model}")
                return content
            except Exception as e:  # noqa: BLE001 - boundary; classified below
                last_error = e
                transient = _is_transient(e)
                all_transient = all_transient and transient
                print(f"Model {model} attempt {attempt + 1} failed: {e}")
                if transient and attempt < len(_RETRY_BACKOFF_SECONDS):
                    delay = _RETRY_BACKOFF_SECONDS[attempt]
                    print(f"  transient error; retrying in {delay}s")
                    time.sleep(delay)
                    continue
                # Non-transient, or retries exhausted for this model: move on
                # to the next model (if any).
                break

    if all_transient:
        raise TransientLLMError(
            f"All models failed with transient backend errors. Last error: {last_error}"
        )
    raise SystemExit(f"ERROR: All models failed. Last error: {last_error}")


def generate_readme(repo_root: Path) -> str:
    tree = run_tree(repo_root)
    files = read_key_files(repo_root)

    # Scan workflow files
    workflows_dir = repo_root / ".github" / "workflows"
    workflows = []
    if workflows_dir.exists():
        for wf in sorted(workflows_dir.glob("*.yml")):
            workflows.append(wf.name)
        for wf in sorted((workflows_dir / "security").glob("*.yml")):
            workflows.append(f"security/{wf.name}")

    # Scan Go automation tools
    scripts_dir = repo_root / "scripts" / "cmd"
    go_tools = []
    if scripts_dir.exists():
        for d in sorted(scripts_dir.iterdir()):
            if d.is_dir() and (d / "main.go").exists():
                go_tools.append(d.name)

    # Read AGENTS.md for automation inventory
    agents_md = ""
    agents_path = repo_root / "AGENTS.md"
    if agents_path.exists():
        agents_md = agents_path.read_text(encoding="utf-8", errors="ignore")[:4000]

    system = (
        "You are a technical writer bot specialized in GitHub automation documentation. "
        "Generate a comprehensive, professional README.md in Korean and English (bilingual). "
        "Use Markdown. Structure: title, badges, overview, features, architecture, "
        "automation inventory (workflows + tools), quick start, local development, "
        "commands reference, and contribution guide. "
        "Be specific about what automation exists - list workflow names and tool names. "
        "When listing workflow files, use their REAL on-disk names including the numeric "
        "prefix (e.g. 10_pr-review.yml, 03_pr-checks.yml, 90_sanity.yml); never strip the "
        "prefix and never invent bare names. "
        "For the architecture section, draw the diagram as a GitHub-native Mermaid "
        "flowchart inside a ```mermaid fenced block. Do NOT hand-draw ASCII/box-drawing "
        "diagrams (┌ │ └ etc.) - they render misaligned. "
        "CRITICAL Mermaid rule: any node label containing angle brackets (e.g. the "
        "<homelab-host> / <homelab-elk> placeholders or a URL) MUST be a quoted "
        "string with the brackets HTML-escaped, e.g. CLIProxy[\"&lt;homelab-host&gt;:8317<br/>...\"]; "
        "a bare '<' in a label makes GitHub render the whole block as raw code. "
        "Inside quoted labels only <br/> line breaks are allowed unescaped. "
        "For the repository structure tree, reflect the ACTUAL top-level layout provided "
        "below; never invent directories such as _bot-scripts/ (that name only ever appears "
        "as a transient CI checkout path, not a real directory). "
        "NEVER include hardcoded private/internal IP addresses (RFC1918: 192.168.x.x, "
        "10.x.x.x, 172.16-31.x.x) or LXC container numbers; use placeholders like "
        "<homelab-host> / <homelab-elk> and the public endpoint https://cliproxy.jclee.me/v1 instead. "
        "Do NOT use bold/emphasis text as a substitute for a heading (markdownlint MD036); "
        "use real '#' headings. "
        "Current README-gen model: minimax-m2.7 (via CLIProxyAPI). "
        "Do NOT invent GitHub repository URLs: never link to non-existent repos such as "
        "github.com/jclee941/CLIProxyAPI or github.com/jclee941/github-bot. For external "
        "links use only qodo-ai/pr-agent, cliproxy.jclee.me, and bot.jclee.me. "
    )

    user_parts = [
        "Generate a comprehensive README.md for the following repository.",
        "",
        "=== PROJECT STRUCTURE ===",
        tree,
        "",
        "=== WORKFLOW FILES (", str(len(workflows)), " total) ===",
        "\n".join(workflows),
        "",
        "=== GO AUTOMATION TOOLS (", str(len(go_tools)), " total) ===",
        "\n".join(go_tools),
        "",
    ]

    for name, content in files.items():
        user_parts.append(f"=== {name} ===")
        user_parts.append(content)
        user_parts.append("")

    if agents_md:
        user_parts.append("=== AUTOMATION INVENTORY (AGENTS.md) ===")
        user_parts.append(agents_md)
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
    try:
        content = redact_private_ips(sanitize_links(normalize_llm_readme_response(generate_readme(repo_root))))
    except TransientLLMError as e:
        # Transient backend outage (e.g. Cloudflare 524): do NOT hard-fail CI.
        # Leave the existing README untouched; the next scheduled run regenerates.
        print(f"::warning::README generation skipped due to transient LLM outage: {e}")
        return 0

    if args.dry_run:
        print("\n--- GENERATED README ---\n")
        print(content)
        return 0

    readme_path.write_text(content, encoding="utf-8")
    print(f"Wrote {readme_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
