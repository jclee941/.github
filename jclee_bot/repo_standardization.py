from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, cast

import requests
import yaml

from jclee_bot import repository_metadata, workflow_issue_automation
from jclee_bot.git_auth import git_askpass_env, git_env_with_auth
from jclee_bot.github_api_client import GITHUB_API, headers
from jclee_bot.json_boundary import JsonObject, JsonValue, is_object_mapping, json_object, object_dict, object_list

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH: Final = Path(__file__).resolve().parents[1] / "config" / "repos.yaml"
OWNER: Final = "jclee941"
TARGET_BRANCH: Final = "master"
DEFAULT_RULESET_NAME: Final = "Default Branch Protection"
MAX_DISPLAYED_FINDINGS: Final = 20
MERMAID_DIRECTIVE_RE: Final = re.compile(
    r"^\s*(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|erDiagram|journey|gantt|pie|mindmap|timeline)\b"
)
SKIPPED_DIRS: Final = frozenset(
    {".git", ".hg", ".svn", ".venv", ".omo", "node_modules", "vendor", "dist", "build", "_site"}
)
REQUIRED_CHECKS: Final = (
    "jclee-bot / pr-metadata",
    "jclee-bot / secret-scan",
    "jclee-bot / actionlint",
)

type StepStatus = Literal["ok", "failed"]
type RepoAction = Literal["ok", "failed", "skipped", "would_update", "updated", "would_apply", "applied", "listed"]


@dataclass(frozen=True, slots=True)
class RepoInventory:
    all_names: frozenset[str]
    deployable_names: frozenset[str]
    protected_names: frozenset[str]


@dataclass(frozen=True, slots=True)
class MarkdownFinding:
    path: str
    line: int
    text: str

    def label(self) -> str:
        return f"{self.path}:{self.line} {self.text}"


