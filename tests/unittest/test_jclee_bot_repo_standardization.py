from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
from _pytest.monkeypatch import MonkeyPatch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jclee_bot import repo_standardization
from jclee_bot.json_boundary import JsonObject, JsonValue


@dataclass(frozen=True, slots=True)
class RepoStandardizationCall:
    app_id: str
    private_key: str
    owner: str
    dry_run: bool
    repo_names: JsonValue


def app_under_test() -> FastAPI:
    app_candidate = cast(object, importlib.import_module("jclee_bot.app").app)
    if not isinstance(app_candidate, FastAPI):
        raise AssertionError("jclee_bot.app.app must be a FastAPI application")
    return app_candidate


def test_repo_standardization_endpoint_delegates_to_app_runner(monkeypatch: MonkeyPatch) -> None:
    calls: list[RepoStandardizationCall] = []

    def fake_run(
        *,
        app_id: str,
        private_key: str,
        owner: str,
        dry_run: bool,
        repo_names: JsonValue,
    ) -> JsonObject:
        calls.append(RepoStandardizationCall(app_id, private_key, owner, dry_run, repo_names))
        return {"dry_run": dry_run, "owner": owner, "steps": [], "summary": {"status": "ok", "failed_steps": []}}

    monkeypatch.setenv("REPO_STANDARDIZATION_TOKEN", "repo-std")
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "key")
    monkeypatch.setattr(repo_standardization, "run_app_repo_standardization_safely", fake_run)

    response = TestClient(app_under_test(), raise_server_exceptions=False).post(
        "/api/v1/repo_standardization",
        json={"owner": "jclee941", "repos": "tmux,resume", "dry_run": True},
        headers={"Authorization": "Bearer repo-std"},
    )

    assert response.status_code == 200
    assert response.json()["summary"]["status"] == "ok"
    assert calls == [RepoStandardizationCall("123", "key", "jclee941", True, "tmux,resume")]


def test_repo_standardization_endpoint_reports_failed_summary(monkeypatch: MonkeyPatch) -> None:
    def fake_run(
        *,
        app_id: str,
        private_key: str,
        owner: str,
        dry_run: bool,
        repo_names: JsonValue,
    ) -> JsonObject:
        return {
            "dry_run": dry_run,
            "owner": owner,
            "steps": [],
            "summary": {"status": "failed", "failed_steps": ["downstream-docs"]},
        }

    monkeypatch.setenv("REPO_STANDARDIZATION_TOKEN", "repo-std")
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "key")
    monkeypatch.setattr(repo_standardization, "run_app_repo_standardization_safely", fake_run)

    response = TestClient(app_under_test(), raise_server_exceptions=False).post(
        "/api/v1/repo_standardization",
        json={"owner": "jclee941", "dry_run": True},
        headers={"Authorization": "Bearer repo-std"},
    )

    assert response.status_code == 500
    assert response.json()["summary"]["failed_steps"] == ["downstream-docs"]


def test_parse_repo_selection_rejects_paths() -> None:
    with pytest.raises(ValueError, match="managed repo name"):
        repo_standardization.parse_repo_selection("../tmux", frozenset({"tmux"}))


def test_scan_markdown_docs_detects_raw_mermaid(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    _ = readme.write_text("# Diagram\n\n```mermaid\nflowchart LR\nA --> B\n```\n", encoding="utf-8")

    findings = repo_standardization.scan_markdown_docs(tmp_path)

    assert [finding.label() for finding in findings] == [
        "README.md:3 raw Mermaid fenced block",
        "README.md:4 flowchart LR",
    ]
