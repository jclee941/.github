"""Static checks for the privileged security review workflow.

The live label-trigger test was removed along with the automation-e2e-public
canary repo; what remains is the static fork-guard analysis, which does not
need a canary and guards the pull_request_target workflow against checking out
untrusted PR head code.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.security_review

SECURITY_WORKFLOW_PATH = ".github/workflows/11_security-pr-review.yml"


def test_security_review_workflow_has_fork_guard() -> None:
    workflow = (Path(__file__).parents[2] / SECURITY_WORKFLOW_PATH).read_text(encoding="utf-8")

    assert "github.event_name == 'pull_request_target'" in workflow
    assert "github.event.label.name == 'security-review'" in workflow
    assert "github.event.pull_request.head.repo.full_name == github.repository" in workflow
    assert "github.event.pull_request.user.login == 'jclee941'" in workflow

    risky_checkout_ref = re.compile(
        "".join(
            (
                r"uses:\s*actions/checkout@.*?ref:\s*\$[{][{]\s*",
                r"(?:github\.event\.pull_request\.head\.(?:sha|ref)|github\.head_ref)",
            )
        ),
        re.DOTALL,
    )
    assert not risky_checkout_ref.search(workflow), "pull_request_target workflow must not checkout PR head code"
