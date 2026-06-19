from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from jclee_bot.checks import CheckResult

CHECK_NAME = "jclee-bot / docs-policy"

_CODE_EXTENSIONS = frozenset({".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java"})
_CONFIG_EXTENSIONS = frozenset({".toml", ".yaml", ".yml", ".json"})
_PRIVATE_IP = re.compile(
    r"\b(?:10\.(?:\d{1,3}\.){2}\d{1,3}|172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})\b"
)


def _is_markdown(path: str) -> bool:
    name = Path(path).name.lower()
    return path.lower().endswith(".md") or name.startswith("readme") or name.startswith("changelog")


def _has_docs(path: str) -> bool:
    return path.startswith("docs/") or _is_markdown(path)


def _has_readme(path: str) -> bool:
    return "readme" in Path(path).name.lower()


def _is_code(path: str) -> bool:
    return Path(path).suffix.lower() in _CODE_EXTENSIONS


def _is_config(path: str) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in _CONFIG_EXTENSIONS or ".env" in path


def _is_api(path: str) -> bool:
    lowered = path.lower()
    return any(marker in lowered for marker in ("route", "api", "endpoint", "handler", "controller"))


def _is_api_doc(path: str) -> bool:
    lowered = path.lower()
    return (
        "openapi" in lowered
        or "swagger" in lowered
        or "api-doc" in lowered
        or (path.startswith("docs/") and "api" in lowered)
    )


def _private_ip_hits(*, changed_files: Sequence[str], workspace: str) -> list[str]:
    hits: list[str] = []
    root = Path(workspace)
    for rel in changed_files:
        if not _is_markdown(rel):
            continue
        path = (root / rel).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            continue
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if _PRIVATE_IP.search(line):
                hits.append(f"{rel}:{i}")
    return hits


def run(*, changed_files: Sequence[str], workspace: str) -> CheckResult:
    private_ips = _private_ip_hits(changed_files=changed_files, workspace=workspace)
    if private_ips:
        return CheckResult(
            name=CHECK_NAME,
            conclusion="failure",
            title="documentation policy failed",
            summary="Hardcoded private IPs found in Markdown docs: " + ", ".join(private_ips[:20]),
        )

    has_code = any(_is_code(f) for f in changed_files)
    has_config = any(_is_config(f) for f in changed_files)
    has_docs_change = any(_has_docs(f) for f in changed_files)
    has_readme_change = any(_has_readme(f) for f in changed_files)
    has_api_change = any(_is_api(f) for f in changed_files)
    has_api_docs = any(_is_api_doc(f) for f in changed_files)

    warnings: list[str] = []
    if has_code and not has_docs_change:
        warnings.append("Code changed without README/docs updates; verify user-facing docs are still current.")
    if has_config and not has_readme_change:
        warnings.append("Configuration changed without README updates; verify setup/config examples are still current.")
    if has_api_change and not has_api_docs:
        warnings.append("API-related files changed without OpenAPI/Swagger/API docs updates.")

    if warnings:
        return CheckResult(
            name=CHECK_NAME,
            conclusion="neutral",
            title="documentation review recommended",
            summary="\n".join(f"- {warning}" for warning in warnings),
        )

    if not changed_files:
        return CheckResult(
            name=CHECK_NAME,
            conclusion="neutral",
            title="docs-policy not run",
            summary="No changed-file context was available.",
        )

    return CheckResult(
        name=CHECK_NAME,
        conclusion="success",
        title="documentation policy OK",
        summary="No Markdown private IP leaks or documentation freshness warnings detected.",
    )
