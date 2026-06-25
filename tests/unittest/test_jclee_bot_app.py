"""Tests for the jclee_bot webhook wrapper app + check dispatcher.

The wrapper must (a) preserve the upstream pr_agent webhook route so reviews
keep working, and (b) dispatch a pull_request payload to the App-owned checks
and produce CheckResults to report via the Checks API.
"""
from __future__ import annotations

from starlette.routing import Match

from jclee_bot import dispatch


def _pr_payload(*, title="feat: ok", head="feat/x", base="master", files=None,
                additions=5, deletions=1, action="opened"):
    return {
        "action": action,
        "pull_request": {
            "title": title,
            "head": {"ref": head, "sha": "abc123"},
            "base": {"ref": base},
            "additions": additions,
            "deletions": deletions,
        },
        "repository": {"full_name": "jclee941/propose"},
    }


def _app_matches_path(app, path: str, method: str) -> bool:
    scope = {"type": "http", "path": path, "method": method, "root_path": "", "headers": []}
    return any(route.matches(scope)[0] is Match.FULL for route in app.router.routes)


class TestDispatch:
    def test_pull_request_opened_produces_metadata_check(self):
        results = dispatch.run_checks(
            _pr_payload(),
            changed_files=["a.py"],
            workspace="/nonexistent",
        )
        names = {r.name for r in results}
        assert "jclee-bot / pr-metadata" in names
        assert "jclee-bot / secret-scan" in names
        assert "jclee-bot / docs-policy" in names

    def test_metadata_failure_propagates(self):
        results = dispatch.run_checks(
            _pr_payload(title="no prefix here"),
            changed_files=["a.py"],
            workspace="/nonexistent",
        )
        meta = next(r for r in results if r.name == "jclee-bot / pr-metadata")
        assert meta.conclusion == "failure"

    def test_actionlint_only_on_workflow_change(self):
        no_wf = dispatch.run_checks(
            _pr_payload(), changed_files=["a.py"], workspace="/nonexistent"
        )
        al = next(r for r in no_wf if r.name == "jclee-bot / actionlint")
        assert al.conclusion == "neutral"

    def test_head_sha_extracted(self):
        assert dispatch.head_sha(_pr_payload()) == "abc123"

    def test_non_pr_action_yields_no_checks(self):
        results = dispatch.run_checks(
            {"action": "labeled", "repository": {}},
            changed_files=[],
            workspace="/x",
        )
        assert results == []


class TestWrapperApp:
    def test_app_preserves_upstream_webhook_route(self):
        from jclee_bot.app import app

        assert _app_matches_path(app, "/api/v1/github_webhooks", "POST")

    def test_app_exposes_checks_route(self):
        from jclee_bot.app import app

        assert _app_matches_path(app, "/api/v1/checks_webhook", "POST")

    def test_app_exposes_readme_automation_route(self):
        from jclee_bot.app import app

        assert _app_matches_path(app, "/api/v1/readme_automation", "POST")

    def test_app_preserves_health_route(self):
        from jclee_bot.app import app

        assert _app_matches_path(app, "/health", "GET"), "Docker healthcheck depends on /health"

    def test_create_event_on_main_webhook_triggers_gitops_automation(self, monkeypatch):
        import json
        import threading

        from fastapi.testclient import TestClient

        from jclee_bot import app as app_module

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

        r = TestClient(app_module.app, raise_server_exceptions=False).post(
            "/api/v1/github_webhooks",
            content=json.dumps(payload),
            headers={"X-GitHub-Event": "create"},
        )

        assert r.status_code != 500
        assert done.wait(2.0), "GitOps automation did not run for create webhook"
        assert ran == [("create", "fix/issue-7-broken-ci")]

    def test_labeled_pull_request_on_main_webhook_triggers_gitops_auto_merge(self, monkeypatch):
        import json
        import threading

        from fastapi.testclient import TestClient

        from jclee_bot import app as app_module

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

        r = TestClient(app_module.app, raise_server_exceptions=False).post(
            "/api/v1/github_webhooks",
            content=json.dumps(payload),
            headers={"X-GitHub-Event": "pull_request"},
        )

        assert r.status_code != 500
        assert done.wait(2.0), "GitOps auto-merge did not run for labeled pull_request webhook"
        assert ran == [("pull_request", "labeled", "auto-merge")]


class TestGithubChecksPayload:
    def test_check_run_payload_maps_fields(self):
        from jclee_bot import github_checks
        from jclee_bot.checks import CheckResult

        r = CheckResult(name="jclee-bot / pr-metadata", conclusion="failure",
                        title="bad", summary="details")
        body = github_checks.check_run_payload(r, "deadbeef")
        assert body["name"] == "jclee-bot / pr-metadata"
        assert body["head_sha"] == "deadbeef"
        assert body["status"] == "completed"
        assert body["conclusion"] == "failure"
        assert body["output"]["title"] == "bad"
        assert body["output"]["summary"] == "details"

    def test_app_has_raw_context_middleware(self):
        """Defect #1: the wrapper must keep the upstream RawContextMiddleware so
        the /api/v1/github_webhooks review path does not 500."""
        from starlette_context.middleware import RawContextMiddleware

        from jclee_bot.app import app

        classes = [m.cls for m in app.user_middleware]
        assert RawContextMiddleware in classes, "RawContextMiddleware missing -> review path 500s"
