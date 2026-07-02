"""Workflow policy tests for .github/workflows/*.yml files.

These tests validate workflow structure and policy compliance WITHOUT
editing the workflow files or making network calls.
"""

from __future__ import annotations

from pathlib import Path

from tests.unittest.workflow_policy_helpers import (
    REPO_ROOT,
    WF_DIR,
    read_app_source,
    read_workflow,
    read_workflow_issue_automation_source,
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

        assert "registry_check" in text, "build-and-push-app.yml must have a registry_check step"
        assert "curl" in text and "registry.jclee.me" in text, (
            "registry_check step must actually probe registry.jclee.me"
        )

    def test_build_conditional_on_reachable(self):
        """Build and push must only run when registry is reachable."""
        text = read_workflow("build-and-push-app.yml")

        assert "if: steps.registry_check.outputs.reachable == 'true'" in text, (
            "docker build-push step must be conditional on steps.registry_check.outputs.reachable == 'true'"
        )

    def test_handles_unreachable_registry(self):
        """Workflow must handle unreachable registry explicitly."""
        text = read_workflow("build-and-push-app.yml")

        # The registry_check step announces when unreachable so runners are not misled
        assert "reachable=false" in text and "unreachable" in text.lower(), (
            "build-and-push-app.yml must explicitly announce when registry is unreachable from this runner"
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

        assert "pytest" in text, "sanity.yml must run pytest"

    def test_smoke_test_is_included(self):
        """sanity.yml must run the minimum smoke test file."""
        text = read_workflow("sanity.yml")

        # AGENTS.md minimum gate: test_fix_json_escape_char.py
        assert "test_fix_json_escape_char.py" in text, (
            "sanity.yml must run tests/unittest/test_fix_json_escape_char.py as the minimum smoke test gate (AGENTS.md)"
        )

    def test_import_check_steps_present(self):
        """sanity.yml must verify core package imports."""
        text = read_workflow("sanity.yml")

        required_imports = [
            "from jclee_bot.review_engine.tools.pr_reviewer import PRReviewer",
            "from jclee_bot.review_engine.tools.pr_description import PRDescription",
            "from jclee_bot.review_engine.tools.pr_code_suggestions import PRCodeSuggestions",
            "from jclee_bot.review_engine.agent.pr_agent import PRAgent",
            "from jclee_bot.review_engine.servers.github_action_runner import run_action",
        ]
        missing = [imp for imp in required_imports if imp not in text]
        assert not missing, f"sanity.yml is missing import checks for: {missing}"

    def test_toml_config_parsing_present(self):
        """sanity.yml must verify .pr_agent.toml and configuration.toml parse."""
        text = read_workflow("sanity.yml")

        checks = [
            ".pr_agent.toml",
            "jclee_bot/review_engine/settings/configuration.toml",
            "tomllib",
        ]
        missing = [c for c in checks if c not in text]
        assert not missing, f"sanity.yml is missing TOML parsing checks: {missing}"


# ---------------------------------------------------------------------------
class TestReadmeAutomationOwnedByApp:
    def test_readme_generator_workflow_removed(self):
        assert not (WF_DIR / "20_readme-gen.yml").exists()
        assert not list(WF_DIR.glob("[0-9][0-9]_readme-gen.yml"))

    def test_app_worker_owns_readme_branch_and_pr_flow(self):
        router_text = (REPO_ROOT / "jclee_bot" / "readme_automation.py").read_text(encoding="utf-8")
        runner_text = (REPO_ROOT / "jclee_bot" / "readme_runner.py").read_text(encoding="utf-8")
        assert "/api/v1/readme_automation" in router_text
        assert "bot/auto-readme-update" in runner_text
        assert "enablePullRequestAutoMerge" in runner_text

    def test_event_workflow_triggers_app_readme_automation(self):
        text = read_workflow("readme-automation.yml")
        assert 'workflows: ["Sanity"]' in text
        assert "repository_dispatch:" in text
        assert "readme-automation" in text
        assert "workflow_dispatch:" in text
        assert "/api/v1/readme_automation" in text
        assert ".accepted == true" in text
        assert '"${status}" = "completed"' in text
        assert "APP_ISSUE_MAINTENANCE_TOKEN" in text

    def test_app_image_contains_readme_helpers(self):
        text = (REPO_ROOT / "Dockerfile.github_app").read_text(encoding="utf-8")
        assert "COPY scripts/*.py scripts/" in text


class TestIssueMaintenanceWorkflow:
    def test_cleanup_is_not_owned_by_workflow(self):
        assert not list(WF_DIR.glob("[0-9][0-9]_issue-maintenance.yml"))


class TestNativeHealthWorkflowPolicy:
    def test_health_workflows_delegate_to_jclee_bot(self):
        for workflow in [
            "elk-health-check.yml",
            "elk-setup.yml",
            "bot-health-monitor.yml",
            "runtime-health-check.yml",
        ]:
            text = read_workflow(workflow)
            assert "/api/v1/native_health" in text
            assert "NATIVE_HEALTH_TOKEN" in text
            assert "ISSUE_COMMANDS_TOKEN" not in text
            assert "/_cluster/health" not in text
            assert "/_cat/indices" not in text

    def test_native_health_workflows_surface_bot_response_summary(self):
        for workflow in ["bot-health-monitor.yml", "runtime-health-check.yml"]:
            text = read_workflow(workflow)
            assert 'response="$(curl -fsS --retry 3 --retry-delay 5 --max-time 180 \\' in text
            assert "Native health::\\(.name) \\(.status): \\(.summary)" in text
            assert "Native health issue actions::\\(.issue_error)" in text

    def test_elk_workflows_pass_secrets_only_to_jclee_bot(self):
        for workflow in ["elk-health-check.yml", "elk-setup.yml"]:
            text = read_workflow(workflow)
            assert "ELK_HOST" in text
            assert "elk_host: $elk_host" in text
            assert "curl -fsS --retry 3 --retry-delay 5 --max-time 180 \\" in text

    def test_bot_health_workflow_keeps_secret_lookup_in_jclee_bot(self):
        text = read_workflow("bot-health-monitor.yml")
        assert "CLIPROXY_API_KEY" not in text
        assert '{repository: $repo, checks: ["bot_health"]}' in text

    def test_build_pushes_rename_compatibility_tag(self):
        text = read_workflow("build-and-push-app.yml")
        assert "registry.jclee.me/jclee-bot-app:latest" in text
        assert "registry.jclee.me/github-bot-app:latest" in text


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Auto-recovery: stale failure/health issues self-close when workflow recovers
# ---------------------------------------------------------------------------


class TestStaleFailureIssueAutoRecovery:
    """Failure/health issues created by scheduled workflows (Runtime
    Health, ELK Health, Downstream Health, Bot Health, ELK Setup) must
    auto-close when their originating workflow recovers; no
    manual cleanup. The GitHub App webhook path is the centralized recovery
    mechanism; do not restore a CI-failure GitHub Actions caller."""

    def test_ci_failure_workflow_caller_is_removed(self):
        assert not (WF_DIR / "37_ci-failure-issues.yml").exists()
        assert not list(WF_DIR.glob("[0-9][0-9]_ci-failure-issues.yml"))

    def test_app_webhook_owns_workflow_run_recovery(self):
        text = read_app_source()
        assert 'CI_FAILURE_EVENTS = frozenset({"workflow_run"})' in text
        assert "_run_event_ci_failure_issues" in text
        assert "run_in_executor(None, _run_event_ci_failure_issues, payload, event)" in text
        assert "_run_app_ci_failure_issues" in text

    def test_app_maps_health_workflow_titles_for_recovery(self):
        text = read_workflow_issue_automation_source()
        for sub in [
            "ELK Health Check Failed",
            "ELK Setup Failed",
            "CLIProxyAPI unreachable",
            "Downstream workflow failures detected",
            "Bot Health Monitor failed",
        ]:
            assert sub in text, (
                f"jclee-bot event-driven success path must close issues titled '{sub}' when the workflow recovers."
            )

    def test_no_ci_failure_workflow_shell_mutations_remain(self):
        offenders: list[str] = []
        for path in WF_DIR.glob("*.yml"):
            text = path.read_text(encoding="utf-8")
            if "/api/v1/ci_failure_issues" in text or "CI_FAILURE_ISSUES_TOKEN" in text:
                offenders.append(path.name)
        assert not offenders, f"CI-failure automation must be App-native, not workflow-triggered: {offenders}"

    def test_sweep_queries_workflow_run_conclusion(self):
        text = read_workflow_issue_automation_source()
        # The sweep must determine recovery by querying the originating
        # workflow's latest run conclusion (success) via the Actions API,
        # not by guessing.
        assert "actions/workflows" in text or "/runs" in text, (
            "jclee-bot sweep must query the workflow's run "
            "conclusion (gh api .../actions/workflows/.../runs) to decide "
            "whether a stale failure issue can be auto-closed."
        )
        assert "conclusion" in text, "sweep must check run conclusion == success before closing."


class TestNotifyFailureTitlesAreStable:
    """notify-on-failure dedupes by EXACT title, so callers must use a STABLE
    title (no ${{ github.run_id }}); otherwise every run gets a unique title
    and a new duplicate issue is created (the spam I had to clean up manually).
    """

    def test_no_run_id_in_notify_titles(self):
        import glob

        offenders: list[str] = []
        for path in glob.glob(str(WF_DIR / "*.yml")) + glob.glob(str(WF_DIR / "**" / "*.yml")):
            text = Path(path).read_text()
            # Look at notify-on-failure title inputs that embed a run id.
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("title:") and ("github.run_id" in stripped or "RUN_ID" in stripped):
                    offenders.append(f"{Path(path).name}: {stripped}")
        assert not offenders, (
            f"notify-on-failure titles must be stable (no run_id) so dedup works; offenders: {'; '.join(offenders)}"
        )
