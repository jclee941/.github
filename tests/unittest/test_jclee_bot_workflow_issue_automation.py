from __future__ import annotations

from fastapi.testclient import TestClient

from jclee_bot import workflow_issue_automation


def test_workflow_run_payload_skips_malformed_run_id() -> None:
    from jclee_bot import app as app_module

    for malformed_run_id in ["not-a-number", True, 1.2, float("inf")]:
        payload = {
            "workflow_run": {
                "name": "Sanity",
                "head_sha": "abcdef1234567890abcdef1234567890abcdef12",
                "id": malformed_run_id,
                "conclusion": "failure",
                "pr_number": 4,
                "run_url": "https://github.com/jclee941/.github/actions/runs/not-a-number",
            },
        }

        run = app_module._workflow_run_from_payload(payload)

        assert run is None


def test_workflow_run_payload_defaults_malformed_pr_number() -> None:
    from jclee_bot import app as app_module

    for malformed_pr_number in ["not-a-number", True, 1.2, float("inf")]:
        payload = {
            "workflow_run": {
                "name": "Sanity",
                "head_sha": "abcdef1234567890abcdef1234567890abcdef12",
                "id": 123,
                "conclusion": "failure",
                "pr_number": malformed_pr_number,
                "run_url": "https://github.com/jclee941/.github/actions/runs/123",
            },
        }

        run = app_module._workflow_run_from_payload(payload)

        assert run is not None
        assert run.pr_number == 0


def test_skipped_workflow_run_is_neutral() -> None:
    assert workflow_issue_automation.normalize_conclusion("skipped") == "neutral"


def test_failure_dry_run_reports_ci_issue_creation_without_mutating(monkeypatch) -> None:
    run = workflow_issue_automation.WorkflowRun(
        name="Sanity",
        head_sha="abcdef1234567890abcdef1234567890abcdef12",
        run_id=123,
        conclusion="failure",
        pr_number=0,
        run_url="https://github.com/jclee941/.github/actions/runs/123",
    )
    mutations: list[str] = []

    monkeypatch.setattr(workflow_issue_automation, "_find_issue_by_title", lambda **kwargs: None)
    monkeypatch.setattr(workflow_issue_automation, "_ensure_ci_labels", lambda **kwargs: mutations.append("label"))
    monkeypatch.setattr(workflow_issue_automation, "_create_issue", lambda **kwargs: mutations.append("create") or 9)

    actions = workflow_issue_automation.record_workflow_run(
        token="tok",
        repo_full_name="jclee941/.github",
        run=run,
        dry_run=True,
    )

    assert actions == ["create-ci-failure:[ci] Sanity failed at abcdef12"]
    assert mutations == []


def test_success_closes_recovered_and_sweeps_legacy(monkeypatch) -> None:
    run = workflow_issue_automation.WorkflowRun(
        name="Runtime Health Check",
        head_sha="abcdef1234567890abcdef1234567890abcdef12",
        run_id=123,
        conclusion="success",
        pr_number=0,
        run_url="https://github.com/jclee941/.github/actions/runs/123",
    )

    monkeypatch.setattr(
        workflow_issue_automation,
        "close_recovered_workflow_issues",
        lambda **kwargs: ["close-recovered:7:Runtime Health Check"],
    )
    monkeypatch.setattr(
        workflow_issue_automation,
        "sweep_legacy_failure_issues",
        lambda **kwargs: ["close-legacy:8:30_runtime-health-check.yml"],
    )

    actions = workflow_issue_automation.record_workflow_run(
        token="tok",
        repo_full_name="jclee941/.github",
        run=run,
        dry_run=False,
    )

    assert actions == ["close-recovered:7:Runtime Health Check", "close-legacy:8:30_runtime-health-check.yml"]


def test_ci_failure_endpoint_delegates_to_app_module(monkeypatch) -> None:
    from jclee_bot import app as app_module

    calls: list[dict[str, object]] = []

    def fake_run(**kwargs) -> dict[str, object]:
        calls.append(kwargs)
        return {"dry_run": True, "repository": "jclee941/.github", "actions": ["create-ci-failure:x"]}

    monkeypatch.setenv("CI_FAILURE_ISSUES_TOKEN", "ci")
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "key")
    monkeypatch.setattr(app_module, "_run_app_ci_failure_issues", fake_run)

    response = TestClient(app_module.app, raise_server_exceptions=False).post(
        "/api/v1/ci_failure_issues",
        json={
            "repository": "jclee941/.github",
            "dry_run": True,
            "workflow_run": {
                "name": "Sanity",
                "head_sha": "abcdef1234567890abcdef1234567890abcdef12",
                "id": 123,
                "conclusion": "failure",
                "pr_number": 0,
                "run_url": "https://github.com/jclee941/.github/actions/runs/123",
            },
        },
        headers={"Authorization": "Bearer ci"},
    )

    assert response.status_code == 200
    assert response.json() == {"dry_run": True, "repository": "jclee941/.github", "actions": ["create-ci-failure:x"]}
    assert calls[0]["app_id"] == "123"
    assert calls[0]["private_key"] == "key"


def test_ci_failure_endpoint_handles_malformed_workflow_run_numbers(monkeypatch) -> None:
    from jclee_bot import app as app_module

    monkeypatch.setenv("CI_FAILURE_ISSUES_TOKEN", "ci")
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "key")
    monkeypatch.setattr(workflow_issue_automation, "installation_token_for_repo", lambda **kwargs: "tok")
    monkeypatch.setattr(
        workflow_issue_automation,
        "sweep_legacy_failure_issues",
        lambda **kwargs: ["close-legacy:8:30_runtime-health-check.yml"],
    )

    client = TestClient(app_module.app, raise_server_exceptions=False)
    for malformed_number in [True, 1.2]:
        response = client.post(
            "/api/v1/ci_failure_issues",
            json={
                "repository": "jclee941/.github",
                "dry_run": True,
                "workflow_run": {
                    "name": "Sanity",
                    "head_sha": "abcdef1234567890abcdef1234567890abcdef12",
                    "id": malformed_number,
                    "conclusion": "failure",
                    "pr_number": malformed_number,
                    "run_url": "https://github.com/jclee941/.github/actions/runs/not-a-number",
                },
            },
            headers={"Authorization": "Bearer ci"},
        )

        assert response.status_code == 200
        assert response.json() == {
            "dry_run": True,
            "repository": "jclee941/.github",
            "actions": ["close-legacy:8:30_runtime-health-check.yml"],
        }
