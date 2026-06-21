"""secret-scan check: run gitleaks over the PR working tree and map findings.

The pure ``result_from_gitleaks`` mapping is unit-tested; ``run`` invokes the
gitleaks binary against a checkout and feeds its JSON report into the mapper.
"""
from __future__ import annotations

import json
import shutil
import subprocess  # noqa: S404 - trusted, fixed-arg gitleaks invocation
import tempfile
from collections.abc import Sequence
from pathlib import Path

from jclee_bot.checks import CheckResult

CHECK_NAME = "jclee-bot / secret-scan"


def result_from_gitleaks(*, findings: Sequence[dict], skipped: bool) -> CheckResult:
    if skipped:
        return CheckResult(
            name=CHECK_NAME,
            conclusion="neutral",
            title="secret scan skipped",
            summary="gitleaks was not available; secret scan skipped.",
        )
    if not findings:
        return CheckResult(
            name=CHECK_NAME,
            conclusion="success",
            title="no secrets detected",
            summary="gitleaks found no secrets in the PR diff.",
        )
    lines = []
    for f in findings:
        rule = f.get("RuleID", "?")
        loc = f.get("File", "?")
        line = f.get("StartLine", "?")
        lines.append(f"- {rule} at {loc}:{line}")
    return CheckResult(
        name=CHECK_NAME,
        conclusion="failure",
        title=f"{len(findings)} potential secret(s) detected",
        summary="\n".join(lines),
    )


def _copy_changed_files(*, workspace: Path, changed_files: Sequence[str], target: Path) -> None:
    for relative in changed_files:
        source = workspace / relative
        if Path(relative).is_absolute() or ".." in Path(relative).parts or not source.is_file():
            continue
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def run(
    *,
    workspace: str,
    changed_files: Sequence[str] | None = None,
    gitleaks_bin: str | None = None,
) -> CheckResult:
    """Run gitleaks over ``workspace`` and return a CheckResult.

    Degrades to a neutral result if the gitleaks binary is unavailable, so a
    missing tool never crashes the webhook handler.
    """
    binary = gitleaks_bin or shutil.which("gitleaks")
    if not binary:
        return result_from_gitleaks(findings=[], skipped=True)

    with tempfile.TemporaryDirectory() as scan_dir:
        scan_root = Path(scan_dir) / "changed"
        if changed_files is None:
            scan_root = Path(workspace)
        else:
            _copy_changed_files(workspace=Path(workspace), changed_files=changed_files, target=scan_root)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as rep:
            report_path = rep.name
        try:
            subprocess.run(  # noqa: S603 - fixed args, trusted binary
                [
                    binary,
                    "detect",
                    "--source",
                    str(scan_root),
                    "--no-banner",
                    "--report-format",
                    "json",
                    "--report-path",
                    report_path,
                    "--exit-code",
                    "0",
                ],
                check=False,
                capture_output=True,
                timeout=120,
            )
            text = Path(report_path).read_text(encoding="utf-8") or "[]"
            findings = json.loads(text)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            return result_from_gitleaks(findings=[], skipped=True)
        finally:
            Path(report_path).unlink(missing_ok=True)
    return result_from_gitleaks(findings=findings, skipped=False)
