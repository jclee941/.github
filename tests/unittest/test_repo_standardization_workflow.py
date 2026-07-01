import re

from tests.unittest.workflow_policy_helpers import (
    REPO_ROOT,
)


class TestRepositoryStandardizationWorkflow:
    def test_repository_standardization_workflow_is_retired(self) -> None:
        workflow = REPO_ROOT / ".github" / "workflows" / "18_repo-standardization.yml"

        assert not workflow.exists()

    def test_readme_presents_app_as_repo_policy_rollout_owner(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        forbidden = [
            "Go CLIs reconcile repository policy",
            "Roll out branch protection to managed repos",
            "GitHub Rulesets rollout",
            "Roll out branch protection rules across managed repos",
            "GitHub Rulesets rollout and drift correction",
            "active workflows delegate branch protection and Rulesets reconciliation",
            "`config/repos.yaml`의 저장소 row를 종단(end-to-end)으로 관리하는 `jclee_bot` App 소유 자동화와 **6개의 Go 자동화 CLI**",
        ]
        offenders = [item for item in forbidden if item in readme]

        assert "Repository standardization | `jclee-bot` App" in readme
        assert not re.search(r"Go automation CLIs[^\n.]+(?:manage|end-to-end)", readme)
        assert not re.search(r"Go 자동화 CLI[^\n.]+(?:관리|종단|end-to-end)", readme)
        assert not re.search(r"종단\(end-to-end\)으로 관리[^\n.]+Go 자동화 CLI", readme)
        assert not offenders, f"README must not describe legacy Go CLIs as the policy rollout owner: {offenders}"

    def test_source_repo_does_not_reference_retired_standardization_workflow(self) -> None:
        source_paths = [
            REPO_ROOT / "README.md",
            REPO_ROOT / "docs" / "git-automation-masterplan.md",
            REPO_ROOT / "docs" / "automation-enhancement-brainstorm.md",
            REPO_ROOT / "scripts" / "AGENTS.md",
        ]
        offenders = [
            path.relative_to(REPO_ROOT).as_posix()
            for path in source_paths
            if "18_repo-standardization.yml" in path.read_text(encoding="utf-8")
        ]

        assert not offenders

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
