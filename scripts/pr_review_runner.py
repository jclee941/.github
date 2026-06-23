#!/usr/bin/env python3
"""pr_review_runner.py — Encapsulates pr-review.yml shell logic in testable Python.

Responsibilities:
1. Fetch PR metadata (author, title, LOC, changed files) via gh CLI.
2. Decide which pr-agent commands to run based on PR characteristics.
3. Run each command, capturing output.
4. Detect silent failures (exit 0 but fatal error in logs).
5. Return non-zero exit code on any failure.

Usage:
    python scripts/pr_review_runner.py <PR_URL>

Environment:
    GITHUB_TOKEN or GH_TOKEN — for gh CLI authentication.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PRMeta:
    number: int
    author: str
    title: str
    additions: int
    deletions: int
    files: list[str]

    @property
    def loc(self) -> int:
        return self.additions + self.deletions


# Patterns that indicate a fatal error even when pr-agent exits 0.
FATAL_PATTERNS = [
    r"Failed to generate prediction with any model",
    r"Failed to review PR",
    r"Rate limit error during LLM inference",
    r"Unknown error during LLM inference",
    r"Error during LLM inference",
    r"Failed to publish (code suggestion|inline code comments fallback|diffview file summary|labels)",
    r"Cannot publish a comment if missing PR",
    r"Failed to get (diff files|merge base commit)",
    r"Failed to add AI metadata",
    r"Empty prediction",
    r"ai handler not set",
    r"Unable to decode JSON response",
    r"Failed to parse AI prediction",
    r"Rate limit exceeded for git provider",
    r"BoxKeyError",
    r"GitHub token is required",
    r"Failed to get git provider",
    r"AuthenticationError",
]

# Patterns that are KNOWN no-ops and should be ignored.
NOOP_PATTERNS = [
    r"Empty diff for PR:",
    r"PR has no files:",
    r"Incremental review is enabled.*but there are no new (files|commits)",
    r"Review output is not published",
    r"Incremental review is not supported",
]


def fetch_pr_meta(pr_url: str) -> PRMeta:
    """Fetch PR metadata via gh CLI."""
    repo, num = _parse_pr_url(pr_url)
    result = subprocess.run(
        ["gh", "pr", "view", str(num), "--repo", repo, "--json", "additions,deletions,files,title,author"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Fallback to empty metadata so the runner can still attempt default commands.
        return PRMeta(number=num, author="", title="", additions=0, deletions=0, files=[])

    data = json.loads(result.stdout)
    files = [f.get("path", "") for f in data.get("files", []) if f.get("path")]
    return PRMeta(
        number=num,
        author=data.get("author", {}).get("login", ""),
        title=data.get("title", ""),
        additions=data.get("additions", 0),
        deletions=data.get("deletions", 0),
        files=files,
    )


def _parse_pr_url(pr_url: str) -> tuple[str, int]:
    """Parse 'https://github.com/owner/repo/pull/123' -> ('owner/repo', 123)."""
    match = re.match(r"https://github\.com/([^/]+/[^/]+)/pull/(\d+)", pr_url)
    if not match:
        raise ValueError(f"Cannot parse PR URL: {pr_url}")
    return match.group(1), int(match.group(2))


def decide_commands(meta: PRMeta) -> tuple[list[str], str]:
    """Return (commands, reason) based on PR characteristics."""
    # 1. Bot author
    if meta.author.endswith("[bot]"):
        return ["review"], "bot author"

    # 2. Docs-only diff
    docs_extensions = (".md", ".rst", ".txt", ".adoc")
    docs_prefixes = ("docs/", "README", "LICENSE", "NOTICE", "CONTRIBUTING", ".github/ISSUE", ".github/PULL_REQUEST")
    if meta.files and all(
        f.endswith(docs_extensions) or f.startswith(docs_prefixes) for f in meta.files
    ):
        return ["describe"], "docs-only diff"

    # 3. feat/fix/refactor title
    if re.match(r"^(feat|fix|refactor)(\([a-z0-9_/-]+\))?!?:", meta.title):
        return ["describe", "review"], "feat/fix/refactor PR"

    # 4. Small PR
    if meta.loc < 50:
        return ["review"], "small PR (<50 LOC)"

    # 5. Large PR
    if meta.loc > 1000:
        return ["describe", "review"], "large PR (>1000 LOC)"

    # 6. Default
    return ["describe", "review"], "default"


_VALID_COMMANDS = {"review", "describe", "improve"}


def _llm_command(meta: PRMeta):
    """Ask llm_decide (pr-command) which commands to run. Returns (commands|None, source).

    Returns (None, 'fallback') on any failure so the caller degrades to the
    deterministic decide_commands(). Never raises.
    """
    try:
        import llm_decide
    except Exception:
        return None, "fallback"
    payload = {
        "author": meta.author, "title": meta.title,
        "additions": meta.additions, "deletions": meta.deletions,
        "loc": meta.loc, "files": meta.files,
    }
    try:
        res = llm_decide.decide("pr-command", payload)
    except Exception:
        return None, "fallback"
    if not res.get("ok") or res.get("action") != "command":
        return None, "fallback"
    cmd = res.get("command")
    if not cmd:
        return None, "fallback"
    cmds = [c.strip() for c in str(cmd).split(",") if c.strip()]
    return cmds, "llm"


def decide_commands_with_llm(meta: PRMeta) -> tuple[list[str], str]:
    """DP-16: LLM-first command selection, deterministic fallback.

    Uses the LLM decision only if every returned command is valid; otherwise
    falls back to the deterministic decide_commands() (fail-open).
    """
    cmds, source = _llm_command(meta)
    if cmds and all(c in _VALID_COMMANDS for c in cmds):
        return cmds, f"llm: {source}"
    return decide_commands(meta)


def run_commands(pr_url: str, commands: list[str], log_path: Path) -> int:
    """Run pr-agent commands, tee output to log_path. Return max exit code."""
    log_path.write_text("", encoding="utf-8")
    max_status = 0
    for cmd in commands:
        header = f"--- running pr-agent {cmd} ---\n"
        print(header, end="")
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(header)

        proc = subprocess.run(
            [sys.executable, "-m", "jclee_bot.review_engine.cli", "--pr_url", pr_url, cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        output = proc.stdout or ""
        print(output, end="")
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(output)
            if not output.endswith("\n"):
                log_file.write("\n")

        if proc.returncode != 0:
            max_status = proc.returncode
            print(f"::error::pr-agent {cmd} exited with status {proc.returncode}")
            break

    return max_status


def check_silent_failures(log_path: Path) -> bool:
    """Return True if fatal patterns found (excluding known no-ops)."""
    log_text = log_path.read_text(encoding="utf-8")
    fatal_regex = re.compile("|".join(FATAL_PATTERNS))
    noop_regex = re.compile("|".join(NOOP_PATTERNS))

    found_fatal = False
    for line in log_text.splitlines():
        if fatal_regex.search(line) and not noop_regex.search(line):
            found_fatal = True
            print(f"::error::Silent failure detected: {line.strip()}")

    return found_fatal


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run pr-agent review commands for a PR")
    parser.add_argument("pr_url", help="GitHub PR URL")
    parser.add_argument("--log", type=Path, default=Path("/tmp/pr-agent.log"), help="Log file path")
    args = parser.parse_args(argv)

    meta = fetch_pr_meta(args.pr_url)
    commands, reason = decide_commands_with_llm(meta)

    print(f"::notice::PR #{meta.number} (LOC={meta.loc}, author={meta.author}, title={meta.title})")
    print(f"::notice::Selected commands: {' '.join(commands)}  ({reason})")

    status = run_commands(args.pr_url, commands, args.log)
    if status != 0:
        return status

    if check_silent_failures(args.log):
        print("::error::pr-agent reported a fatal error but exited 0 (silent failure)")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
