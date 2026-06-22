"""Repository inventory constants for live GitHub E2E tests."""

from __future__ import annotations

from pathlib import Path
from typing import TypeAlias

import yaml

JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

GITHUB_API_URL = "https://api.github.com"
GITHUB_OWNER = "jclee941"

REPO_ROOT = Path(__file__).resolve().parents[2]
REPOS_CONFIG = REPO_ROOT / "config" / "repos.yaml"
REQUIRED_WORKFLOWS: list[str] = []
REQUIRED_FILES = [".github/dependabot.yml", ".github/CODEOWNERS", ".github/PULL_REQUEST_TEMPLATE.md"]
REQUIRED_CONTEXTS = ["jclee-bot / pr-metadata", "jclee-bot / secret-scan", "jclee-bot / actionlint"]


def _load_repos_config() -> list[JsonObject]:
    payload = yaml.safe_load(REPOS_CONFIG.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), "config/repos.yaml must contain a mapping"
    repositories = payload.get("repositories")
    assert isinstance(repositories, list), "config/repos.yaml must contain repositories list"
    for repo in repositories:
        assert isinstance(repo, dict), "config/repos.yaml repository entries must be mappings"
    return repositories


def configured_repo_names(flag: str | None = None) -> list[str]:
    names: list[str] = []
    for repo in _load_repos_config():
        if flag is not None:
            automation = repo.get("automation")
            if not isinstance(automation, dict) or automation.get(flag) is not True:
                continue
        name = repo.get("name")
        assert isinstance(name, str), "repository entry missing string name"
        names.append(name)
    return names
