from __future__ import annotations

import os
from pathlib import Path

from tests.unittest.workflow_policy_helpers import (
    REPO_ROOT,
    run_bash_script,
    step_with_run_containing,
    workflow_job,
    workflow_steps,
)


class TestRepositoryStandardizationWorkflow:
    def test_standardization_is_owned_by_app_endpoint(self) -> None:
        job = workflow_job("repo-standardization.yml", "standardize")
        steps = workflow_steps("repo-standardization.yml", "standardize")
        delegate = step_with_run_containing(steps, "/api/v1/repo_standardization")
        env = job.get("env")
        run = delegate.get("run")

        assert isinstance(env, dict)
        assert env["REPO_STANDARDIZATION_URL"] == "http://127.0.0.1:3001/api/v1/repo_standardization"
        assert isinstance(run, str)
        assert "Repository standardization failed" in run
        assert "timeout=900" in run

    def test_workflow_does_not_run_gitops_go_clis(self) -> None:
        text = "\n".join(str(step.get("run", "")) for step in workflow_steps("repo-standardization.yml", "standardize"))
        forbidden = [
            "go run ./cmd/repo-standardization",
            "go run ./cmd/branch-protection",
            "go run ./cmd/rulesets-manager",
            "/api/v1/repo_metadata",
        ]
        offenders = [item for item in forbidden if item in text]

        assert not offenders, f"repo standardization workflow must delegate to jclee-bot App only: {offenders}"

    def test_workflow_does_not_install_go(self) -> None:
        steps = workflow_steps("repo-standardization.yml", "standardize")
        uses = [str(step.get("uses", "")) for step in steps]

        assert not any("actions/setup-go" in item for item in uses)

    def test_dispatch_repo_input_is_not_executed_in_mode_resolution(self, tmp_path: Path) -> None:
        steps = workflow_steps("repo-standardization.yml", "standardize")
        resolve = next(step for step in steps if step.get("id") == "mode")
        resolve_run = resolve.get("run")
        assert isinstance(resolve_run, str)

        marker = tmp_path / "repo-injection"
        output = tmp_path / "github-output"
        env = os.environ | {
            "GITHUB_OUTPUT": str(output),
            "INPUT_DRY_RUN": "true",
            "INPUT_REPOS": f"tmux; touch {marker}",
            "REPO_STANDARDIZATION_TOKEN_AVAILABLE": "false",
        }

        result = run_bash_script(resolve_run, cwd=REPO_ROOT, env=env)

        assert result.returncode == 0
        assert not marker.exists()
        assert f"repos=tmux; touch {marker}" in output.read_text(encoding="utf-8")
