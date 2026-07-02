from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import yaml
from pydantic import TypeAdapter

from jclee_bot.json_boundary import JsonValue, is_object_mapping, object_dict, object_list

DEFAULT_CONFIG_PATH: Final = Path(__file__).resolve().parents[1] / "config" / "repos.yaml"
JSON_VALUE_ADAPTER: Final[TypeAdapter[JsonValue]] = TypeAdapter(JsonValue)


@dataclass(frozen=True, slots=True)
class ManagedRepo:
    name: str
    default_branch: str

    def full_name(self, owner: str) -> str:
        return f"{owner}/{self.name}"


def load_health_repos(config_path: Path) -> tuple[ManagedRepo, ...]:
    raw = _safe_load_yaml(config_path.read_text(encoding="utf-8"))
    inventory = object_dict(raw, "repository inventory must be a mapping")
    repositories = object_list(inventory.get("repositories"), "repository inventory must contain repositories")
    managed: list[ManagedRepo] = []
    for entry_value in repositories:
        if not is_object_mapping(entry_value):
            continue
        entry = object_dict(entry_value)
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        automation_value = entry.get("automation")
        automation = object_dict(automation_value) if is_object_mapping(automation_value) else {}
        if automation.get("health_check") is not True:
            continue
        default_branch = entry.get("default_branch")
        managed.append(
            ManagedRepo(name=name, default_branch=default_branch if isinstance(default_branch, str) else "master")
        )
    return tuple(sorted(managed, key=lambda repo: repo.name))


def _safe_load_yaml(text: str) -> JsonValue:
    return JSON_VALUE_ADAPTER.validate_python(yaml.safe_load(text))
