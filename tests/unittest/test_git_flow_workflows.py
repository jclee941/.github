"""Workflow policy tests for .github/workflows/*.yml files.

These tests validate workflow structure and policy compliance WITHOUT
editing the workflow files or making network calls.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import cast

import pytest
import yaml

from jclee_bot.json_boundary import object_dict, object_list

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


def read_workflow_yaml(name: str) -> dict[str, object]:
    parsed = cast(object, yaml.safe_load(read_workflow(name)))
    return object_dict(parsed)


def workflow_job(name: str, job: str) -> dict[str, object]:
    workflow = read_workflow_yaml(name)
    jobs = object_dict(workflow["jobs"])
    return object_dict(jobs[job])


def workflow_steps(name: str, job: str) -> list[dict[str, object]]:
    job_config = workflow_job(name, job)
    steps = object_list(job_config["steps"], "workflow job must contain steps")
    return [object_dict(cast(object, step)) for step in steps if isinstance(step, dict)]


def step_with_run_containing(steps: list[dict[str, object]], text: str) -> dict[str, object]:
    for step in steps:
        run = step.get("run")
        if isinstance(run, str) and text in run:
            return step
    pytest.fail(f"Workflow run step containing {text!r} was not found")


def repo_standardization_validation_step(steps: list[dict[str, object]]) -> dict[str, object]:
    for step in steps:
        run = step.get("run")
        if isinstance(run, str) and "repo-standardization" in run and "--normalize-repos" not in run:
            return step
    pytest.fail("Repository standardization validation step was not found")


def run_bash_script(script: str, *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def read_workflow_issue_automation_source() -> str:
    paths = [
        REPO_ROOT / "jclee_bot" / "workflow_issue_automation.py",
        REPO_ROOT / "jclee_bot" / "workflow_legacy_sweep.py",
        REPO_ROOT / "jclee_bot" / "workflow_current_sweep.py",
    ]
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


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


class TestRepositoryMetadataWorkflow:
    def test_repo_metadata_is_owned_by_app_endpoint(self):
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

    def test_repo_standardization_rejects_malicious_dispatch_repos_before_mutation(self, tmp_path: Path):
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

    def test_repo_standardization_passes_repo_selection_as_single_argv(self, tmp_path: Path):
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
        ]:
            assert f'"{wf}"' in text, (
                f"ci-failure-issues.yml workflow_run must watch '{wf}' so its "
                "stale failure issue auto-closes on recovery."
            )

    def test_workflow_delegates_issue_mutation_to_app(self):
        text = read_workflow("ci-failure-issues.yml")
        assert "/api/v1/ci_failure_issues" in text
        assert "CI_FAILURE_ISSUES_TOKEN" in text
        forbidden = ["gh issue create", "gh issue close", "gh issue comment", "gh label create"]
        offenders = [token for token in forbidden if token in text]
        assert not offenders, f"ci-failure-issues.yml must delegate issue mutations to jclee-bot: {offenders}"

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

    def test_event_driven_cases_are_all_watched(self):
        import re

        text = read_workflow("ci-failure-issues.yml")
        # Every workflow name with an event-driven case "$WF_NAME" mapping must
        # be present in the workflow_run.workflows watch list, otherwise its
        # success never triggers the immediate close.
        m = re.search(r'workflow_run:\s*\n\s*workflows:\s*\n((?:\s+- "[^"]+"\n)+)', text)
        assert m, "could not find workflow_run.workflows block"
        watched = set(re.findall(r'- "([^"]+)"', m.group(1)))
        app_text = read_workflow_issue_automation_source()
        cases = set(re.findall(r'\("([^"]+)", \(', app_text))
        missing = cases - watched
        assert not missing, (
            f"event-driven case-mapped workflows missing from workflow_run watch list: {sorted(missing)}"
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
            "ci-failure-issues.yml must keep workflow_dispatch so the stale-failure sweep can be triggered manually."
        )

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
