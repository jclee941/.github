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
