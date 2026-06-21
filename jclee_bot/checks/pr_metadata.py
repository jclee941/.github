"""pr-metadata check: title convention, PR size, sensitive files.

Consolidates the old per-repo 03_pr-checks + 09_semantic-pr workflows into a
single App-reported check. Pure function — no network.
"""
from __future__ import annotations

import re
from collections.abc import Sequence

from jclee_bot.checks import CheckResult

CHECK_NAME = "jclee-bot / pr-metadata"

# Conventional-commit style prefixes (semantic PR).
_CONVENTIONAL_TITLE = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(\([\w./-]+\))?!?: .+",
)

# PR size thresholds (mirrors the prior pr-checks 500 LOC guard).
_MAX_CHANGED_LINES = 500
_MAX_CHANGED_FILES = 50

# Files that should never appear in a normal PR diff.
_SENSITIVE_PATTERNS = (
    re.compile(r"(^|/)\.env(\.|$)"),
    re.compile(r"(^|/)\.secrets\.toml$"),
    re.compile(r"(^|/)id_rsa$"),
    re.compile(r"\.pem$"),
    re.compile(r"(^|/)\.npmrc$"),
)


def _sensitive(changed_files: Sequence[str]) -> list[str]:
    hits: list[str] = []
    for f in changed_files:
        if any(p.search(f) for p in _SENSITIVE_PATTERNS):
            hits.append(f)
    return hits


def _readme_automation_pr(*, head_ref: str, changed_files: Sequence[str]) -> bool:
    return head_ref == "bot/auto-readme-update" and set(changed_files) == {"README.md"}


def _retired_workflow_cleanup_pr(*, head_ref: str, changed_files: Sequence[str]) -> bool:
    return head_ref == "bot/remove-downstream-workflows" and all(
        path.startswith(".github/workflows/") for path in changed_files
    )


def _dependabot_lockfile_pr(*, head_ref: str, changed_files: Sequence[str]) -> bool:
    if not head_ref.startswith("dependabot/"):
        return False

    return all(path.endswith(("package.json", "package-lock.json")) for path in changed_files)


def run(
    *,
    title: str,
    head_ref: str,
    base_ref: str,
    changed_files: Sequence[str],
    additions: int,
    deletions: int,
) -> CheckResult:
    problems: list[str] = []

    if not _CONVENTIONAL_TITLE.match(title.strip()):
        problems.append(
            "PR title must follow conventional commits "
            "(e.g. `feat: ...`, `fix(scope): ...`)."
        )

    total_lines = additions + deletions
    size_exempt = (
        _readme_automation_pr(head_ref=head_ref, changed_files=changed_files)
        or _retired_workflow_cleanup_pr(head_ref=head_ref, changed_files=changed_files)
        or _dependabot_lockfile_pr(head_ref=head_ref, changed_files=changed_files)
    )
    if not size_exempt and (
        total_lines > _MAX_CHANGED_LINES or len(changed_files) > _MAX_CHANGED_FILES
    ):
        problems.append(
            f"PR size too large: {total_lines} changed LOC across "
            f"{len(changed_files)} files (limit {_MAX_CHANGED_LINES} LOC / "
            f"{_MAX_CHANGED_FILES} files)."
        )

    sensitive = _sensitive(changed_files)
    if sensitive:
        problems.append("Sensitive files present in diff: " + ", ".join(sensitive))

    if problems:
        return CheckResult(
            name=CHECK_NAME,
            conclusion="failure",
            title="PR metadata checks failed",
            summary="\n".join(f"- {p}" for p in problems),
        )

    return CheckResult(
        name=CHECK_NAME,
        conclusion="success",
        title="PR metadata OK",
        summary=(
            f"Title follows conventional commits; {additions + deletions} LOC "
            f"across {len(changed_files)} files; no sensitive files."
        ),
    )
