#!/usr/bin/env python3
"""Tests for scripts/check_workflow_scripts.py."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from check_workflow_scripts import (
    check_script,
    check_workflows,
    extract_script_blocks,
)

_CLEAN_SCRIPT = textwrap.dedent(
    """\
    const x = 1;
    if (x > 0) {
      console.log('positive');
    } else {
      console.log('non-positive');
    }
    """
)

_BROKEN_SCRIPT = textwrap.dedent(
    """\
    const x = 1;
    if (x > 0) {
      console.log('positive');
    } else {
      console.log('non-positive');
    """  # missing closing brace for else
)

_EXPR_SCRIPT = textwrap.dedent(
    """\
    const body = `Workflow: ${{ github.workflow }} / sha ${{ github.sha }}`;
    console.log(body);
    """
)


def _write_workflow(path: Path, script: str, step_name: str = "Run script") -> None:
    path.write_text(
        textwrap.dedent(
            f"""\
            name: Test WF
            on: push
            jobs:
              demo:
                runs-on: ubuntu-latest
                steps:
                  - name: {step_name}
                    uses: actions/github-script@v9
                    with:
                      script: |
            """
        )
        + textwrap.indent(script, " " * 24),
        encoding="utf-8",
    )


class TestCheckScript:
    def test_clean_script_passes(self):
        ok, msg = check_script(_CLEAN_SCRIPT)
        assert ok, msg

    def test_broken_script_fails(self):
        ok, msg = check_script(_BROKEN_SCRIPT)
        assert not ok
        assert "SyntaxError" in msg or "Unexpected" in msg

    def test_github_expr_not_false_flagged(self):
        # ${{ }} is resolved by GitHub before JS runs; must not be a syntax error.
        ok, msg = check_script(_EXPR_SCRIPT)
        assert ok, msg

    def test_top_level_await_allowed(self):
        # github-script wraps in async fn, so top-level await must be valid.
        ok, msg = check_script("await Promise.resolve(1);\nreturn;")
        assert ok, msg


class TestCheckWorkflows:
    def test_detects_broken_workflow(self, tmp_path: Path):
        _write_workflow(tmp_path / "bad.yml", _BROKEN_SCRIPT, "Broken step")
        failures = check_workflows(str(tmp_path))
        assert len(failures) == 1
        block, msg = failures[0]
        assert block.step == "Broken step"
        assert "SyntaxError" in msg or "Unexpected" in msg

    def test_clean_workflow_passes(self, tmp_path: Path):
        _write_workflow(tmp_path / "good.yml", _CLEAN_SCRIPT)
        assert check_workflows(str(tmp_path)) == []

    def test_expr_workflow_passes(self, tmp_path: Path):
        _write_workflow(tmp_path / "expr.yml", _EXPR_SCRIPT)
        assert check_workflows(str(tmp_path)) == []

    def test_extracts_all_blocks(self, tmp_path: Path):
        _write_workflow(tmp_path / "a.yml", _CLEAN_SCRIPT)
        _write_workflow(tmp_path / "b.yml", _EXPR_SCRIPT)
        blocks = extract_script_blocks(str(tmp_path))
        assert len(blocks) == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
