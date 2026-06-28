from __future__ import annotations

from pathlib import Path
from typing import TypedDict

import requests
import yaml

from jclee_bot import github_checks
from jclee_bot.github_api_client import GITHUB_API, headers


class AppInstallation(TypedDict, total=False):
    id: int | str | None


class InstallationRepository(TypedDict, total=False):
    full_name: str
    name: str


def managed_repo_names(config_path: Path | None = None) -> set[str] | None:
    path = config_path or Path(__file__).resolve().parents[1] / "config" / "repos.yaml"
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    repos = data.get("repositories", []) if isinstance(data, dict) else []
    return {
        str(repo["name"])
        for repo in repos
        if isinstance(repo, dict) and repo.get("automation", {}).get("deploy_workflows") is True
    }


def app_installations(*, app_id: str, private_key: str) -> list[AppInstallation]:
    token_jwt = github_checks._app_jwt(app_id, private_key)  # noqa: SLF001 - shared App auth helper
    resp = requests.get(
        f"{GITHUB_API}/app/installations",
        headers={"Authorization": f"Bearer {token_jwt}", "Accept": "application/vnd.github+json"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def installation_repositories(*, token: str) -> list[InstallationRepository]:
    repos: list[InstallationRepository] = []
    page = 1
    while True:
        resp = requests.get(
            f"{GITHUB_API}/installation/repositories",
            headers=headers(token),
            params={"per_page": 100, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("repositories", []) if isinstance(data, dict) else []
        repos.extend(batch)
        if len(batch) < 100:
            return repos
        page += 1
