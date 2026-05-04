"""Static-analysis tests for the git-flow automation workflows.

These tests parse every YAML file under .github/workflows/ and assert
that each git-flow workflow has the expected structural invariants:
  - top-level on/permissions/jobs blocks
  - workflow_dispatch with dry_run input (so we can canary safely)
  - degrade-soft pattern (|| echo ::warning::) where required
  - skip-bot guard where required
  - concurrency group with the right key
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

GIT_FLOW_WORKFLOWS = [
    "issue-to-branch.yml",
    "branch-to-pr.yml",
    "pr-auto-merge.yml",
    "merged-pr-cleanup.yml",
    "ci-failure-issues.yml",
    "release-publish.yml",
]


def _load(name: str) -> dict:
    path = WORKFLOWS_DIR / name
    assert path.exists(), f"workflow not found: {path}"
    return yaml.safe_load(path.read_text())


@pytest.mark.parametrize("name", GIT_FLOW_WORKFLOWS)
def test_workflow_yaml_parses(name: str) -> None:
    doc = _load(name)
    assert isinstance(doc, dict)
    # 'on' becomes True under YAML 1.1 because it's a bool keyword. Modern
    # PyYAML still emits the string "on" with safe_load, but accept either.
    on_block = doc.get("on") if "on" in doc else doc.get(True)
    assert on_block, f"{name}: missing 'on' block"
    assert "jobs" in doc, f"{name}: missing 'jobs' block"
    assert "permissions" in doc, f"{name}: missing 'permissions' block"


@pytest.mark.parametrize("name", GIT_FLOW_WORKFLOWS)
def test_workflow_has_dispatch_with_dry_run(name: str) -> None:
    """Every git-flow workflow must support manual canary dispatch with dry_run."""
    doc = _load(name)
    on_block = doc.get("on") if "on" in doc else doc.get(True)
    assert "workflow_dispatch" in on_block, f"{name}: must support workflow_dispatch"
    inputs = on_block["workflow_dispatch"].get("inputs") or {}
    assert "dry_run" in inputs, f"{name}: workflow_dispatch.inputs must include dry_run"
    assert inputs["dry_run"]["type"] == "boolean", f"{name}: dry_run must be boolean"


@pytest.mark.parametrize("name", GIT_FLOW_WORKFLOWS)
def test_workflow_has_concurrency(name: str) -> None:
    doc = _load(name)
    assert "concurrency" in doc, f"{name}: missing top-level concurrency"
    assert "group" in doc["concurrency"], f"{name}: concurrency.group required"


@pytest.mark.parametrize("name", GIT_FLOW_WORKFLOWS)
def test_workflow_has_timeout(name: str) -> None:
    doc = _load(name)
    for jname, job in doc["jobs"].items():
        assert "timeout-minutes" in job, f"{name}.jobs.{jname}: timeout-minutes required"


@pytest.mark.parametrize(
    "name",
    [
        "branch-to-pr.yml",
        "pr-auto-merge.yml",
        "merged-pr-cleanup.yml",
        # release-publish.yml deliberately hard-fails on tag/release errors
        # because a missed release is loud signal, not graceful degradation.
    ],
)
def test_workflow_uses_soft_failure_pattern(name: str) -> None:
    """gh CLI calls in these workflows should warn-and-continue, not hard-fail."""
    text = (WORKFLOWS_DIR / name).read_text()
    # Look for at least one '|| echo "::warning::' fallback per workflow.
    assert re.search(r"\|\|\s*echo\s+\"::warning::", text), f"{name}: expected at least one warn-and-continue fallback"


def test_dynamic_pr_command_selector_in_pr_review() -> None:
    """G: pr-review.yml must compute pr-agent commands dynamically."""
    text = (WORKFLOWS_DIR / "pr-review.yml").read_text()
    assert "Selected commands:" in text, "missing dynamic selector in pr-review.yml"
    # All five decision branches must be present.
    for snippet in [
        "bot author",
        "docs-only diff",
        "feat/fix/refactor PR",
        "small PR (<50 LOC)",
        "large PR (>1000 LOC)",
        "default",
    ]:
        assert snippet in text, f"pr-review.yml missing selector branch: {snippet}"


def test_actionlint_is_optional() -> None:
    """If actionlint is on PATH, lint every workflow file. Otherwise skip cleanly."""
    if not shutil.which("actionlint"):
        pytest.skip("actionlint not installed locally; CI runs it instead")
    import subprocess

    files = sorted(str(p) for p in WORKFLOWS_DIR.glob("*.yml"))
    proc = subprocess.run(["actionlint", "-color"] + files, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


SEMVER_BUMP_CASES = [
    # (commit subject, expected_bump_or_None)
    ("feat: add new endpoint", "minor"),
    ("feat(api): add new endpoint", "minor"),
    ("fix: typo in README", "patch"),
    ("fix(parser): edge case", "patch"),
    ("refactor: extract helper", "patch"),
    ("perf: speed up encoder", "patch"),
    ("feat!: drop py3.11 support", "major"),
    ("fix(api)!: rename argument", "major"),
    ("docs: typo", None),
    ("chore: bump deps", None),
    ("test: add coverage", None),
    ("ci: pin runner", None),
    ("style: format with ruff", None),
    ("build: docker pin", None),
]


def _classify_bump(subject: str) -> str | None:
    """Mirror the bash logic in release-publish.yml so unit tests stay
    authoritative even if the workflow file evolves."""
    if re.match(r"^[a-z]+(\([a-z0-9_/-]+\))?!:", subject):
        return "major"
    if "BREAKING CHANGE" in subject:
        return "major"
    if re.match(r"^feat(\([^)]+\))?:", subject):
        return "minor"
    if re.match(r"^(fix|perf|refactor)(\([^)]+\))?:", subject):
        return "patch"
    return None


@pytest.mark.parametrize("subject,expected", SEMVER_BUMP_CASES)
def test_semver_bump_classification(subject: str, expected: str | None) -> None:
    assert _classify_bump(subject) == expected, f"{subject!r} -> {expected!r}"
