from __future__ import annotations

import importlib
from pathlib import Path
from typing import cast

from _pytest.monkeypatch import MonkeyPatch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jclee_bot import repository_metadata, workflow_issue_automation
from jclee_bot.json_boundary import JsonObject


def fake_installation_token_for_repo(
    *,
    app_id: str,
    private_key: str,
    repo_full_name: str,
) -> str:
    assert app_id
    assert private_key
    assert repo_full_name == "jclee941/tmux"
    return "tok"


def fake_github_get(*, token: str, path: str) -> JsonObject:
    assert token == "tok"
    if path == "/repos/jclee941/tmux":
        return {"description": "Old", "homepage": ""}
    return {"names": ["dotfiles", "terminal"]}


def fake_github_patch(*, token: str, path: str, payload: JsonObject) -> JsonObject:
    assert token == "tok"
    assert path
    assert payload
    mutations_for_test.append("patch")
    return {}


def fake_github_put(*, token: str, path: str, payload: JsonObject) -> JsonObject:
    assert token == "tok"
    assert path
    assert payload
    mutations_for_test.append("put")
    return {}


def app_under_test() -> FastAPI:
    module = importlib.import_module("jclee_bot.app")
    return cast(FastAPI, module.app)


mutations_for_test: list[str] = []


def test_metadata_drift_detects_description_and_ignores_topic_order() -> None:
    desired = repository_metadata.DesiredRepositoryMetadata(
        name="tmux",
        description="Standard description",
        homepage="",
        topics=("automation", "security"),
    )
    actual = repository_metadata.ActualRepositoryMetadata(
        description="Old description",
        homepage="",
        topics=("automation", "security"),
    )

    assert repository_metadata.metadata_drift(desired, actual) == ("description",)


def test_run_app_repository_metadata_dry_run_reports_drift_without_mutation(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    inventory = tmp_path / "repos.yaml"
    _ = inventory.write_text(
        """repositories:
  - name: source
    automation:
      deploy_workflows: false
    metadata:
      description: Source repo
      topics: [skip]
      homepage: ""
  - name: tmux
    automation:
      deploy_workflows: true
    metadata:
      description: Tmux configuration
      topics: [terminal, dotfiles]
      homepage: ""
""",
        encoding="utf-8",
    )

    mutations_for_test.clear()

    monkeypatch.setattr(
        workflow_issue_automation,
        "installation_token_for_repo",
        fake_installation_token_for_repo,
    )
    monkeypatch.setattr(repository_metadata, "github_get", fake_github_get)
    monkeypatch.setattr(repository_metadata, "github_patch", fake_github_patch)
    monkeypatch.setattr(repository_metadata, "github_put", fake_github_put)

    result = repository_metadata.run_app_repository_metadata(
        app_id="1",
        private_key="key",
        owner="jclee941",
        dry_run=True,
        repo_names={"tmux"},
        config_path=inventory,
    )

    assert result["repositories"] == [
        {
            "repo": "jclee941/tmux",
            "action": "would_update",
            "fields": ["description"],
            "error": "",
        }
    ]
    assert mutations_for_test == []


def test_desired_repository_metadata_uses_metadata_presence_not_deployability(tmp_path: Path) -> None:
    inventory = tmp_path / "repos.yaml"
    _ = inventory.write_text(
        """repositories:
  - name: metadata-only
    automation:
      deploy_workflows: false
    metadata:
      description: Metadata only repo
      topics: [Automation]
      homepage: ""
""",
        encoding="utf-8",
    )

    desired = repository_metadata.desired_repository_metadata(inventory)

    assert set(desired) == {"metadata-only"}
    assert desired["metadata-only"].topics == ("automation",)


def test_repo_metadata_endpoint_delegates_to_app_runner(monkeypatch: MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> JsonObject:
        calls.append(kwargs)
        return {"dry_run": True, "owner": "jclee941", "repositories": [], "summary": {}}

    monkeypatch.setenv("REPO_METADATA_TOKEN", "repo-meta")
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "key")
    monkeypatch.setattr(repository_metadata, "run_app_repository_metadata_safely", fake_run)

    response = TestClient(app_under_test(), raise_server_exceptions=False).post(
        "/api/v1/repo_metadata",
        json={"owner": "jclee941", "repos": ["tmux"], "dry_run": True},
        headers={"Authorization": "Bearer repo-meta"},
    )

    assert response.status_code == 200
    assert response.json()["summary"] == {}
    assert calls == [
        {
            "app_id": "123",
            "private_key": "key",
            "owner": "jclee941",
            "dry_run": True,
            "repo_names": {"tmux"},
        }
    ]


def test_repo_metadata_endpoint_requires_dedicated_token(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("REPO_METADATA_TOKEN", raising=False)
    monkeypatch.setenv("ISSUE_MAINTENANCE_TOKEN", "issue-token")
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "key")

    response = TestClient(app_under_test(), raise_server_exceptions=False).post(
        "/api/v1/repo_metadata",
        json={"owner": "jclee941", "repos": ["tmux"], "dry_run": True},
        headers={"Authorization": "Bearer issue-token"},
    )

    assert response.status_code == 401


def test_repo_metadata_endpoint_rejects_non_jclee941_owner(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("REPO_METADATA_TOKEN", "repo-meta")
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "key")

    response = TestClient(app_under_test(), raise_server_exceptions=False).post(
        "/api/v1/repo_metadata",
        json={"owner": "other-owner", "repos": ["tmux"], "dry_run": True},
        headers={"Authorization": "Bearer repo-meta"},
    )

    assert response.status_code == 400
    assert response.json() == {"error": "owner must be jclee941"}
