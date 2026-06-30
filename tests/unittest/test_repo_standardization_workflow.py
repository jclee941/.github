from __future__ import annotations

import os
from pathlib import Path

from tests.unittest.workflow_policy_helpers import (
    REPO_ROOT,
    repo_standardization_validation_step,
    run_bash_script,
    step_with_run_containing,
    workflow_job,
    workflow_steps,
)


class TestRepositoryMetadataWorkflow:
    def test_repo_metadata_is_owned_by_app_endpoint(self) -> None:
        job = workflow_job("repo-standardization.yml", "standardize")
        steps = workflow_steps("repo-standardization.yml", "standardize")
        reconcile = step_with_run_containing(steps, "/api/v1/repo_metadata")
        env = job.get("env")
        run = reconcile.get("run")

        assert isinstance(env, dict)
        assert env["REPO_METADATA_TOKEN"] == "${{ secrets.REPO_METADATA_TOKEN }}"
        assert isinstance(run, str)
        assert "/api/v1/repo_metadata" in run
        assert "Repository metadata reconciliation failed" in run

    def test_repo_standardization_rejects_malicious_dispatch_repos_before_mutation(self, tmp_path: Path) -> None:
        steps = workflow_steps("repo-standardization.yml", "standardize")
        resolve = next(step for step in steps if step.get("id") == "mode")
        resolve_run = resolve.get("run")
        assert isinstance(resolve_run, str)

        marker = tmp_path / "repo-injection"
        output = tmp_path / "github-output"
        env = os.environ | {
            "GITHUB_OUTPUT": str(output),
            "GH_PAT_AVAILABLE": "false",
            "INPUT_DRY_RUN": "true",
            "INPUT_REPOS": f"tmux; touch {marker}",
            "REPO_METADATA_TOKEN_AVAILABLE": "false",
        }

        result = run_bash_script(resolve_run, cwd=REPO_ROOT / "scripts", env=env)

        assert result.returncode != 0
        assert not marker.exists()

    def test_repo_standardization_passes_repo_selection_as_single_argv(self, tmp_path: Path) -> None:
        steps = workflow_steps("repo-standardization.yml", "standardize")
        run_docs = repo_standardization_validation_step(steps)
        docs_run = run_docs.get("run")
        assert isinstance(docs_run, str)

        marker = tmp_path / "repo-injection"
        argv_file = tmp_path / "argv.txt"
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        go = bin_dir / "go"
        _ = go.write_text(
            f"#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" > {argv_file}\n",
            encoding="utf-8",
        )
        go.chmod(0o755)

        substituted = docs_run.replace("${{ steps.mode.outputs.dry_run }}", "true").replace(
            "${{ steps.mode.outputs.repos }}",
            f"tmux; touch {marker}",
        )
        env = os.environ | {"PATH": f"{bin_dir}:{os.environ['PATH']}"}

        result = run_bash_script(substituted, cwd=REPO_ROOT / "scripts", env=env)

        assert result.returncode == 0
        assert not marker.exists()
        assert argv_file.read_text(encoding="utf-8").splitlines()[-1] == f"tmux; touch {marker}"
