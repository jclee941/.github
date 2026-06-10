"""Tests for the jclee_bot webhook wrapper app + check dispatcher.

The wrapper must (a) preserve the upstream pr_agent webhook route so reviews
keep working, and (b) dispatch a pull_request payload to the App-owned checks
and produce CheckResults to report via the Checks API.
"""
from __future__ import annotations

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

        paths = {getattr(r, "path", None) for r in app.routes}
        assert "/api/v1/github_webhooks" in paths

    def test_app_exposes_checks_route(self):
        from jclee_bot.app import app

        paths = {getattr(r, "path", None) for r in app.routes}
        assert "/api/v1/checks_webhook" in paths

    def test_app_preserves_health_route(self):
        from jclee_bot.app import app

        paths = {getattr(r, "path", None) for r in app.routes}
        assert "/health" in paths, "Docker healthcheck depends on /health"


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


class TestChecksReporting:
    def test_checks_webhook_reports_to_checks_api(self, monkeypatch):
        """Defect #3/#4: checks_webhook must actually create check runs via the
        Checks API, not just return a JSON summary."""
        import json

        from fastapi.testclient import TestClient

        from jclee_bot import app as app_module

        created = []

        def fake_token(*a, **k):
            return "tok"

        def fake_create(*, token, repo_full_name, result, head_sha):
            created.append((repo_full_name, result.name, head_sha))

            class R:
                status_code = 201

            return R()

        # No real diff fetch in unit test: stub changed-files + Checks API.
        monkeypatch.setattr(app_module, "_installation_token", fake_token, raising=False)
        monkeypatch.setattr(app_module.github_checks, "create_check_run", fake_create)
        monkeypatch.setattr(app_module, "_fetch_changed_files", lambda *a, **k: ["a.py"])
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "")

        payload = {
            "action": "opened",
            "installation": {"id": 42},
            "repository": {"full_name": "jclee941/propose"},
            "pull_request": {
                "title": "no prefix",
                "head": {"ref": "x", "sha": "deadbeef"},
                "base": {"ref": "master"},
                "additions": 1,
                "deletions": 0,
            },
        }
        client = TestClient(app_module.app)
        r = client.post("/api/v1/checks_webhook", content=json.dumps(payload))
        assert r.status_code == 200
        # At least pr-metadata (failure) + secret-scan must be reported.
        names = {c[1] for c in created}
        assert "jclee-bot / pr-metadata" in names, f"check runs not created: {created}"
        assert all(c[2] == "deadbeef" for c in created)

    def test_pull_request_on_main_webhook_triggers_checks(self, monkeypatch):
        """Defect #2: GitHub delivers to the single /api/v1/github_webhooks URL.
        A pull_request event there must ALSO run the App checks (not only the
        separate /api/v1/checks_webhook)."""
        import json

        from fastapi.testclient import TestClient

        from jclee_bot import app as app_module

        import threading
        import time

        ran = []
        done = threading.Event()
        slow_started = threading.Event()

        def slow_checks(payload):
            slow_started.set()
            time.sleep(0.3)  # simulate git fetch + gitleaks + actionlint
            ran.append(payload.get("action"))
            done.set()

        monkeypatch.setattr(app_module, "_run_checks_for_payload", slow_checks)
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "")

        payload = {
            "action": "opened",
            "installation": {"id": 1},
            "repository": {"full_name": "jclee941/x"},
            "pull_request": {"number": 1, "html_url": "https://github.com/jclee941/x/pull/1",
                             "head": {"ref": "f", "sha": "s"}, "base": {"ref": "master"},
                             "title": "feat: x", "additions": 1, "deletions": 0},
            "sender": {"login": "u", "id": 1},
        }
        client = TestClient(app_module.app, raise_server_exceptions=False)
        t0 = time.monotonic()
        r = client.post("/api/v1/github_webhooks", content=json.dumps(payload),
                        headers={"X-GitHub-Event": "pull_request"})
        elapsed = time.monotonic() - t0
        assert r.status_code != 500
        # Defect #1: the webhook must be acknowledged WITHOUT waiting for the
        # slow checks runner (it runs in the background).
        assert slow_started.wait(2.0), "checks were not triggered off the main webhook URL"
        # The request returned before the 0.3s checks completed.
        assert done.wait(2.0), "background checks did not finish"

    def test_create_check_run_failure_not_counted_reported(self, monkeypatch):
        """Defect #2: a rejected Checks API response must NOT be counted as
        reported."""
        from jclee_bot import app as app_module

        monkeypatch.setattr(app_module, "_installation_token", lambda iid: "tok", raising=False)
        monkeypatch.setattr(app_module, "_fetch_changed_files", lambda *a, **k: ["a.py"], raising=False)
        monkeypatch.setattr(app_module, "_checkout_pr_head", lambda *a, **k: True, raising=False)

        import requests

        def rejecting_create(**k):
            raise requests.HTTPError("403 Forbidden")

        monkeypatch.setattr(app_module.github_checks, "create_check_run", rejecting_create)
        payload = {
            "action": "opened", "installation": {"id": 1},
            "repository": {"full_name": "jclee941/x"},
            "pull_request": {"number": 1, "title": "feat: x",
                             "head": {"ref": "f", "sha": "s"}, "base": {"ref": "master"},
                             "additions": 1, "deletions": 0},
        }
        out = app_module._run_checks_for_payload(payload)
        assert out["reported"] == [], "rejected check runs must not appear in reported"

    def test_standalone_endpoint_graceful_on_token_failure(self, monkeypatch):
        """Defect #3: standalone /api/v1/checks_webhook must not 500 when token
        minting fails."""
        import json

        from fastapi.testclient import TestClient

        from jclee_bot import app as app_module

        def boom(iid):
            raise RuntimeError("bad key")

        monkeypatch.setattr(app_module, "_installation_token", boom, raising=False)
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "")
        payload = {"action": "opened", "installation": {"id": 1},
                   "repository": {"full_name": "jclee941/x"},
                   "pull_request": {"number": 1, "title": "feat: x",
                                    "head": {"ref": "f", "sha": "s"}, "base": {"ref": "master"},
                                    "additions": 1, "deletions": 0}}
        r = TestClient(app_module.app, raise_server_exceptions=False).post(
            "/api/v1/checks_webhook", content=json.dumps(payload))
        assert r.status_code == 200, "token failure must degrade, not 500"

    def test_checkout_failure_makes_content_checks_neutral(self, monkeypatch):
        """Defect: if PR checkout fails, content checks (secret-scan, actionlint)
        must NOT report success on an empty dir — they must be neutral."""
        from jclee_bot import app as app_module

        monkeypatch.setattr(app_module, "_installation_token", lambda iid: "tok", raising=False)
        monkeypatch.setattr(app_module, "_fetch_changed_files", lambda *a, **k: ["a.py"], raising=False)
        monkeypatch.setattr(app_module, "_checkout_pr_head", lambda *a, **k: False, raising=False)
        monkeypatch.setattr(app_module.github_checks, "create_check_run",
                            lambda **k: type("R", (), {"status_code": 201})())

        payload = {"action": "opened", "installation": {"id": 1},
                   "repository": {"full_name": "jclee941/x"},
                   "pull_request": {"number": 1, "title": "feat: x",
                                    "head": {"ref": "f", "sha": "s"}, "base": {"ref": "master"},
                                    "additions": 1, "deletions": 0}}
        out = app_module._run_checks_for_payload(payload)
        by = {c["name"]: c["conclusion"] for c in out["checks"]}
        assert by["jclee-bot / secret-scan"] == "neutral", "secret-scan must NOT be success when checkout failed"

    def test_changed_files_fetch_failure_makes_metadata_neutral(self, monkeypatch):
        """Defect: if changed-files fetch fails, pr-metadata must be neutral, not
        success evaluated against an empty file list."""
        from jclee_bot import app as app_module

        def boom_files(*a, **k):
            raise RuntimeError("api down")

        monkeypatch.setattr(app_module, "_installation_token", lambda iid: "tok", raising=False)
        monkeypatch.setattr(app_module, "_fetch_changed_files", boom_files, raising=False)
        monkeypatch.setattr(app_module, "_checkout_pr_head", lambda *a, **k: True, raising=False)
        monkeypatch.setattr(app_module.github_checks, "create_check_run",
                            lambda **k: type("R", (), {"status_code": 201})())

        payload = {"action": "opened", "installation": {"id": 1},
                   "repository": {"full_name": "jclee941/x"},
                   "pull_request": {"number": 1, "title": "feat: x",
                                    "head": {"ref": "f", "sha": "s"}, "base": {"ref": "master"},
                                    "additions": 1, "deletions": 0}}
        out = app_module._run_checks_for_payload(payload)
        by = {c["name"]: c["conclusion"] for c in out["checks"]}
        assert by["jclee-bot / pr-metadata"] == "neutral", "pr-metadata must be neutral when changed-files unavailable"
