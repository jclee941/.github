from __future__ import annotations

import subprocess
from pathlib import Path
from typing import cast

import pytest
import yaml

from jclee_bot.json_boundary import is_object_mapping, object_dict, object_list

REPO_ROOT = Path(__file__).resolve().parents[2]
WF_DIR = REPO_ROOT / ".github" / "workflows"
assert WF_DIR.exists(), f"Workflows dir not found: {WF_DIR}"


def read_workflow(name: str) -> str:
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
    return [object_dict(step) for step in steps if is_object_mapping(step)]


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
