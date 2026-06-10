#!/usr/bin/env python3
"""Tests for .github/workflows/37_ci-failure-issues.yml conclusion handling.

The workflow auto-creates a ci-failure issue when a watched workflow_run
finishes. It previously coerced BOTH `cancelled` and `skipped` conclusions to
`failure`, which spammed false-positive issues:
  - `skipped` is normal: e.g. CI Auto-Heal has `if: ... conclusion == 'failure'`
    so it legitimately skips whenever upstream succeeded. That is NOT a failure.

These tests pin that `skipped` is NOT treated as a failure (no spurious issue).
"""
from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github/workflows/37_ci-failure-issues.yml"
)


def _compute_event_run() -> str:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job in (doc.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            if step.get("id") == "ev":
                return step.get("run", "") or ""
    raise AssertionError("could not find the 'Compute event' (id: ev) step")


def test_skipped_is_not_coerced_to_failure() -> None:
    """The coerce-to-failure block must not include 'skipped'."""
    region = _coercion_region(_compute_event_run())
    assert "skipped" not in region, (
        "skipped must not be coerced to failure (it is normal, not a failure); "
        f"coercion region:\n{region}"
    )


def _coercion_region(run: str) -> str:
    """Return only the conclusion-coercion code region (the if-block that may
    rewrite CONCLUSION to 'failure'), excluding the validation allow-list."""
    lines = run.splitlines()
    region = []
    capture = False
    for line in lines:
        if "treat as failure" in line.lower() or "CONCLUSION=\"failure\"" in line:
            capture = True
        if capture:
            region.append(line)
    return "\n".join(region)


def test_skipped_not_in_coercion_block() -> None:
    """The block that rewrites CONCLUSION to 'failure' must not include skipped."""
    region = _coercion_region(_compute_event_run())
    assert "skipped" not in region, (
        "the coerce-to-failure block must not include 'skipped'; "
        f"region was:\n{region}"
    )
