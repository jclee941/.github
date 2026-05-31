"""Workflow policy tests for .github/workflows/*.yml files.

These tests validate workflow structure and policy compliance WITHOUT
editing the workflow files or making network calls.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Root of the repo (parent of .github/)
REPO_ROOT = Path(__file__).resolve().parents[2]  # /home/jclee/dev/.github
WF_DIR = REPO_ROOT / ".github" / "workflows"
assert WF_DIR.exists(), f"Workflows dir not found: {WF_DIR}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_workflow(name: str) -> str:
    """Return raw text of a workflow file.

    Workflow files carry an ``NN_`` sequential-numbering prefix (e.g.
    ``34_auto-deploy.yml``). Callers pass the logical name (``auto-deploy.yml``)
    and this resolves the prefixed file so the policy tests stay stable across
    re-numbering.
    """
    path = WF_DIR / name
    if not path.exists():
        matches = sorted(WF_DIR.glob(f"[0-9][0-9]_{name}"))
        if matches:
            path = matches[0]
    if not path.exists():
        pytest.fail(f"Workflow not found: {path}")
    return path.read_text()


# ---------------------------------------------------------------------------
# T4 – Auto-deploy failure issue lifecycle
# ---------------------------------------------------------------------------

class TestAutoDeployFailureIssueLifecycle:
    """
    Validates two properties about the auto-deploy / issue-failure pipeline:

    1. auto-deploy.yml must NOT contain a direct `gh issue create` step.
       (Such logic has been offloaded to ci-failure-issues.yml to avoid
        duplicate issues #18 and #29.)

    2. ci-failure-issues.yml must watch "Auto Deploy Workflows" and have
       exact-title-match deduplication.
    """

    def test_auto_deploy_does_not_directly_create_issues(self):
        """auto-deploy.yml should NOT run `gh issue create` directly.

        Failure-issue creation is handled by ci-failure-issues.yml via
        workflow_run trigger. Direct gh issue create in auto-deploy
        produced duplicate issues #18 and #29.
        """
        text = read_workflow("auto-deploy.yml")

        # This snippet makes up the gh issue create step in auto-deploy.
        # The fix removes that step entirely.
        forbidden_snippet = "gh issue create --repo ${{ github.repository }}"
        assert (
            forbidden_snippet not in text
        ), (
            "auto-deploy.yml still contains direct `gh issue create` step; "
            "this creates duplicate issues. "
            "Offload failure-issue creation to ci-failure-issues.yml."
        )

    def test_ci_failure_issues_watches_auto_deploy(self):
        """ci-failure-issues.yml must listen to 'Auto Deploy Workflows'."""
        text = read_workflow("ci-failure-issues.yml")

        assert '"Auto Deploy Workflows"' in text, (
            "ci-failure-issues.yml must watch 'Auto Deploy Workflows' "
            "in its workflow_run trigger"
        )

    def test_ci_failure_issues_has_exact_title_deduplication(self):
        """ci-failure-issues.yml must dedupe by exact title, not substring."""
        text = read_workflow("ci-failure-issues.yml")

        # The --jq filter must use select(.title == "$TITLE") for exact match.
        # Substring match like :~ would produce false positives.
        assert "select(.title ==" in text, (
            "ci-failure-issues.yml must use exact title comparison",
        )

        # The title pattern must be specific enough for stable dedup
        assert '"[ci] $WF_NAME failed at' in text, (
            "ci-failure-issues.yml title prefix must include "
            '"[ci] $WF_NAME failed at" for stable deduplication'
        )


# ---------------------------------------------------------------------------
# T5 – Build workflow policy
# ---------------------------------------------------------------------------

class TestBuildWorkflowPolicy:
    """
    Validates build-and-push-app.yml registry handling:

    - Must have an explicit registry reachability check step.
    - Build step must be conditional on `reachable == 'true'`.
    - Must handle unreachable registry explicitly (no silent continue).
    """

    def test_has_registry_check_step(self):
        """build-and-push-app.yml must have a registry reachability step."""
        text = read_workflow("build-and-push-app.yml")

        assert "registry_check" in text, (
            "build-and-push-app.yml must have a registry_check step"
        )
        assert "curl" in text and "registry.jclee.me" in text, (
            "registry_check step must actually probe registry.jclee.me"
        )

    def test_build_conditional_on_reachable(self):
        """Build and push must only run when registry is reachable."""
        text = read_workflow("build-and-push-app.yml")

        assert (
            "if: steps.registry_check.outputs.reachable == 'true'" in text
        ), (
            "docker build-push step must be conditional on "
            "steps.registry_check.outputs.reachable == 'true'"
        )

    def test_handles_unreachable_registry(self):
        """Workflow must handle unreachable registry explicitly."""
        text = read_workflow("build-and-push-app.yml")

        # The registry_check step announces when unreachable so runners are not misled
        assert (
            "reachable=false" in text
            and "unreachable" in text.lower()
        ), (
            "build-and-push-app.yml must explicitly announce "
            "when registry is unreachable from this runner"
        )


# ---------------------------------------------------------------------------
# Sanity workflow basic
# ---------------------------------------------------------------------------

class TestSanityWorkflow:
    """
    Validates sanity.yml runs the required smoke tests.
    """

    def test_runs_pytest(self):
        """sanity.yml must invoke pytest."""
        text = read_workflow("sanity.yml")

        assert "pytest" in text, (
            "sanity.yml must run pytest"
        )

    def test_smoke_test_is_included(self):
        """sanity.yml must run the minimum smoke test file."""
        text = read_workflow("sanity.yml")

        # AGENTS.md minimum gate: test_fix_json_escape_char.py
        assert "test_fix_json_escape_char.py" in text, (
            "sanity.yml must run "
            "tests/unittest/test_fix_json_escape_char.py "
            "as the minimum smoke test gate (AGENTS.md)"
        )

    def test_import_check_steps_present(self):
        """sanity.yml must verify core package imports."""
        text = read_workflow("sanity.yml")

        required_imports = [
            "from pr_agent.tools.pr_reviewer import PRReviewer",
            "from pr_agent.tools.pr_description import PRDescription",
            "from pr_agent.tools.pr_code_suggestions import PRCodeSuggestions",
            "from pr_agent.agent.pr_agent import PRAgent",
            "from pr_agent.servers.github_action_runner import run_action",
        ]
        missing = [
            imp for imp in required_imports
            if imp not in text
        ]
        assert not missing, (
            f"sanity.yml is missing import checks for: {missing}"
        )

    def test_toml_config_parsing_present(self):
        """sanity.yml must verify .pr_agent.toml and configuration.toml parse."""
        text = read_workflow("sanity.yml")

        checks = [
            ".pr_agent.toml",
            "pr_agent/settings/configuration.toml",
            "tomllib",
        ]
        missing = [c for c in checks if c not in text]
        assert not missing, (
            f"sanity.yml is missing TOML parsing checks: {missing}"
        )


# ---------------------------------------------------------------------------
# README generator must run on the source repo (jclee941/.github) itself
# ---------------------------------------------------------------------------

class TestReadmeGeneratorOwnRepo:
    """20_readme-gen.yml must keep the source repo's own README current."""

    def test_does_not_skip_source_repo(self):
        """The job must NOT carry a guard that skips jclee941/.github."""
        text = read_workflow("readme-gen.yml")
        assert "github.repository != 'jclee941/.github'" not in text, (
            "20_readme-gen.yml still skips the source repo; the bot can never "
            "auto-update its own README. Remove the repository != guard."
        )

    def test_single_commit_branch_block(self):
        """Only ONE 'git checkout -b bot/auto-readme-update' may exist."""
        text = read_workflow("readme-gen.yml")
        assert text.count("git checkout -b bot/auto-readme-update") == 1, (
            "20_readme-gen.yml has a duplicated commit/push block; "
            "collapse it into a single idempotent push."
        )

    def test_run_blocks_use_set_eu(self):
        """Shell run blocks must use 'set -eu' (not bare 'set -e')."""
        text = read_workflow("readme-gen.yml")
        # No bare 'set -e' line should remain (it must be 'set -eu' or stricter).
        bare = [
            ln for ln in text.splitlines()
            if ln.strip() == "set -e"
        ]
        assert not bare, (
            "20_readme-gen.yml has bare 'set -e' blocks; use 'set -eu'."
        )


# ---------------------------------------------------------------------------
# Template sync must NOT clobber the (LLM-generated) README
# ---------------------------------------------------------------------------

class TestTemplateSyncDoesNotTouchReadme:
    """22_template-sync.yml must sync only CONTRIBUTING.md + LICENSE."""

    def test_no_readme_sparse_checkout(self):
        text = read_workflow("template-sync.yml")
        assert "templates/README.md" not in text, (
            "22_template-sync.yml still sparse-checks-out templates/README.md; "
            "it would clobber the LLM-generated README from 20_readme-gen.yml."
        )

    def test_no_readme_copy(self):
        text = read_workflow("template-sync.yml")
        assert "README.md README.md" not in text and "cp _templates/templates/README.md" not in text, (
            "22_template-sync.yml still copies a static README over the repo README."
        )

    def test_does_not_stage_readme(self):
        text = read_workflow("template-sync.yml")
        # git add must not include README.md anymore.
        add_lines = [ln for ln in text.splitlines() if "git add" in ln]
        for ln in add_lines:
            assert "README.md" not in ln, (
                f"22_template-sync.yml still stages README.md: {ln.strip()}"
            )


# ---------------------------------------------------------------------------
# Auto-merge workflows must self-heal BLOCKED (stale-base) PRs
# ---------------------------------------------------------------------------

class TestAutoMergeSelfHeal:
    """12_dependabot-auto-merge.yml and 13_pr-auto-merge.yml must update
    a stale base branch when GitHub reports mergeStateStatus=BLOCKED while
    checks pass, so required-context drift unblocks itself. They must NEVER
    bypass branch protection with --admin."""

    WORKFLOWS = ["dependabot-auto-merge.yml", "pr-auto-merge.yml"]

    def test_inspects_merge_state_status(self):
        for wf in self.WORKFLOWS:
            text = read_workflow(wf)
            assert "mergeStateStatus" in text, (
                f"{wf} must inspect mergeStateStatus to detect BLOCKED PRs"
            )

    def test_calls_update_branch(self):
        for wf in self.WORKFLOWS:
            text = read_workflow(wf)
            assert "update-branch" in text, (
                f"{wf} must call 'gh pr update-branch' to self-heal stale bases"
            )

    def test_never_uses_admin_bypass(self):
        for wf in self.WORKFLOWS:
            text = read_workflow(wf)
            # Only flag --admin in executable lines, not in explanatory
            # comments like 'We never use --admin'.
            offending = [
                ln for ln in text.splitlines()
                if "--admin" in ln and not ln.lstrip().startswith("#")
            ]
            assert not offending, (
                f"{wf} must NOT use --admin (never bypass branch protection): "
                f"{offending}"
            )
