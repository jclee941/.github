from __future__ import annotations

import json
import subprocess
import threading

from fastapi.testclient import TestClient

from jclee_bot import app as app_module


class TestWrapperAppGitOps:
    def test_create_event_on_main_webhook_triggers_gitops_automation(self, monkeypatch) -> None:
        ran = []
        done = threading.Event()

        def fake_gitops(payload, event):
            ran.append((event, payload.get("ref")))
            done.set()
            return {"actions": ["create-pr:9"]}

        monkeypatch.setattr(app_module, "_run_gitops_automation_for_payload", fake_gitops)
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "")
        payload = {
            "ref": "fix/issue-7-broken-ci",
            "ref_type": "branch",
            "installation": {"id": 1},
            "repository": {"full_name": "jclee941/x", "default_branch": "master"},
            "sender": {"login": "jclee941"},
        }

        response = TestClient(app_module.app, raise_server_exceptions=False).post(
            "/api/v1/github_webhooks",
            content=json.dumps(payload),
            headers={"X-GitHub-Event": "create"},
        )

        assert response.status_code != 500
        assert done.wait(2.0), "GitOps automation did not run for create webhook"
        assert ran == [("create", "fix/issue-7-broken-ci")]

    def test_labeled_pull_request_on_main_webhook_triggers_gitops_auto_merge(self, monkeypatch) -> None:
        ran = []
        done = threading.Event()

        def fake_gitops(payload, event):
            ran.append((event, payload.get("action"), payload.get("label", {}).get("name")))
            done.set()
            return {"actions": ["enable-auto-merge:9"]}

        monkeypatch.setattr(app_module, "_run_gitops_automation_for_payload", fake_gitops)
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "")
        payload = {
            "action": "labeled",
            "label": {"name": "auto-merge"},
            "installation": {"id": 1},
            "repository": {"full_name": "jclee941/x", "default_branch": "master"},
            "pull_request": {"number": 9, "node_id": "PR_9", "draft": False},
            "sender": {"login": "jclee941"},
        }

        response = TestClient(app_module.app, raise_server_exceptions=False).post(
            "/api/v1/github_webhooks",
            content=json.dumps(payload),
            headers={"X-GitHub-Event": "pull_request"},
        )

        assert response.status_code != 500
        assert done.wait(2.0), "GitOps auto-merge did not run for labeled pull_request webhook"
        assert ran == [("pull_request", "labeled", "auto-merge")]

    def test_ready_pull_request_on_main_webhook_triggers_gitops_auto_merge(self, monkeypatch) -> None:
        ran = []
        done = threading.Event()

        def fake_gitops(payload, event):
            ran.append((event, payload.get("action"), payload.get("pull_request", {}).get("labels", [])))
            done.set()
            return {"actions": ["enable-auto-merge:9"]}

        monkeypatch.setattr(app_module, "_run_gitops_automation_for_payload", fake_gitops)
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "")
        payload = {
            "action": "ready_for_review",
            "installation": {"id": 1},
            "repository": {"full_name": "jclee941/x", "default_branch": "master"},
            "pull_request": {
                "number": 9,
                "node_id": "PR_9",
                "draft": False,
                "labels": [{"name": "auto-merge"}],
            },
            "sender": {"login": "jclee941"},
        }

        response = TestClient(app_module.app, raise_server_exceptions=False).post(
            "/api/v1/github_webhooks",
            content=json.dumps(payload),
            headers={"X-GitHub-Event": "pull_request"},
        )

        assert response.status_code != 500
        assert done.wait(2.0), "GitOps auto-merge did not run for ready pull_request webhook"
        assert ran == [("pull_request", "ready_for_review", [{"name": "auto-merge"}])]

    def test_checkout_pr_head_uses_askpass_without_token_in_git_args(self, monkeypatch, tmp_path) -> None:
        token = "ghs_secret_installation_token"
        token_user = "x-access" + "-token"
        calls: list[tuple[list[str], dict[str, str] | None]] = []

        def fake_run(args, **kwargs):
            calls.append((args, kwargs.get("env")))
            return subprocess.CompletedProcess(args, 0)

        monkeypatch.setattr(app_module.subprocess, "run", fake_run)

        assert app_module._checkout_pr_head(token, "jclee941/propose", "abc123", str(tmp_path)) is True
        joined_args = " ".join(" ".join(args) for args, _env in calls)
        assert token not in joined_args
        assert token_user not in joined_args
        assert "https://github.com/jclee941/propose.git" in joined_args
        fetch_env = calls[1][1]
        assert fetch_env is not None
        assert fetch_env["GIT_ASKPASS_USERNAME"] == token_user
        assert fetch_env["GIT_ASKPASS_PASSWORD"] == token
