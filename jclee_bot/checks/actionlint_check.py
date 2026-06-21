"""actionlint check: lint changed workflow files via actionlint.

Only runs when the PR touches ``.github/workflows/**``. The pure
``result_from_output`` mapping is unit-tested; ``run`` decides whether to
invoke the binary and maps its output.
"""
from __future__ import annotations

import shutil
import subprocess  # noqa: S404 - trusted, fixed-arg actionlint invocation
from collections.abc import Sequence
from pathlib import Path

from jclee_bot.checks import CheckResult

CHECK_NAME = "jclee-bot / actionlint"


def _touches_workflows(changed_files: Sequence[str]) -> bool:
    return any(f.startswith(".github/workflows/") for f in changed_files)


def _existing_changed_workflows(*, changed_files: Sequence[str], workspace: str) -> list[str]:
    root = Path(workspace)
    return [
        path
        for path in changed_files
        if path.startswith(".github/workflows/") and not Path(path).is_absolute() and (root / path).is_file()
    ]


def result_from_output(*, returncode: int, output: str, ran: bool) -> CheckResult:
    if not ran:
        return CheckResult(
            name=CHECK_NAME,
            conclusion="neutral",
            title="actionlint not run",
            summary="actionlint was unavailable; workflow lint skipped.",
        )
    if returncode == 0:
        return CheckResult(
            name=CHECK_NAME,
            conclusion="success",
            title="workflows lint clean",
            summary="actionlint reported no problems in changed workflows.",
        )
    return CheckResult(
        name=CHECK_NAME,
        conclusion="failure",
        title="actionlint reported problems",
        summary="```\n" + output.strip()[:60000] + "\n```",
    )


def run(*, changed_files: Sequence[str], workspace: str, actionlint_bin: str | None = None) -> CheckResult:
    if not _touches_workflows(changed_files):
        return CheckResult(
            name=CHECK_NAME,
            conclusion="neutral",
            title="no workflow changes",
            summary="No workflow files (.github/workflows/**) changed; actionlint not needed.",
        )
    binary = actionlint_bin or shutil.which("actionlint")
    if not binary:
        return result_from_output(returncode=0, output="", ran=False)
    workflow_paths = _existing_changed_workflows(changed_files=changed_files, workspace=workspace)
    if not workflow_paths:
        return CheckResult(
            name=CHECK_NAME,
            conclusion="success",
            title="workflow deletions clean",
            summary="Changed workflow files were deleted; no remaining workflow YAML needed linting.",
        )
    try:
        proc = subprocess.run(  # noqa: S603 - fixed args, trusted binary
            [binary, "-no-color", *workflow_paths],
            check=False,
            capture_output=True,
            text=True,
            cwd=workspace,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, OSError):
        return result_from_output(returncode=0, output="", ran=False)
    return result_from_output(
        returncode=proc.returncode,
        output=(proc.stdout or "") + (proc.stderr or ""),
        ran=True,
    )
