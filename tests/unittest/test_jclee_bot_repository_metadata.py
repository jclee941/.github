from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from _pytest.monkeypatch import MonkeyPatch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jclee_bot import repository_metadata, workflow_issue_automation
from jclee_bot.json_boundary import JsonObject


@dataclass(frozen=True, slots=True)
class RepoMetadataCall:
    app_id: str
    private_key: str
    owner: str
    dry_run: bool
    repo_names: set[str] | None


@dataclass(frozen=True, slots=True)
class GitHubMutation:
    method: str
    token: str
    path: str
    payload: JsonObject


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


def app_under_test() -> FastAPI:
    app_candidate = cast(object, importlib.import_module("jclee_bot.app").app)
    if not isinstance(app_candidate, FastAPI):
        raise AssertionError("jclee_bot.app.app must be a FastAPI application")
    return app_candidate


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

    monkeypatch.setattr(
        workflow_issue_automation,
        "installation_token_for_repo",
        fake_installation_token_for_repo,
    )
    monkeypatch.setattr(repository_metadata, "github_get", fake_github_get)

    def forbidden_github_mutation(*, token: str, path: str, payload: JsonObject) -> JsonObject:
        raise AssertionError(f"dry-run must not mutate {path} with {token=} {payload=}")

    monkeypatch.setattr(repository_metadata, "github_patch", forbidden_github_mutation)
    monkeypatch.setattr(repository_metadata, "github_put", forbidden_github_mutation)

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


def test_run_app_repository_metadata_empty_repo_selection_does_not_expand_to_all(tmp_path: Path) -> None:
    inventory = tmp_path / "repos.yaml"
    _ = inventory.write_text(
        """repositories:
  - name: tmux
    metadata:
      description: Tmux configuration
      topics: [terminal]
      homepage: ""
""",
        encoding="utf-8",
    )

    result = repository_metadata.run_app_repository_metadata(
        app_id="1",
        private_key="key",
        owner="jclee941",
        dry_run=True,
        repo_names=set(),
        config_path=inventory,
    )

    assert result["repositories"] == []
    assert result["summary"] == {}


def test_apply_repository_metadata_updates_changed_fields(monkeypatch: MonkeyPatch) -> None:
    mutations: list[GitHubMutation] = []

    def fake_github_patch(*, token: str, path: str, payload: JsonObject) -> JsonObject:
        mutations.append(GitHubMutation("PATCH", token, path, payload))
        return {}

    def fake_github_put(*, token: str, path: str, payload: JsonObject) -> JsonObject:
        mutations.append(GitHubMutation("PUT", token, path, payload))
        return {}

    monkeypatch.setattr(repository_metadata, "github_patch", fake_github_patch)
    monkeypatch.setattr(repository_metadata, "github_put", fake_github_put)

    repository_metadata.apply_repository_metadata(
        token="tok",
        full_repo="jclee941/tmux",
        desired=repository_metadata.DesiredRepositoryMetadata(
            name="tmux",
            description="Tmux configuration",
            homepage="https://example.invalid/tmux",
            topics=("dotfiles", "terminal"),
        ),
        fields=("description", "homepage", "topics"),
    )

    assert mutations == [
        GitHubMutation(
            "PATCH",
            "tok",
            "/repos/jclee941/tmux",
            {"description": "Tmux configuration", "homepage": "https://example.invalid/tmux"},
        ),
        GitHubMutation("PUT", "tok", "/repos/jclee941/tmux/topics", {"names": ["dotfiles", "terminal"]}),
    ]


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
    calls: list[RepoMetadataCall] = []

    def fake_run(
        *,
        app_id: str,
        private_key: str,
        owner: str,
        dry_run: bool,
        repo_names: set[str] | None,
    ) -> JsonObject:
        calls.append(RepoMetadataCall(app_id, private_key, owner, dry_run, repo_names))
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
    assert calls == [RepoMetadataCall("123", "key", "jclee941", True, {"tmux"})]


def test_repo_metadata_endpoint_accepts_background_runs(monkeypatch: MonkeyPatch) -> None:
    calls: list[RepoMetadataCall] = []

    def fake_run(
        *,
        app_id: str,
        private_key: str,
        owner: str,
        dry_run: bool,
        repo_names: set[str] | None,
    ) -> JsonObject:
        calls.append(RepoMetadataCall(app_id, private_key, owner, dry_run, repo_names))
        return {"dry_run": dry_run, "owner": owner, "repositories": [], "summary": {}}

    monkeypatch.setenv("REPO_METADATA_TOKEN", "repo-meta")
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "key")
    monkeypatch.setattr(repository_metadata, "run_app_repository_metadata_safely", fake_run)

    response = TestClient(app_under_test(), raise_server_exceptions=False).post(
        "/api/v1/repo_metadata",
        json={"owner": "jclee941", "repos": ["tmux"], "dry_run": True, "background": True},
        headers={"Authorization": "Bearer repo-meta"},
    )

    assert response.status_code == 200
    assert response.json() == {"accepted": True, "dry_run": True, "owner": "jclee941"}
    assert calls == [RepoMetadataCall("123", "key", "jclee941", True, {"tmux"})]


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
