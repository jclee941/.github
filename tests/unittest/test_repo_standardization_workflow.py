from __future__ import annotations

import os
import re
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

    def test_readme_presents_app_as_repo_policy_rollout_owner(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        forbidden = [
            "Go CLIs reconcile repository policy",
            "Roll out branch protection to managed repos",
            "GitHub Rulesets rollout",
            "Roll out branch protection rules across managed repos",
            "GitHub Rulesets rollout and drift correction",
            "`config/repos.yaml`의 저장소 row를 종단(end-to-end)으로 관리하는 `jclee_bot` App 소유 자동화와 **6개의 Go 자동화 CLI**",
        ]
        offenders = [item for item in forbidden if item in readme]

        assert "Repository standardization | `jclee-bot` App" in readme
        assert not re.search(r"Go automation CLIs[^\n.]+(?:manage|end-to-end)", readme)
        assert not re.search(r"Go 자동화 CLI[^\n.]+(?:관리|종단|end-to-end)", readme)
        assert not re.search(r"종단\(end-to-end\)으로 관리[^\n.]+Go 자동화 CLI", readme)
        assert not offenders, f"README must not describe legacy Go CLIs as the policy rollout owner: {offenders}"

    def test_docs_lock_policy_rollout_to_app_not_go_clis(self) -> None:
        docs: dict[str, list[str]] = {
            "README.md": [
                "Repository standardization | `jclee-bot` App",
                "production policy rollout is not driven by workflow-side Go execution",
            ],
            "docs/git-automation-masterplan.md": [
                "Production branch protection and Rulesets rollout must stay App-owned",
                "Branch protection diagnostics",
                "Rulesets diagnostics",
            ],
            "docs/automation-enhancement-brainstorm.md": [
                "production standardization is App-owned",
                "Go diagnostic dry-run",
            ],
            "scripts/AGENTS.md": [
                "production repository standardization is owned by the App endpoint",
                "Never add workflow-side `go run ./cmd/branch-protection`",
            ],
        }
        combined: list[str] = []
        for relative_path, required in docs.items():
            text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
            combined.append(text)
            missing = [item for item in required if item not in text]
            assert not missing, f"{relative_path} is missing App-owned rollout wording: {missing}"

        all_docs = "\n".join(combined)
        forbidden = [
            "Branch protection rollout | `scripts/cmd/branch-protection`",
            "Rulesets rollout | `scripts/cmd/rulesets-manager`",
            "Apply branch protection + auto-merge",
            "Manage GitHub Rulesets (list/apply/delete)",
            "go run ./cmd/branch-protection           # apply",
        ]
        offenders = [item for item in forbidden if item in all_docs]

        assert not offenders, f"docs must not present Go CLIs as production policy rollout owners: {offenders}"

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
