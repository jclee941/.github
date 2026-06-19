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
    ``30_runtime-health-check.yml``). Callers pass the logical name
    (``runtime-health-check.yml``) and this resolves the prefixed file so
    the policy tests stay stable across re-numbering.
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
class TestReadmeAutomationOwnedByApp:
    def test_readme_generator_workflow_removed(self):
        assert not (WF_DIR / "20_readme-gen.yml").exists()
        assert not list(WF_DIR.glob("[0-9][0-9]_readme-gen.yml"))

    def test_app_worker_owns_readme_branch_and_pr_flow(self):
        text = (REPO_ROOT / "jclee_bot" / "readme_automation.py").read_text(encoding="utf-8")
        assert "/api/v1/readme_automation" in text
        assert "bot/auto-readme-update" in text
        assert "enablePullRequestAutoMerge" in text

    def test_app_image_contains_readme_helpers(self):
        text = (REPO_ROOT / "Dockerfile.github_app").read_text(encoding="utf-8")
        assert "COPY scripts/*.py scripts/" in text



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



# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Auto-recovery: stale failure/health issues self-close when workflow recovers
# ---------------------------------------------------------------------------

class TestStaleFailureIssueAutoRecovery:
    """Failure/health issues created by scheduled workflows (Runtime
    Health, ELK Health, Downstream Health, Bot Health, CI Auto-Heal, ELK
    Setup) must auto-close when their originating workflow recovers; no
    manual cleanup. ci-failure-issues.yml is the centralized recovery
    mechanism: (1) event-driven on workflow_run success, and (2) a
    manually dispatchable sweep that closes open failure/health issues
    whose workflow's latest master run is green."""

    def test_watches_all_recoverable_workflows(self):
        text = read_workflow("ci-failure-issues.yml")
        # The event-driven workflow_run trigger must cover every health/scan
        # workflow that has a stable-titled failure issue that should
        # auto-close on recovery. Gitleaks / CodeQL / PR Checks / Drift
        # Detector / Auto Deploy are gone (per-repo CI workflows were
        # replaced by the jclee-bot App Checks-API runner).
        for wf in [
            "ELK Health Check",
            "ELK Setup",
            "Runtime Health Check",
            "Downstream Health Check",
            "Bot Health Monitor",
            "CI Auto-Heal",
        ]:
            assert f'"{wf}"' in text, (
                f"ci-failure-issues.yml workflow_run must watch '{wf}' so its "
                "stale failure issue auto-closes on recovery."
            )

    def test_event_driven_close_maps_health_workflow_titles(self):
        text = read_workflow("ci-failure-issues.yml")
        # On workflow_run success, the health/scan workflows' stable issue
        # titles must be closed immediately (event-driven), not only by the
        # daily sweep. Guard that the success path maps these workflow names.
        # Updated to the App-era watch list: Gitleaks is gone (App does
        # secret-scan), CodeQL is GitHub-native, PR Checks and Auto Deploy
        # are gone.
        for sub in [
            "ELK Health Check Failed",
            "ELK Setup Failed",
            "CLIProxyAPI unreachable",
            "Downstream workflow failures detected",
            "Bot Health Monitor failed",
            "CI Auto-Heal failed",
        ]:
            assert sub in text, (
                f"ci-failure-issues.yml event-driven success path must close "
                f"issues titled '{sub}' when the workflow recovers."
            )

    def test_event_driven_cases_are_all_watched(self):
        import re
        text = read_workflow("ci-failure-issues.yml")
        # Every workflow name with an event-driven case "$WF_NAME" mapping must
        # be present in the workflow_run.workflows watch list, otherwise its
        # success never triggers the immediate close.
        m = re.search(
            r'workflow_run:\s*\n\s*workflows:\s*\n((?:\s+- "[^"]+"\n)+)', text
        )
        assert m, "could not find workflow_run.workflows block"
        watched = set(re.findall(r'- "([^"]+)"', m.group(1)))
        cases = set(re.findall(r'"([^"]+)"\)\s*SUBS', text))
        missing = cases - watched
        assert not missing, (
            "event-driven case-mapped workflows missing from workflow_run "
            f"watch list: {sorted(missing)}"
        )

    def test_sweep_is_manually_dispatchable(self):
        text = read_workflow("ci-failure-issues.yml")
        # GitOps automation is event-driven: the periodic cron was removed in
        # favor of workflow_dispatch + the event-driven workflow_run triage path.
        # The stale-issue sweep must remain reachable via manual dispatch.
        assert "schedule:" not in text and "cron:" not in text, (
            "ci-failure-issues.yml must NOT use a cron schedule (event-driven only)."
        )
        assert "workflow_dispatch:" in text, (
            "ci-failure-issues.yml must keep workflow_dispatch so the stale-failure "
            "sweep can be triggered manually."
        )

    def test_sweep_queries_workflow_run_conclusion(self):
        text = read_workflow("ci-failure-issues.yml")
        # The sweep must determine recovery by querying the originating
        # workflow's latest run conclusion (success) via the Actions API,
        # not by guessing.
        assert "actions/workflows" in text or "/runs" in text, (
            "ci-failure-issues.yml sweep must query the workflow's run "
            "conclusion (gh api .../actions/workflows/.../runs) to decide "
            "whether a stale failure issue can be auto-closed."
        )
        assert "conclusion" in text, (
            "sweep must check run conclusion == success before closing."
        )


class TestNotifyFailureTitlesAreStable:
    """notify-on-failure dedupes by EXACT title, so callers must use a STABLE
    title (no ${{ github.run_id }}); otherwise every run gets a unique title
    and a new duplicate issue is created (the spam I had to clean up manually).
    """

    def test_no_run_id_in_notify_titles(self):
        import glob
        offenders = []
        for path in glob.glob(str(WF_DIR / "*.yml")) + glob.glob(
            str(WF_DIR / "**" / "*.yml")
        ):
            text = Path(path).read_text()
            # Look at notify-on-failure title inputs that embed a run id.
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("title:") and (
                    "github.run_id" in stripped or "RUN_ID" in stripped
                ):
                    offenders.append(f"{Path(path).name}: {stripped}")
        assert not offenders, (
            "notify-on-failure titles must be stable (no run_id) so dedup "
            "works; offenders: " + "; ".join(offenders)
        )
