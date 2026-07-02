from __future__ import annotations


class TestChecksReporting:
    def test_checks_webhook_rejects_unsigned_by_default(self, monkeypatch):
        import json

        from fastapi.testclient import TestClient

        from jclee_bot import app as app_module

        monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
        monkeypatch.delenv("JCLEE_BOT_ALLOW_UNSIGNED_WEBHOOKS", raising=False)
        monkeypatch.setattr(app_module, "_run_checks_for_payload", lambda payload: {"unexpected": payload})

        response = TestClient(app_module.app, raise_server_exceptions=False).post(
            "/api/v1/checks_webhook",
            content=json.dumps({"repository": {"full_name": "jclee941/x"}}),
        )

        assert response.status_code == 401
        assert response.json() == {"error": "invalid signature"}

    def test_main_webhook_does_not_dispatch_unsigned_by_default(self, monkeypatch):
        import json

        from fastapi.testclient import TestClient

        from jclee_bot import app as app_module

        ran = []

        def fake_checks(payload):
            ran.append(payload)
            return {"checks": []}

        monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
        monkeypatch.delenv("JCLEE_BOT_ALLOW_UNSIGNED_WEBHOOKS", raising=False)
        monkeypatch.setattr(app_module, "_run_checks_for_payload", fake_checks)

        response = TestClient(app_module.app, raise_server_exceptions=False).post(
            "/api/v1/github_webhooks",
            content=json.dumps(
                {
                    "action": "opened",
                    "installation": {"id": 1},
                    "repository": {"full_name": "jclee941/x"},
                    "pull_request": {"head": {"sha": "abc"}, "base": {"ref": "master"}},
                }
            ),
            headers={"X-GitHub-Event": "pull_request"},
        )

        assert response.status_code != 500
        assert ran == []

    def test_checks_webhook_reports_to_checks_api(self, monkeypatch):
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

        monkeypatch.setattr(app_module, "_installation_token", fake_token, raising=False)
        monkeypatch.setattr(app_module.github_checks, "create_check_run", fake_create)
        monkeypatch.setattr(app_module, "_fetch_changed_files", lambda *a, **k: ["a.py"])
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "")
        monkeypatch.setenv("JCLEE_BOT_ALLOW_UNSIGNED_WEBHOOKS", "true")

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
        response = client.post("/api/v1/checks_webhook", content=json.dumps(payload))
        assert response.status_code == 200
        names = {item[1] for item in created}
        assert "jclee-bot / pr-metadata" in names, f"check runs not created: {created}"
        assert all(item[2] == "deadbeef" for item in created)

    def test_pull_request_on_main_webhook_triggers_checks(self, monkeypatch):
        import json
        import threading

        from fastapi.testclient import TestClient

        from jclee_bot import app as app_module

        ran = []
        done = threading.Event()
        release_checks = threading.Event()
        request_finished = threading.Event()
        slow_started = threading.Event()
        response_holder = []

        def slow_checks(payload):
            slow_started.set()
            assert release_checks.wait(2.0), "test did not release background check runner"
            ran.append(payload.get("action"))
            done.set()

        monkeypatch.setattr(app_module, "_run_checks_for_payload", slow_checks)
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "")
        monkeypatch.setenv("JCLEE_BOT_ALLOW_UNSIGNED_WEBHOOKS", "true")

        payload = {
            "action": "opened",
            "installation": {"id": 1},
            "repository": {"full_name": "jclee941/x"},
            "pull_request": {
                "number": 1,
                "html_url": "https://github.com/jclee941/x/pull/1",
                "head": {"ref": "f", "sha": "s"},
                "base": {"ref": "master"},
                "title": "feat: x",
                "additions": 1,
                "deletions": 0,
            },
            "sender": {"login": "u", "id": 1},
        }
        client = TestClient(app_module.app, raise_server_exceptions=False)

        def post_webhook():
            response_holder.append(
                client.post(
                    "/api/v1/github_webhooks",
                    content=json.dumps(payload),
                    headers={"X-GitHub-Event": "pull_request"},
                )
            )
            request_finished.set()

        thread = threading.Thread(target=post_webhook)
        thread.start()
        assert slow_started.wait(2.0), "checks were not triggered off the main webhook URL"
        release_checks.set()
        assert done.wait(2.0), "background checks did not finish"
        thread.join(2.0)
        assert request_finished.is_set(), "webhook request did not finish"
        assert response_holder[0].status_code != 500

    def test_create_check_run_failure_not_counted_reported(self, monkeypatch):
        import requests

        from jclee_bot import app as app_module

        monkeypatch.setattr(app_module, "_installation_token", lambda iid: "tok", raising=False)
        monkeypatch.setattr(app_module, "_fetch_changed_files", lambda *a, **k: ["a.py"], raising=False)
        monkeypatch.setattr(app_module, "_checkout_pr_head", lambda *a, **k: True, raising=False)

        def rejecting_create(**k):
            raise requests.HTTPError("403 Forbidden")

        monkeypatch.setattr(app_module.github_checks, "create_check_run", rejecting_create)
        payload = {
            "action": "opened",
            "installation": {"id": 1},
            "repository": {"full_name": "jclee941/x"},
            "pull_request": {
                "number": 1,
                "title": "feat: x",
                "head": {"ref": "f", "sha": "s"},
                "base": {"ref": "master"},
                "additions": 1,
                "deletions": 0,
            },
        }
        out = app_module._run_checks_for_payload(payload)
        assert out["reported"] == [], "rejected check runs must not appear in reported"

    def test_standalone_endpoint_graceful_on_token_failure(self, monkeypatch):
        import json

        from fastapi.testclient import TestClient

        from jclee_bot import app as app_module

        def boom(iid):
            raise RuntimeError("bad key")

        monkeypatch.setattr(app_module, "_installation_token", boom, raising=False)
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "")
        monkeypatch.setenv("JCLEE_BOT_ALLOW_UNSIGNED_WEBHOOKS", "true")
        payload = {
            "action": "opened",
            "installation": {"id": 1},
            "repository": {"full_name": "jclee941/x"},
            "pull_request": {
                "number": 1,
                "title": "feat: x",
                "head": {"ref": "f", "sha": "s"},
                "base": {"ref": "master"},
                "additions": 1,
                "deletions": 0,
            },
        }
        response = TestClient(app_module.app, raise_server_exceptions=False).post(
            "/api/v1/checks_webhook", content=json.dumps(payload)
        )
        assert response.status_code == 200, "token failure must degrade, not 500"

    def test_checkout_failure_makes_content_checks_fail(self, monkeypatch):
        from jclee_bot import app as app_module

        monkeypatch.setattr(app_module, "_installation_token", lambda iid: "tok", raising=False)
        monkeypatch.setattr(app_module, "_fetch_changed_files", lambda *a, **k: ["a.py"], raising=False)
        monkeypatch.setattr(app_module, "_checkout_pr_head", lambda *a, **k: False, raising=False)
        monkeypatch.setattr(
            app_module.github_checks,
            "create_check_run",
            lambda **k: type("R", (), {"status_code": 201})(),
        )

        payload = {
            "action": "opened",
            "installation": {"id": 1},
            "repository": {"full_name": "jclee941/x"},
            "pull_request": {
                "number": 1,
                "title": "feat: x",
                "head": {"ref": "f", "sha": "s"},
                "base": {"ref": "master"},
                "additions": 1,
                "deletions": 0,
            },
        }
        out = app_module._run_checks_for_payload(payload)
        by_name = {check["name"]: check["conclusion"] for check in out["checks"]}
        assert by_name["jclee-bot / secret-scan"] == "failure", "secret-scan must fail when checkout failed"

    def test_changed_files_fetch_failure_makes_metadata_fail(self, monkeypatch):
        from jclee_bot import app as app_module

        def boom_files(*a, **k):
            raise RuntimeError("api down")

        monkeypatch.setattr(app_module, "_installation_token", lambda iid: "tok", raising=False)
        monkeypatch.setattr(app_module, "_fetch_changed_files", boom_files, raising=False)
        monkeypatch.setattr(app_module, "_checkout_pr_head", lambda *a, **k: True, raising=False)
        monkeypatch.setattr(
            app_module.github_checks,
            "create_check_run",
            lambda **k: type("R", (), {"status_code": 201})(),
        )

        payload = {
            "action": "opened",
            "installation": {"id": 1},
            "repository": {"full_name": "jclee941/x"},
            "pull_request": {
                "number": 1,
                "title": "feat: x",
                "head": {"ref": "f", "sha": "s"},
                "base": {"ref": "master"},
                "additions": 1,
                "deletions": 0,
            },
        }
        out = app_module._run_checks_for_payload(payload)
        by_name = {check["name"]: check["conclusion"] for check in out["checks"]}
        assert by_name["jclee-bot / pr-metadata"] == "failure", "pr-metadata must fail when changed-files unavailable"
        assert by_name["jclee-bot / secret-scan"] == "failure", "secret-scan must fail when changed-files unavailable"
        assert by_name["jclee-bot / actionlint"] == "failure", "actionlint must fail when changed-files unavailable"
