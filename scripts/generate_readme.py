#!/usr/bin/env python3
"""generate_readme.py — Automated README.md generator using CLIProxyAPI.

Scans repository structure, reads key configuration files, and generates
a comprehensive README.md via the homelab LLM backend.

Usage:
    python scripts/generate_readme.py [--dry-run]

Environment:
    CLIPROXY_API_KEY — API key for CLIProxyAPI (required)
    CLIPROXY_API_KEY_OP_REF — optional 1Password secret ref used when key is unset
    OPENAI_BASE_URL  — CLIProxyAPI endpoint (default: https://cliproxy.jclee.me/v1)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from importlib import import_module
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
_cliproxy_client = import_module("cliproxy_client")
_cliproxy_routing = import_module("cliproxy_routing")
_readme_cleaning = import_module("generate_readme_cleaning")
_readme_prompts = import_module("generate_readme_prompts")
_readme_retry = import_module("generate_readme_retry")
_readme_scan = import_module("generate_readme_scan")

CliproxyCredentialError = _cliproxy_client.CliproxyCredentialError
CliproxyMessage = _cliproxy_client.CliproxyMessage
TransientLLMError = _readme_retry.TransientLLMError
cliproxy_chat_completion = _cliproxy_client.cliproxy_chat_completion
automation_source_system_prompt = _readme_prompts.automation_source_system_prompt
normalize_llm_readme_response = _readme_cleaning.normalize_llm_readme_response
product_readme_system_prompt = _readme_prompts.product_readme_system_prompt
redact_private_ips = _readme_cleaning.redact_private_ips
resolve_cliproxy_api_key = _cliproxy_client.resolve_cliproxy_api_key
route_models_by_quota = _cliproxy_routing.route_models_by_quota
run_tree = _readme_scan.run_tree
sanitize_links = _readme_cleaning.sanitize_links
_is_transient = _readme_retry.is_transient

API_BASE = os.environ.get("OPENAI_BASE_URL", "https://cliproxy.jclee.me/v1")
API_KEY = os.environ.get("CLIPROXY_API_KEY", "")
MODELS = ["gpt-5.5", "minimax-m3"]
MAX_TOKENS = 16000  # README is long; 4000 truncated the JSON mid-string

# Backoff (seconds) between retry attempts for a single model on transient
# backend errors (Cloudflare 524, 502/503, 429, connection/timeouts). The
# length of this list determines the number of EXTRA attempts per model.
_RETRY_BACKOFF_SECONDS = [2, 5, 10]


def _is_automation_source_repo(repo_root: Path) -> bool:
    return (
        (repo_root / "jclee_bot").is_dir()
        and (repo_root / "pr_agent").is_dir()
        and (repo_root / "config" / "repos.yaml").exists()
    )


def _looks_like_downstream_automation_boilerplate(text: str) -> bool:
    lower = text.lower()
    bot_owned_markers = (
        "jclee-bot",
        "bot.jclee.me",
        "qodo-ai/pr-agent",
        "cliproxy.jclee.me",
        "jclee-bot에의해자동화됨",
    )
    stale_policy_markers = (
        "workflow/event-adapter policy",
        "automation-policy boilerplate",
        "bot-owned pr metadata",
        "downstream health checks",
    )
    generator_control_plane_pairs = (
        ("readme generation", "automation surfaces"),
        ("readme 생성", "자동화 표면"),
        ("gpt-5.5", "minimax-m3"),
    )
    return any(marker in lower for marker in bot_owned_markers + stale_policy_markers) or any(
        first in lower and second in lower for first, second in generator_control_plane_pairs
    )


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
    try:
        api_key = API_KEY or resolve_cliproxy_api_key()
    except CliproxyCredentialError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc

    last_error = None
    all_transient = True
    messages = [
        CliproxyMessage(role="system", content=system),
        CliproxyMessage(role="user", content=user),
    ]
    for model in route_models_by_quota(MODELS):
        # attempt 0 = initial try; subsequent attempts use the backoff list.
        for attempt in range(len(_RETRY_BACKOFF_SECONDS) + 1):
            try:
                content = cliproxy_chat_completion(
                    model=model,
                    messages=messages,
                    api_key=api_key,
                    base_url=API_BASE,
                    max_tokens=MAX_TOKENS,
                    temperature=0.3,
                    timeout_seconds=300,
                )
                print(f"Generated with model: {model}")
                return content
            except Exception as exc:  # noqa: BLE001 - boundary; classified below
                last_error = exc
                transient = _is_transient(exc)
                all_transient = all_transient and transient
                print(f"Model {model} attempt {attempt + 1} failed: {exc}")
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


def _workflow_files(repo_root: Path) -> list[str]:
    workflows_dir = repo_root / ".github" / "workflows"
    workflows: list[str] = []
    if workflows_dir.exists():
        for wf in sorted(workflows_dir.glob("*.yml")):
            workflows.append(wf.name)
        for wf in sorted((workflows_dir / "security").glob("*.yml")):
            workflows.append(f"security/{wf.name}")
    return workflows


def _go_automation_tools(repo_root: Path) -> list[str]:
    scripts_dir = repo_root / "scripts" / "cmd"
    go_tools: list[str] = []
    if scripts_dir.exists():
        for d in sorted(scripts_dir.iterdir()):
            if d.is_dir() and (d / "main.go").exists():
                go_tools.append(d.name)
    return go_tools


def generate_readme(repo_root: Path) -> str:
    tree = run_tree(repo_root)
    files = read_key_files(repo_root)
    is_automation_source = _is_automation_source_repo(repo_root)
    if (
        not is_automation_source
        and "README.md" in files
        and _looks_like_downstream_automation_boilerplate(files["README.md"])
    ):
        del files["README.md"]
    system = (
        automation_source_system_prompt()
        if is_automation_source
        else product_readme_system_prompt()
    )

    user_parts = [
        "Generate a comprehensive README.md for the following repository.",
        "",
        "=== PROJECT STRUCTURE ===",
        tree,
        "",
    ]

    if is_automation_source:
        workflows = _workflow_files(repo_root)
        go_tools = _go_automation_tools(repo_root)
        user_parts.extend(
            [
                "=== WORKFLOW FILES (",
                str(len(workflows)),
                " total) ===",
                "\n".join(workflows),
                "",
                "=== GO AUTOMATION TOOLS (",
                str(len(go_tools)),
                " total) ===",
                "\n".join(go_tools),
                "",
            ]
        )

    for name, content in files.items():
        user_parts.append(f"=== {name} ===")
        user_parts.append(content)
        user_parts.append("")

    agents_path = repo_root / "AGENTS.md"
    if is_automation_source and agents_path.exists():
        agents_md = agents_path.read_text(encoding="utf-8", errors="ignore")[:4000]
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
        print(f"::warning::README automation skipped due to transient LLM outage: {e}")
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
