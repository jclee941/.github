#!/usr/bin/env python3
"""Regression tests for the gitleaks install step in
.github/workflows/45_reusable-gitleaks.yml.

The reusable gitleaks workflow runs on self-hosted runners for private repos
(`runs-on: ${{ ... 'self-hosted' || 'ubuntu-latest' }}`). The install step used
`wget` only; the self-hosted `propose` runner lacks `wget`, so the step failed
in <0.5s with no output, leaving the gitleaks check permanently BLOCKED and
downstream sync PRs unmergeable.

These tests pin a resilient installer: it must not depend on `wget` alone, must
fall back to `curl`, and must verify the download is non-empty before extracting
so a silent fetch failure surfaces a clear error instead of a confusing
`tar` failure.
"""
from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github/workflows/45_reusable-gitleaks.yml"
)


def _install_run() -> str:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job in (doc.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            if step.get("name", "") == "Install gitleaks":
                return step.get("run", "") or ""
    raise AssertionError("could not find the 'Install gitleaks' step")


def test_install_does_not_depend_on_wget_alone() -> None:
    run = _install_run()
    assert "curl" in run, (
        "Install gitleaks must support curl as a fallback (self-hosted runners "
        "may not have wget)"
    )


def test_install_verifies_download_nonempty() -> None:
    run = _install_run()
    # A guard proving the tarball was actually downloaded before tar runs.
    assert "-s /tmp/gitleaks.tar.gz" in run, (
        "Install gitleaks must verify the downloaded tarball is non-empty "
        "before extracting"
    )


def test_install_still_extracts_and_chmods() -> None:
    run = _install_run()
    assert "tar -xzf /tmp/gitleaks.tar.gz" in run
    assert 'chmod +x "$HOME/.local/bin/gitleaks"' in run
