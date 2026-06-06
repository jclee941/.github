#!/usr/bin/env python3
"""check_workflow_scripts.py — validate embedded github-script JavaScript.

Why this exists
---------------
`actions/github-script` steps embed JavaScript inside a YAML `script:` block.
`actionlint` validates workflow structure and shell, but it does NOT parse the
embedded JS, so a missing brace ships silently and the step fails at runtime
with cryptic errors like "SyntaxError: Unexpected token ')'". Two such bugs
(31_repo-health.yml, 82_issue-label.yml) caused recurring Repository Health /
Issue Label workflow failures.

This guard extracts every github-script block from all workflows and runs
`node --check` on each, so syntax bugs are caught in CI (wired into
90_sanity.yml) before they reach a live run.

How it stays correct
--------------------
GitHub substitutes ``${{ <expr> }}`` interpolations into the script BEFORE the
JS executes, so a bare ``${{ github.workflow }}`` is valid at runtime even
though it is not valid JS source. We replace those expressions with a string
placeholder before the syntax check to avoid false positives, mirroring what
GitHub does at runtime.

Usage:
    check_workflow_scripts.py [WORKFLOW_DIR]

Defaults to ``.github/workflows``. Exits non-zero and prints
``file | step | error`` for every block that fails ``node --check``.
"""
from __future__ import annotations

import glob
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass

import yaml

# GitHub Actions ${{ ... }} expressions are resolved before the JS runs.
_EXPR = re.compile(r"\$\{\{.*?\}\}", re.DOTALL)


@dataclass(frozen=True)
class ScriptBlock:
    file: str
    job: str
    step: str
    script: str


def _is_github_script(step: dict) -> bool:
    uses = step.get("uses", "") or ""
    return "actions/github-script" in uses


def extract_script_blocks(workflow_dir: str) -> list[ScriptBlock]:
    """Return every actions/github-script `with.script` block in the dir."""
    blocks: list[ScriptBlock] = []
    for wf in sorted(glob.glob(os.path.join(workflow_dir, "**", "*.yml"), recursive=True)):
        try:
            doc = yaml.safe_load(open(wf, encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if not isinstance(doc, dict):
            continue
        for job_name, job in (doc.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            for step in job.get("steps") or []:
                if not isinstance(step, dict) or not _is_github_script(step):
                    continue
                script = (step.get("with") or {}).get("script")
                if not isinstance(script, str) or not script.strip():
                    continue
                blocks.append(
                    ScriptBlock(
                        file=wf,
                        job=str(job_name),
                        step=str(step.get("name", "?")),
                        script=script,
                    )
                )
    return blocks


def check_script(script: str) -> tuple[bool, str]:
    """Run `node --check` on the github-script body. Returns (ok, message)."""
    # Substitute ${{ }} expressions (GitHub resolves these before JS runs).
    js = _EXPR.sub("__GH_EXPR__", script)
    # github-script wraps the body in an async function; replicate so that
    # top-level `await`/`return` are valid and brace balance is enforced.
    wrapped = (
        "(async function(github, context, core, exec, io, fetch, glob, "
        "require, process, console, __dirname, __filename){\n"
        + js
        + "\n})"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(wrapped)
        path = fh.name
    try:
        result = subprocess.run(
            ["node", "--check", path], capture_output=True, text=True
        )
    finally:
        os.unlink(path)
    if result.returncode == 0:
        return True, ""
    err_lines = result.stderr.strip().splitlines()
    msg = next(
        (line.strip() for line in err_lines if "SyntaxError" in line),
        err_lines[-1].strip() if err_lines else "unknown syntax error",
    )
    return False, msg


def check_workflows(workflow_dir: str = ".github/workflows") -> list[tuple[ScriptBlock, str]]:
    """Return a list of (block, error) for every block that fails the check."""
    failures: list[tuple[ScriptBlock, str]] = []
    for block in extract_script_blocks(workflow_dir):
        ok, msg = check_script(block.script)
        if not ok:
            failures.append((block, msg))
    return failures


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    workflow_dir = args[0] if args else ".github/workflows"

    blocks = extract_script_blocks(workflow_dir)
    failures = check_workflows(workflow_dir)

    if not failures:
        print(f"OK: {len(blocks)} github-script block(s) validated, 0 syntax errors.")
        return 0

    print("Invalid github-script JavaScript detected:", file=sys.stderr)
    for block, msg in failures:
        print(f"  {block.file} | {block.step} | {msg}", file=sys.stderr)
    print(
        "\nFix the embedded JavaScript (check for unbalanced braces/parens). "
        "github-script wraps the body in an async function.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
