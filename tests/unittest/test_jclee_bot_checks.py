"""Tests for the fork-owned jclee_bot App Checks-API runner.

These checks let the jclee-bot GitHub App run lightweight static checks on a PR
and report them via the GitHub Checks API, so installing the App gives the
checks with zero per-repo workflow files (Oracle architecture A+C).
"""
from __future__ import annotations

import pytest

from jclee_bot.checks import CheckResult, actionlint_check, pr_metadata, secret_scan


class TestCheckResult:
    def test_conclusion_must_be_valid(self):
        with pytest.raises(ValueError):
            CheckResult(name="x", conclusion="bogus", title="t", summary="s")

    def test_valid_result(self):
        r = CheckResult(name="jclee-bot / x", conclusion="success", title="t", summary="s")
        assert r.conclusion == "success"


class TestPrMetadata:
    def test_conventional_title_passes(self):
        r = pr_metadata.run(
            title="feat: add NAS build cache",
            head_ref="feat/nas-cache",
            base_ref="master",
            changed_files=["a.py", "b.py"],
            additions=10,
            deletions=2,
        )
        assert r.name == "jclee-bot / pr-metadata"
        assert r.conclusion == "success"

    def test_non_conventional_title_fails(self):
        r = pr_metadata.run(
            title="random change without prefix",
            head_ref="feat/x",
            base_ref="master",
            changed_files=["a.py"],
            additions=1,
            deletions=0,
        )
        assert r.conclusion == "failure"
        assert "title" in r.summary.lower()

    def test_oversized_pr_fails(self):
        r = pr_metadata.run(
            title="feat: huge",
            head_ref="feat/huge",
            base_ref="master",
            changed_files=[f"f{i}.py" for i in range(60)],
            additions=5000,
            deletions=10,
        )
        assert r.conclusion == "failure"
        assert "loc" in r.summary.lower() or "size" in r.summary.lower()

    def test_sensitive_file_fails(self):
        r = pr_metadata.run(
            title="feat: add config",
            head_ref="feat/cfg",
            base_ref="master",
            changed_files=["app/.env", "src/main.py"],
            additions=3,
            deletions=0,
        )
        assert r.conclusion == "failure"
        assert "sensitive" in r.summary.lower()


class TestSecretScan:
    def test_no_findings_passes(self):
        r = secret_scan.result_from_gitleaks(findings=[], skipped=False)
        assert r.name == "jclee-bot / secret-scan"
        assert r.conclusion == "success"

    def test_findings_fail(self):
        findings = [
            {"RuleID": "aws-access-key", "File": "src/app.py", "StartLine": 12},
        ]
        r = secret_scan.result_from_gitleaks(findings=findings, skipped=False)
        assert r.conclusion == "failure"
        assert "src/app.py" in r.summary
        assert "aws-access-key" in r.summary

    def test_skipped_is_neutral(self):
        r = secret_scan.result_from_gitleaks(findings=[], skipped=True)
        assert r.conclusion == "neutral"


class TestActionlint:
    def test_no_workflow_changes_is_neutral(self):
        r = actionlint_check.run(changed_files=["src/app.py"], workspace="/tmp/x")
        assert r.name == "jclee-bot / actionlint"
        assert r.conclusion == "neutral"
        assert "no workflow" in r.summary.lower()

    def test_clean_workflows_pass(self):
        r = actionlint_check.result_from_output(returncode=0, output="", ran=True)
        assert r.conclusion == "success"

    def test_lint_errors_fail(self):
        out = ".github/workflows/x.yml:3:1: unexpected key \"jobss\" [syntax-check]"
        r = actionlint_check.result_from_output(returncode=1, output=out, ran=True)
        assert r.conclusion == "failure"
        assert "jobss" in r.summary
