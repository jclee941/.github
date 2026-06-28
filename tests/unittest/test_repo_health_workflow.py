from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW = Path(".github/workflows/31_repo-health.yml")


def _repo_health_script() -> str:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = data["jobs"]["check-health"]["steps"]
    for step in steps:
        if step.get("name") == "Check repository health":
            return str(step["with"]["script"])
    raise AssertionError("Check repository health step not found")


def test_repo_health_leaves_recovered_issue_closure_to_app() -> None:
    script = _repo_health_script()

    assert "if (missing.length === 0)" in script
    assert "github.rest.issues.createComment" not in script
    assert "state: 'closed'" not in script
    assert "jclee-bot App issue maintenance handles closure" in script
