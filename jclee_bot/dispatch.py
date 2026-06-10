"""Dispatch a GitHub pull_request webhook payload to the App-owned checks.

Pure orchestration — given the webhook payload + the PR's changed files + a
workspace checkout, return the list of CheckResults. The webhook route in
``jclee_bot.app`` maps these onto GitHub Check Runs via the Checks API.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from jclee_bot.checks import CheckResult, actionlint_check, pr_metadata, secret_scan

_PR_ACTIONS = {"opened", "synchronize", "reopened", "ready_for_review"}


def head_sha(payload: dict[str, Any]) -> str:
    return payload.get("pull_request", {}).get("head", {}).get("sha", "")


def run_checks(
    payload: dict[str, Any],
    *,
    changed_files: Sequence[str],
    workspace: str,
) -> list[CheckResult]:
    """Run all App-owned checks for a pull_request payload.

    Returns an empty list for non-PR or unhandled actions so callers can no-op.
    """
    if payload.get("action") not in _PR_ACTIONS:
        return []
    pr = payload.get("pull_request")
    if not isinstance(pr, dict):
        return []

    results: list[CheckResult] = [
        pr_metadata.run(
            title=pr.get("title", ""),
            head_ref=pr.get("head", {}).get("ref", ""),
            base_ref=pr.get("base", {}).get("ref", ""),
            changed_files=changed_files,
            additions=int(pr.get("additions", 0) or 0),
            deletions=int(pr.get("deletions", 0) or 0),
        ),
        secret_scan.run(workspace=workspace),
        actionlint_check.run(changed_files=changed_files, workspace=workspace),
    ]
    return results
