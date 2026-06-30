from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Final

from jclee_bot import workflow_issue_automation
from jclee_bot.git_auth import git_askpass_env, git_env_with_auth
from jclee_bot.repo_standardization_types import MarkdownFinding, RepositoryAction, StandardizationStep, step_status

MAX_DISPLAYED_FINDINGS: Final = 20
MERMAID_DIRECTIVE_RE: Final = re.compile(
    r"^\s*(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|erDiagram|journey|gantt|pie|mindmap|timeline)\b"
)
SKIPPED_DIRS: Final = frozenset(
    {".git", ".hg", ".svn", ".venv", ".omo", "node_modules", "vendor", "dist", "build", "_site"}
)


def docs_step(*, app_id: str, private_key: str, owner: str, repo_names: tuple[str, ...]) -> StandardizationStep:
    actions: list[RepositoryAction] = []
    for repo_name in repo_names:
        full_repo = f"{owner}/{repo_name}"
        token = workflow_issue_automation.installation_token_for_repo(
            app_id=app_id,
            private_key=private_key,
            repo_full_name=full_repo,
        )
        if not token:
            actions.append(RepositoryAction(repo=full_repo, action="failed", detail="installation token unavailable"))
            continue
        try:
            actions.append(scan_remote_repository(token=token, owner=owner, repo_name=repo_name))
        except (OSError, subprocess.SubprocessError) as exc:
            actions.append(RepositoryAction(repo=full_repo, action="failed", detail=str(exc)))
    return StandardizationStep(name="downstream-docs", status=step_status(actions), repositories=tuple(actions))


def scan_remote_repository(*, token: str, owner: str, repo_name: str) -> RepositoryAction:
    full_repo = f"{owner}/{repo_name}"
    with tempfile.TemporaryDirectory(prefix=f"repo-standardization-{repo_name}-") as workspace:
        repo_dir = Path(workspace) / repo_name
        clone_repository(token=token, full_repo=full_repo, repo_dir=repo_dir, workspace=workspace)
        findings = scan_markdown_docs(repo_dir)
    if findings:
        return RepositoryAction(repo=full_repo, action="failed", detail=format_findings(findings))
    return RepositoryAction(repo=full_repo, action="ok")


def clone_repository(*, token: str, full_repo: str, repo_dir: Path, workspace: str) -> None:
    auth_env = git_askpass_env(token=token, workspace=workspace)
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", f"https://github.com/{full_repo}.git", str(repo_dir)],
            check=True,
            timeout=120,
            capture_output=True,
            text=True,
            env=git_env_with_auth(auth_env),
        )
    finally:
        askpass = Path(workspace) / "git-askpass.sh"
        if askpass.exists():
            askpass.unlink()


def scan_markdown_docs(root: Path) -> tuple[MarkdownFinding, ...]:
    findings: list[MarkdownFinding] = []
    for path in root.rglob("*.md"):
        if any(part in SKIPPED_DIRS for part in path.relative_to(root).parts[:-1]):
            continue
        findings.extend(scan_markdown_file(root, path))
    return tuple(findings)


def scan_markdown_file(root: Path, path: Path) -> tuple[MarkdownFinding, ...]:
    rel = path.relative_to(root).as_posix()
    findings: list[MarkdownFinding] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        trimmed = line.strip()
        if trimmed.startswith("```mermaid"):
            findings.append(MarkdownFinding(path=rel, line=index, text="raw Mermaid fenced block"))
            continue
        if MERMAID_DIRECTIVE_RE.match(trimmed):
            findings.append(MarkdownFinding(path=rel, line=index, text=trimmed))
    return tuple(findings)


def format_findings(findings: tuple[MarkdownFinding, ...]) -> str:
    displayed = findings[:MAX_DISPLAYED_FINDINGS]
    parts = [finding.label() for finding in displayed]
    if len(findings) > len(displayed):
        parts.append(f"and {len(findings) - len(displayed)} more")
    return "; ".join(parts)
