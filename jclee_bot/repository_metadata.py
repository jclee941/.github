from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TypeGuard, cast

import requests
import yaml

from jclee_bot import workflow_issue_automation
from jclee_bot.github_retry import github_request
from jclee_bot.json_boundary import JsonObject, is_object_mapping, json_object, object_dict, object_list

GITHUB_API = "https://api.github.com"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "repos.yaml"

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DesiredRepositoryMetadata:
    name: str
    description: str
    homepage: str
    topics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ActualRepositoryMetadata:
    description: str
    homepage: str
    topics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MetadataAction:
    repo: str
    action: str
    fields: tuple[str, ...] = ()
    error: str = ""

    def to_dict(self) -> JsonObject:
        return {
            "repo": self.repo,
            "action": self.action,
            "fields": list(self.fields),
            "error": self.error,
        }


def run_app_repository_metadata(
    *,
    app_id: str,
    private_key: str,
    owner: str,
    dry_run: bool,
    repo_names: set[str] | None,
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> JsonObject:
    desired_by_name = desired_repository_metadata(config_path)
    selected_names = set(desired_by_name) if repo_names is None else set(repo_names)
    actions: list[MetadataAction] = []

    unknown = sorted(selected_names - set(desired_by_name))
    for repo_name in unknown:
        actions.append(
            MetadataAction(
                repo=f"{owner}/{repo_name}",
                action="failed",
                error="repository is not configured for metadata automation",
            )
        )

    for repo_name in sorted(selected_names & set(desired_by_name)):
        desired = desired_by_name[repo_name]
        full_repo = f"{owner}/{repo_name}"
        action = reconcile_repository_metadata(
            app_id=app_id,
            private_key=private_key,
            full_repo=full_repo,
            desired=desired,
            dry_run=dry_run,
        )
        actions.append(action)

    return {
        "dry_run": dry_run,
        "owner": owner,
        "repositories": [action.to_dict() for action in actions],
        "summary": summarize_actions(actions),
    }


def run_app_repository_metadata_safely(
    *,
    app_id: str,
    private_key: str,
    owner: str,
    dry_run: bool,
    repo_names: set[str] | None,
) -> JsonObject:
    try:
        return run_app_repository_metadata(
            app_id=app_id,
            private_key=private_key,
            owner=owner,
            dry_run=dry_run,
            repo_names=repo_names,
        )
    except Exception as exc:  # noqa: BLE001 - automation endpoint must return JSON on worker errors
        logger.exception("App repository metadata automation failed")
        return {
            "dry_run": dry_run,
            "owner": owner,
            "repositories": [],
            "error": "repository metadata automation failed",
            "error_type": type(exc).__name__,
        }


def desired_repository_metadata(config_path: Path) -> dict[str, DesiredRepositoryMetadata]:
    raw = cast(object, yaml.safe_load(config_path.read_text(encoding="utf-8")))
    inventory = object_dict(raw, "repository inventory must be a mapping")
    repositories = object_list(inventory.get("repositories"), "repository inventory must contain repositories")

    desired: dict[str, DesiredRepositoryMetadata] = {}
    for entry_value in repositories:
        if not is_object_mapping(entry_value):
            continue
        entry = object_dict(entry_value)
        metadata_value = entry.get("metadata")
        if not is_object_mapping(metadata_value):
            continue
        metadata = object_dict(metadata_value)
        name = entry.get("name")
        description = metadata.get("description")
        if not isinstance(name, str) or not isinstance(description, str) or not description:
            continue
        homepage = metadata.get("homepage")
        topics = metadata.get("topics")
        desired[name] = DesiredRepositoryMetadata(
            name=name,
            description=description,
            homepage=homepage if isinstance(homepage, str) else "",
            topics=normalize_topics(topics),
        )
    return desired


def reconcile_repository_metadata(
    *,
    app_id: str,
    private_key: str,
    full_repo: str,
    desired: DesiredRepositoryMetadata,
    dry_run: bool,
) -> MetadataAction:
    token = workflow_issue_automation.installation_token_for_repo(
        app_id=app_id,
        private_key=private_key,
        repo_full_name=full_repo,
    )
    if not token:
        return MetadataAction(repo=full_repo, action="failed", error="installation token unavailable")

    try:
        actual = fetch_repository_metadata(token=token, full_repo=full_repo)
        drift = metadata_drift(desired, actual)
        if not drift:
            return MetadataAction(repo=full_repo, action="ok")
        if dry_run:
            return MetadataAction(repo=full_repo, action="would_update", fields=drift)
        apply_repository_metadata(token=token, full_repo=full_repo, desired=desired, fields=drift)
        return MetadataAction(repo=full_repo, action="updated", fields=drift)
    except requests.RequestException as exc:
        return MetadataAction(repo=full_repo, action="failed", error=f"github api error: {exc}")
    except ValueError as exc:
        return MetadataAction(repo=full_repo, action="failed", error=str(exc))


def fetch_repository_metadata(*, token: str, full_repo: str) -> ActualRepositoryMetadata:
    repo = github_get(token=token, path=f"/repos/{full_repo}")
    topics = github_get(token=token, path=f"/repos/{full_repo}/topics")
    topic_names = topics.get("names")
    if not isinstance(topic_names, list):
        raise ValueError("GitHub topics response is missing names")
    return ActualRepositoryMetadata(
        description=string_field(repo.get("description")),
        homepage=string_field(repo.get("homepage")),
        topics=normalize_topics(topic_names),
    )


def apply_repository_metadata(
    *,
    token: str,
    full_repo: str,
    desired: DesiredRepositoryMetadata,
    fields: tuple[str, ...],
) -> None:
    if "description" in fields or "homepage" in fields:
        _ = github_patch(
            token=token,
            path=f"/repos/{full_repo}",
            payload={"description": desired.description, "homepage": desired.homepage},
        )
    if "topics" in fields:
        _ = github_put(
            token=token,
            path=f"/repos/{full_repo}/topics",
            payload={"names": list(desired.topics)},
        )


def metadata_drift(
    desired: DesiredRepositoryMetadata,
    actual: ActualRepositoryMetadata,
) -> tuple[str, ...]:
    fields: list[str] = []
    if desired.description != actual.description:
        fields.append("description")
    if desired.homepage != actual.homepage:
        fields.append("homepage")
    if desired.topics != actual.topics:
        fields.append("topics")
    return tuple(fields)


def normalize_topics(values: object) -> tuple[str, ...]:
    if not is_topic_values(values):
        return ()
    topics = {value.strip().lower() for value in values if isinstance(value, str) and value.strip()}
    return tuple(sorted(topics))


def github_get(*, token: str, path: str) -> JsonObject:
    response = github_request(lambda: requests.get(api_url(path), headers=github_headers(token), timeout=30))
    raw = cast(object, response.json())
    return json_object(raw, f"GET {path}")


def github_patch(*, token: str, path: str, payload: JsonObject) -> JsonObject:
    response = github_request(
        lambda: requests.patch(api_url(path), headers=github_headers(token), json=payload, timeout=30)
    )
    raw = cast(object, response.json())
    return json_object(raw, f"PATCH {path}")


def github_put(*, token: str, path: str, payload: JsonObject) -> JsonObject:
    response = github_request(
        lambda: requests.put(api_url(path), headers=github_headers(token), json=payload, timeout=30)
    )
    raw = cast(object, response.json())
    return json_object(raw, f"PUT {path}")


def api_url(path: str) -> str:
    return f"{GITHUB_API}{path}"


def github_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def string_field(value: object) -> str:
    return value if isinstance(value, str) else ""


def summarize_actions(actions: list[MetadataAction]) -> JsonObject:
    summary: JsonObject = {}
    for action in actions:
        current = summary.get(action.action, 0)
        summary[action.action] = current + 1 if isinstance(current, int) else 1
    return summary


def is_topic_values(value: object) -> TypeGuard[list[object] | tuple[object, ...]]:
    return isinstance(value, list | tuple)
