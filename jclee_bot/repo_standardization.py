from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

import requests
import yaml

from jclee_bot import repository_metadata
from jclee_bot.json_boundary import JsonObject, JsonValue, is_object_mapping, object_dict, object_list
from jclee_bot.repo_standardization_docs import docs_step, scan_markdown_docs
from jclee_bot.repo_standardization_github import branch_protection_step, rulesets_step
from jclee_bot.repo_standardization_types import RepoAction, RepositoryAction, StandardizationStep, StepStatus

logger = logging.getLogger(__name__)

__all__ = [
    "parse_repo_selection",
    "run_app_repo_standardization",
    "run_app_repo_standardization_safely",
    "scan_markdown_docs",
]

DEFAULT_CONFIG_PATH: Final = Path(__file__).resolve().parents[1] / "config" / "repos.yaml"
OWNER: Final = "jclee941"


@dataclass(frozen=True, slots=True)
class RepoInventory:
    all_names: frozenset[str]
    deployable_names: frozenset[str]
    protected_names: frozenset[str]


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
