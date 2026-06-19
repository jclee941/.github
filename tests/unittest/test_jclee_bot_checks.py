"""Tests for the fork-owned jclee_bot App Checks-API runner.

These checks let the jclee-bot GitHub App run lightweight static checks on a PR
and report them via the GitHub Checks API, so installing the App gives the
checks with zero per-repo workflow files (Oracle architecture A+C).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from jclee_bot.checks import CheckResult, actionlint_check, docs_policy, pr_metadata, secret_scan


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

    def test_readme_automation_pr_ignores_size_limit(self):
        r = pr_metadata.run(
            title="docs: auto-update README.md",
            head_ref="bot/auto-readme-update",
            base_ref="master",
            changed_files=["README.md"],
            additions=5000,
            deletions=10,
        )

        assert r.conclusion == "success"

    def test_retired_workflow_cleanup_pr_ignores_size_limit(self):
        r = pr_metadata.run(
            title="chore: remove retired downstream workflows",
            head_ref="bot/remove-downstream-workflows",
            base_ref="master",
            changed_files=[".github/workflows/03_pr-checks.yml", ".github/workflows/20_readme-gen.yml"],
            additions=0,
            deletions=5000,
        )

        assert r.conclusion == "success"

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

    def test_run_scans_only_changed_files(self, monkeypatch, tmp_path):
        (tmp_path / "README.md").write_text("# ok\n", encoding="utf-8")
        (tmp_path / ".env").write_text("SECRET=value\n", encoding="utf-8")
        seen_sources: list[set[str]] = []

        def fake_run(args, **_kwargs):
            source = tmp_path
            report_path = None
            for index, value in enumerate(args):
                if value == "--source":
                    source = Path(args[index + 1])
                if value == "--report-path":
                    report_path = Path(args[index + 1])
            seen_sources.append({str(path.relative_to(source)) for path in source.rglob("*") if path.is_file()})
            report_path.write_text("[]", encoding="utf-8")
            return None

        monkeypatch.setattr(secret_scan.shutil, "which", lambda _name: "gitleaks")
        monkeypatch.setattr(secret_scan.subprocess, "run", fake_run)

        r = secret_scan.run(workspace=str(tmp_path), changed_files=["README.md"])

        assert r.conclusion == "success"
        assert seen_sources == [{"README.md"}]


class TestActionlint:
    def test_no_workflow_changes_is_neutral(self):
        r = actionlint_check.run(changed_files=["src/app.py"], workspace="/tmp/x")
        assert r.name == "jclee-bot / actionlint"
        assert r.conclusion == "neutral"
        assert "no workflow" in r.summary.lower()

    def test_deleted_workflow_changes_pass_without_linting_unrelated_workflows(self, tmp_path):
        (tmp_path / ".github" / "workflows").mkdir(parents=True)
        (tmp_path / ".github" / "workflows" / "legacy.yml").write_text("name: legacy\n", encoding="utf-8")

        r = actionlint_check.run(
            changed_files=[".github/workflows/deleted.yml"],
            workspace=str(tmp_path),
            actionlint_bin="actionlint",
        )

        assert r.conclusion == "success"
        assert "deleted" in r.summary

    def test_clean_workflows_pass(self):
        r = actionlint_check.result_from_output(returncode=0, output="", ran=True)
        assert r.conclusion == "success"

    def test_lint_errors_fail(self):
        out = ".github/workflows/x.yml:3:1: unexpected key \"jobss\" [syntax-check]"
        r = actionlint_check.result_from_output(returncode=1, output=out, ran=True)
        assert r.conclusion == "failure"
        assert "jobss" in r.summary


class TestDocsPolicy:
    def test_markdown_private_ip_fails(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "runbook.md").write_text("connect to 192.168.1.10\n", encoding="utf-8")
        r = docs_policy.run(changed_files=["docs/runbook.md"], workspace=str(tmp_path))
        assert r.name == "jclee-bot / docs-policy"
        assert r.conclusion == "failure"
        assert "docs/runbook.md:1" in r.summary

    def test_code_change_without_docs_is_neutral(self, tmp_path):
        r = docs_policy.run(changed_files=["src/app.py"], workspace=str(tmp_path))
        assert r.conclusion == "neutral"
        assert "Code changed" in r.summary

    def test_docs_update_passes(self, tmp_path):
        (tmp_path / "README.md").write_text("# ok\n", encoding="utf-8")
        r = docs_policy.run(changed_files=["README.md"], workspace=str(tmp_path))
        assert r.conclusion == "success"
