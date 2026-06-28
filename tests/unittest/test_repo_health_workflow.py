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


def test_repo_health_closes_existing_issue_when_required_docs_recover() -> None:
    script = _repo_health_script()

    assert "if (missing.length === 0)" in script
    assert "github.rest.issues.createComment" in script
    assert "state: 'closed'" in script
    assert "all required files present; closed issue" in script