@dataclass(frozen=True, slots=True)
class RepositoryAction:
    repo: str
    action: RepoAction
    detail: str = ""

    def to_dict(self) -> JsonObject:
        return {"repo": self.repo, "action": self.action, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class StandardizationStep:
    name: str
    status: StepStatus
    repositories: tuple[RepositoryAction, ...]

    def to_dict(self) -> JsonObject:
        return {
            "name": self.name,
            "status": self.status,
            "repositories": [action.to_dict() for action in self.repositories],
        }


def run_app_repo_standardization_safely(
    *,
    app_id: str,
    private_key: str,
    owner: str,
    dry_run: bool,
    repo_names: JsonValue,
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> JsonObject:
    try:
        return run_app_repo_standardization(
            app_id=app_id,
            private_key=private_key,
            owner=owner,
            dry_run=dry_run,
            repo_names=repo_names,
            config_path=config_path,
        )
    except (OSError, ValueError, requests.RequestException, subprocess.SubprocessError) as exc:
        logger.exception("App repository standardization failed")
        return {
            "dry_run": dry_run,
            "owner": owner,
            "steps": [],
            "error": "repository standardization failed",
            "error_type": type(exc).__name__,
            "detail": str(exc),
        }


def run_app_repo_standardization(
    *,
    app_id: str,
    private_key: str,
    owner: str,
    dry_run: bool,
    repo_names: JsonValue,
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> JsonObject:
    if owner != OWNER:
        raise ValueError("owner must be jclee941")
    inventory = load_inventory(config_path)
    selected = parse_repo_selection(repo_names, inventory.all_names)
    metadata_repos = None if selected is None else set(selected)

    metadata = repository_metadata.run_app_repository_metadata_safely(
        app_id=app_id,
        private_key=private_key,
        owner=owner,
        dry_run=dry_run,
        repo_names=metadata_repos,
    )
    steps = [
        metadata_step(metadata),
        docs_step(
            app_id=app_id,
            private_key=private_key,
            owner=owner,
            repo_names=select_target_repos(selected, inventory.deployable_names),
        ),
        branch_protection_step(
            app_id=app_id,
            private_key=private_key,
            owner=owner,
            dry_run=dry_run,
            repo_names=select_target_repos(selected, inventory.protected_names),
        ),
        rulesets_step(
            app_id=app_id,
            private_key=private_key,
            owner=owner,
            dry_run=dry_run,
            repo_names=select_target_repos(selected, inventory.protected_names),
        ),
    ]
    failed_steps = tuple(step.name for step in steps if step.status == "failed")
    return {
        "dry_run": dry_run,
        "owner": owner,
        "steps": [step.to_dict() for step in steps],
        "summary": {
            "status": "failed" if failed_steps else "ok",
            "failed_steps": list(failed_steps),
        },
    }


def load_inventory(config_path: Path) -> RepoInventory:
    raw = cast(object, yaml.safe_load(config_path.read_text(encoding="utf-8")))
    inventory = object_dict(raw, "repository inventory must be a mapping")
    repositories = object_list(inventory.get("repositories"), "repository inventory must contain repositories")
    all_names: set[str] = set()
    deployable_names: set[str] = set()
    protected_names: set[str] = set()
    for entry_value in repositories:
        if not is_object_mapping(entry_value):
            continue
        entry = object_dict(entry_value)
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        all_names.add(name)
        automation_value = entry.get("automation")
        automation = object_dict(automation_value) if is_object_mapping(automation_value) else {}
        if automation.get("deploy_workflows") is True:
            deployable_names.add(name)
        if automation.get("branch_protection") is True:
            protected_names.add(name)
    return RepoInventory(
        all_names=frozenset(all_names),
        deployable_names=frozenset(deployable_names),
        protected_names=frozenset(protected_names),
    )


def parse_repo_selection(value: JsonValue, allowed_names: frozenset[str]) -> frozenset[str] | None:
    if value is None or value == "":
        return None
    raw_names: list[str]
    if isinstance(value, str):
        raw_names = value.split(",")
    elif isinstance(value, list):
        raw_names = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("repos must contain GitHub repository names")
            raw_names.append(item)
    else:
        raise ValueError("repos must be a list or comma-separated string")

    selected: set[str] = set()
    for raw_name in raw_names:
        name = raw_name.strip()
        if not name:
            continue
        if "/" in name or "\\" in name or ".." in name:
            raise ValueError(f"repo {name!r} must be a managed repo name, not a path")
        if name not in allowed_names:
            raise ValueError(f"unsupported repo {name!r}")
        selected.add(name)
    if not selected:
        return None
    return frozenset(selected)


def select_target_repos(selected: frozenset[str] | None, target_names: frozenset[str]) -> tuple[str, ...]:
    names = target_names if selected is None else selected & target_names
    return tuple(sorted(names))


def metadata_step(metadata: JsonObject) -> StandardizationStep:
    repositories: list[RepositoryAction] = []
    raw_repositories = metadata.get("repositories", [])
    if isinstance(raw_repositories, list):
        for item in raw_repositories:
            if not isinstance(item, dict):
                continue
            repo = str(item.get("repo") or "")
            action = str(item.get("action") or "failed")
            raw_fields = item.get("fields", [])
            fields = raw_fields if isinstance(raw_fields, list) else []
            detail = str(item.get("error") or ",".join(str(field) for field in fields if isinstance(field, str)))
            repositories.append(RepositoryAction(repo=repo, action=repo_action(action), detail=detail))
    has_failure = metadata.get("error") or any(item.action == "failed" for item in repositories)
    status: StepStatus = "failed" if has_failure else "ok"
    return StandardizationStep(name="repository-metadata", status=status, repositories=tuple(repositories))


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


def branch_protection_step(
    *,
    app_id: str,
    private_key: str,
    owner: str,
    dry_run: bool,
    repo_names: tuple[str, ...],
) -> StandardizationStep:
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
            actions.append(apply_branch_protection(token=token, full_repo=full_repo, dry_run=dry_run))
        except requests.RequestException as exc:
            actions.append(RepositoryAction(repo=full_repo, action="failed", detail=str(exc)))
    return StandardizationStep(name="branch-protection", status=step_status(actions), repositories=tuple(actions))


def apply_branch_protection(*, token: str, full_repo: str, dry_run: bool) -> RepositoryAction:
    if dry_run:
        return RepositoryAction(repo=full_repo, action="would_apply")
    github_patch(
        token=token,
        path=f"/repos/{full_repo}",
        payload={"allow_auto_merge": True, "delete_branch_on_merge": True},
    )
    github_put(
        token=token,
        path=f"/repos/{full_repo}/branches/{TARGET_BRANCH}/protection",
        payload=branch_protection_payload(),
    )
    return RepositoryAction(repo=full_repo, action="applied")


def branch_protection_payload() -> JsonObject:
    return {
        "required_status_checks": {
            "strict": False,
            "contexts": list(REQUIRED_CHECKS),
        },
        "enforce_admins": False,
        "required_pull_request_reviews": None,
        "restrictions": None,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "block_creations": False,
        "required_linear_history": False,
        "required_conversation_resolution": False,
        "lock_branch": False,
        "allow_fork_syncing": True,
    }


def rulesets_step(
    *,
    app_id: str,
    private_key: str,
    owner: str,
    dry_run: bool,
    repo_names: tuple[str, ...],
) -> StandardizationStep:
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
            actions.append(upsert_ruleset(token=token, full_repo=full_repo, dry_run=dry_run))
        except requests.RequestException as exc:
            actions.append(RepositoryAction(repo=full_repo, action="failed", detail=str(exc)))
    return StandardizationStep(name="rulesets", status=step_status(actions), repositories=tuple(actions))


def upsert_ruleset(*, token: str, full_repo: str, dry_run: bool) -> RepositoryAction:
    existing_id = find_ruleset_id(token=token, full_repo=full_repo, ruleset_name=DEFAULT_RULESET_NAME)
    if dry_run:
        detail = "update existing ruleset" if existing_id else "create ruleset"
        return RepositoryAction(repo=full_repo, action="would_apply", detail=detail)
    method = github_put if existing_id else github_post
    path = f"/repos/{full_repo}/rulesets/{existing_id}" if existing_id else f"/repos/{full_repo}/rulesets"
    method(token=token, path=path, payload=ruleset_payload())
    return RepositoryAction(repo=full_repo, action="applied")


def find_ruleset_id(*, token: str, full_repo: str, ruleset_name: str) -> int | None:
    response = requests.get(f"{GITHUB_API}/repos/{full_repo}/rulesets", headers=headers(token), timeout=30)
    response.raise_for_status()
    raw_rulesets = response.json()
    if not isinstance(raw_rulesets, list):
        return None
    for item in raw_rulesets:
        if not isinstance(item, dict) or item.get("name") != ruleset_name:
            continue
        ruleset_id = item.get("id")
        if isinstance(ruleset_id, int):
            return ruleset_id
    return None


def ruleset_payload() -> JsonObject:
    return {
        "name": DEFAULT_RULESET_NAME,
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}],
        "conditions": {"ref_name": {"include": [f"refs/heads/{TARGET_BRANCH}"], "exclude": []}},
        "rules": [
            {
                "type": "required_status_checks",
                "parameters": {
                    "required_status_checks": [{"context": context} for context in REQUIRED_CHECKS],
                    "strict_required_status_checks_policy": False,
                },
            },
            {"type": "deletion"},
            {"type": "non_fast_forward"},
        ],
    }


def github_patch(*, token: str, path: str, payload: JsonObject) -> JsonObject:
    response = requests.patch(f"{GITHUB_API}{path}", headers=headers(token), json=payload, timeout=30)
    response.raise_for_status()
    return json_object(response.json(), f"PATCH {path}")


def github_put(*, token: str, path: str, payload: JsonObject) -> JsonObject:
    response = requests.put(f"{GITHUB_API}{path}", headers=headers(token), json=payload, timeout=30)
    response.raise_for_status()
    raw = response.json() if response.content else {}
    return json_object(raw, f"PUT {path}")


def github_post(*, token: str, path: str, payload: JsonObject) -> JsonObject:
    response = requests.post(f"{GITHUB_API}{path}", headers=headers(token), json=payload, timeout=30)
    response.raise_for_status()
    return json_object(response.json(), f"POST {path}")


def step_status(actions: list[RepositoryAction]) -> StepStatus:
    return "failed" if any(action.action == "failed" for action in actions) else "ok"


def repo_action(value: str) -> RepoAction:
    match value:
        case "ok":
            return "ok"
        case "failed":
            return "failed"
        case "skipped":
            return "skipped"
        case "would_update":
            return "would_update"
        case "updated":
            return "updated"
        case "would_apply":
            return "would_apply"
        case "applied":
            return "applied"
        case "listed":
            return "listed"
        case _:
            return "failed"
